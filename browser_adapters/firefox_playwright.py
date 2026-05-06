import os
import random
import re
import logging
import signal
import psutil
import concurrent.futures
import copy
import tempfile
from common import FuzzedBrowser
from playwright.async_api import async_playwright  # 更改为异步API
import concurrent.futures
import subprocess
from threading import Lock
from typing import List, Tuple, Optional
import asyncio

class FirefoxPlaywrightBrowser(FuzzedBrowser):
    def __init__(self, thread_id, timeout):
        self.thread_id = thread_id
        self.timeout_sec = int(timeout) / 1000
        self.seperate = False
        self.close_browser_prob = 1.0 / 50
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.tmp_dir = "/tmp/firefoxtmpdir" + str(self.thread_id) + "pid" + str(
            os.getpid()) + "rand" + str(random.random())
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.profile_dir = os.path.join(self.tmp_dir, 'profile')
        os.makedirs(self.profile_dir, exist_ok=True)

        self.use_xvfb = True
        if "NO_XVFB" in os.environ:
            logging.info(f"[{self.thread_id}]: no xvfb")
            self.use_xvfb = False

        if self.use_xvfb:
            temp_lock = Lock()
            with temp_lock:
                self.display_port = self._free_port()
            logging.info(f"[{self.thread_id}]: display port: {self.display_port}")
            self.xvfb = subprocess.Popen(
                ["Xvfb", f":{self.display_port}", "-ac", "-maxclients", "2048"])
        else:
            self.display_port = None
            self.xvfb = None

        if "FIREFOX_PATH" in os.environ:
            self.firefox_path = os.environ["FIREFOX_PATH"]
        else:
            logging.error(f"[{thread_id}]: didn't set FIREFOX_PATH env var")
            exit(1)

        self.termination_log = None
        self.msg_path = os.path.join(self.tmp_dir, 'browser.log')
        self.firefox_error = os.path.join(self.tmp_dir, 'console.error')

    def __del__(self):
        try:
            self.xvfb.kill()
        except:
            pass
        try:
            import asyncio
            asyncio.run(self.close_browser())
        except:
            pass

    def _free_port(self):
        import socket
        from contextlib import closing
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    async def launch_browser(self):  # 改为异步方法
        logging.info(f"[{self.thread_id}]: launch_browser start...")
        if self.use_xvfb and self.xvfb.poll() is not None:
            logging.info(f"[{self.thread_id}]: restarting xvfb")
            self.xvfb.kill()
            self.xvfb = subprocess.Popen(
                ["Xvfb", f":{self.display_port}", "-ac", "-maxclients", "2048"])

        try:
            os.makedirs(os.path.dirname(self.msg_path), exist_ok=True)
            open(self.msg_path, 'w').close()
        except Exception as e:
            logging.error(f"[{self.thread_id}]: Failed to init log file: {str(e)}")

        try:
            logging.info(f"[{self.thread_id}]: start launching playwright")
            self.playwright = await async_playwright().start()  # 异步启动

            firefox_user_prefs = {
                "app.update.auto": False,
                "app.update.enabled": False,
                "dom.report_all_js_exceptions": False,
                "browser.tabs.crashReporting.includeURL": True,
                "toolkit.startup.max_resumed_crashes": -1,
                "browser.safemode": True
            }

            firefox_env = {
                'MOZ_LOG': 'timestamp,nsHttp:5,sync',
                'MOZ_LOG_FILE': self.msg_path,
                'MOZ_DISABLE_CONTENT_SANDBOX': '1',
                'FIREFOX_ERROR': self.firefox_error
            }

            launch_options = {
                "executable_path": self.firefox_path,
                "headless": True,
                "args": [
                    "--new-tab",
                    f"--MOZ_LOG_FILE={self.msg_path}"
                ],
                "firefox_user_prefs": firefox_user_prefs,
                "env": firefox_env,
                "timeout": self.timeout_sec * 1000
            }

            if self.use_xvfb:
                os.environ["DISPLAY"] = f":{self.display_port}"

            self.browser = await self.playwright.firefox.launch(**launch_options)  # 异步启动
            self.context = await self.browser.new_context()  # 异步创建上下文
            self.page = await self.context.new_page()  # 异步创建页面

            self.page.on("pageerror", lambda exc: print(f"uncaught pageerror exception: {exc}"))
            self.page.on("crash", lambda exc: print(f"uncaught crash exception: {exc}"))

            logging.info(f"[{self.thread_id}]: playwright launched successfully")
            return True
        except Exception as e:
            logging.error(f"[{self.thread_id}]: failed to launch browser: {str(e)}")
            await self.close_browser()
            return False

    async def close_browser(self):  # 改为异步方法
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()  # 异步停止
            logging.info(f"[{self.thread_id}]: browser closed successfully")
        except Exception as e:
            logging.error(f"[{self.thread_id}]: error closing browser: {str(e)}")
        finally:
            self.context = None
            self.browser = None
            self.playwright = None

    async def close_all_tabs(self):  # 改为异步方法
        if self.context:
            await self.context.close()
        self.context = await self.browser.new_context()
        
    async def ready(self):  # 改为异步方法
        try:
            await self.close_browser()
            await self.launch_browser()
        except BaseException:
            await self.close_browser()
            await self.launch_browser()
        
    def clone(self):
        cloned = copy.copy(self)
        cloned.browser = None
        cloned.context = None
        cloned.page = None
        return cloned

    async def fuzz(self, path: str) -> bool:  # 改为异步方法
        try:
            logging.info(f"[{self.thread_id}]: fuzzing start...")
            file_url = f"file://{os.path.abspath(path)}"
            await self.page.goto(file_url, timeout=self.timeout_sec * 1000)  # 异步导航
            await self.page.content()
            return True
        except Exception as e:
            try:
                logging.error(f"[{self.thread_id}]: fuzzing error: {str(e)}")
                ret = False
                content = await self.page.evaluate("()=>{return 'I am ok!'}")
                if content == "I am ok!": ret = True
                if ret == False:
                    await self.close_browser()
                    await self.launch_browser()
                return ret
            except Exception as e:
                logging.error(f"[{self.thread_id}]: fuzzing error again: {str(e)}")
                await self.close_browser()
                await self.launch_browser()
                return False
            
    async def execute_script(self, code):  # 改为异步方法并添加超时检查
        try:
            # 用 asyncio.wait_for 来为 evaluate 调用设置5秒超时
            result = await asyncio.wait_for(
                self.page.evaluate(code),
                timeout=self.timeout_sec
            )
            await self.page.content()
            return True
        except Exception as e:
            try:
                logging.error(f"[{self.thread_id}]: fuzzing error: {str(e)}")
                ret = False
                content = await self.page.evaluate("()=>{return 'I am ok!'}")
                if content == "I am ok!": ret = True
                if ret == False:
                    await self.close_browser()
                    await self.launch_browser()
                return ret
            except Exception as e:
                logging.error(f"[{self.thread_id}]: fuzzing error again: {str(e)}")
                await self.close_browser()
                await self.launch_browser()
                return False

    async def get_statement_valid_feedback(self) -> Optional[str]:  # 改为异步方法
        try:
            return await self.page.evaluate("""() => {
                if (!window.myFeedback) window.myFeedback = [];
                const res = JSON.stringify(window.myFeedback);
                window.myFeedback = [];
                return res;
            }""")
        except Exception as e:
            logging.error(f"[{self.thread_id}]: feedback error: {str(e)}")
            return None

    async def get_valid_variables(self) -> Optional[str]:  # 改为异步方法
        try:
            code = """() => {
                const variables = [];
                for (const varName of Object.keys(window)) {
                    if (window[varName] !== null) {
                        variables.push(varName);
                    }
                }
                return JSON.stringify(variables);
            }"""
            result = await asyncio.wait_for(
                self.page.evaluate(code),
                timeout=self.timeout_sec
            )
            return result
        except Exception as e:
            logging.error(f"[{self.thread_id}]: variables error: {str(e)}")
            return []
    
    def message(self) -> str:
        """获取浏览器日志信息（保持同步方法）"""
        try:
            if self.termination_log:
                tmp = self.termination_log
                self.termination_log = None
                return tmp
            return self._get_browser_logs()
        except Exception as e:
            logging.error(f"[{self.thread_id}]: Failed to get message: {str(e)}")
            return f"Error retrieving logs: {str(e)}"

    def _get_browser_logs(self) -> str:
        try:
            if not os.path.exists(self.msg_path):
                return "Log file not found"
            with open(self.msg_path, "r", encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                return ''.join(lines[-500:]).strip()
        except Exception as e:
            return f"Log read error: {str(e)}"

    def _capture_termination_log(self):
        try:
            self.termination_log = self._get_browser_logs()
            open(self.msg_path, 'w').close()
        except Exception as e:
            logging.error(f"[{self.thread_id}]: Failed to capture termination log: {str(e)}")