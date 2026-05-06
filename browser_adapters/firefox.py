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
from selenium.webdriver.common.utils import free_port
from selenium.webdriver.firefox import webdriver
# from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.firefox.firefox_profile import FirefoxProfile
import subprocess
import errno
from selenium.common.exceptions import UnexpectedAlertPresentException, InvalidSessionIdException
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from threading import Lock
from typing import List, Tuple, Optional

import urllib3
from urllib3.exceptions import ReadTimeoutError


class FirefoxSeleniumBrowser(FuzzedBrowser):
    def __init__(self, thread_id, timeout):
        self.thread_id = thread_id
        self.timeout_sec = int(timeout) / 1000
        self.firefox = None
        self.seperate = False
        self.close_browser_prob = 1.0 / 50
        self.browser: Firefox = None  # actually it is a driver
        self.tmp_dir = "/tmp/firefoxtmpdir" + str(self.thread_id) + "pid" + str(
            os.getpid()) + "rand" + str(random.random())
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.profile_dir = os.path.join(self.tmp_dir, 'profile')
        os.makedirs(self.profile_dir, exist_ok=True)
        self.firefox_error = os.path.join(self.tmp_dir, 'console.error')
        self.msg_path = self.tmp_dir + "/tmp_log"
        self.profile_path = self.tmp_dir + "/profile"

        self.use_xvfb = True
        if "NO_XVFB" in os.environ:
            logging.info(f"[{self.thread_id}]: no xvfb")
            self.use_xvfb = False

        if self.use_xvfb:
            temp_lock = Lock()
            with temp_lock:
                self.display_port = free_port()
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
        if "FIREFOXDRIVER_PATH" in os.environ:
            self.firefox_driver_path = os.environ["FIREFOXDRIVER_PATH"]
        else:
            logging.error(f"[{thread_id}]: didn't set FIREFOXDRIVER_PATH env var")
            exit(1)
        self.termination_log = None

        # self.launch_browser()

    def __del__(self):
        try:
            self.xvfb.kill()
        except:
            pass
        try:
            self.close_browser()
        except:
            pass

    def launch_browser(self):
        if self.use_xvfb and self.xvfb.poll() is not None:
            logging.info(f"[{self.thread_id}]: xvfb has been kill. port: {self.display_port}")
            self.xvfb.kill()
            self.xvfb = subprocess.Popen(
                ["Xvfb", f":{self.display_port}", "-ac", "-maxclients", "2048"])
        # ops = FirefoxOptions()
        # profile = FirefoxProfile()
        # profile.set_preference("app.update.auto", "false")
        # profile.set_preference("app.update.enabled", "false")

        try:
            logging.info(f"[{self.thread_id}]: start launching")
            # os.environ['FIREFOX_ERROR'] = self.firefox_error
            # os.environ['MOZ_DISABLE_CONTENT_SANDBOX'] = '1'

            # 确保 self.profile_path 存在
            # print(self.profile_path)
            if not os.path.exists(self.profile_path):
                print(self.profile_path)
                os.makedirs(self.profile_path)

            # 在 self.tmp_dir 内创建一个临时子目录来存放 profile
            temp_profile_dir = self.profile_path

            # 使用该目录创建 FirefoxProfile 对象
            profile = FirefoxProfile(temp_profile_dir)
            profile.set_preference("app.update.auto", False)
            profile.set_preference("app.update.enabled", False)
            profile.set_preference("dom.report_all_js_exceptions", False)
            profile.set_preference("browser.tabs.crashReporting.includeURL", True)

            # 设置安全模式参数（等价于命令行 -safe-mode）
            profile.set_preference("toolkit.startup.max_resumed_crashes", -1)  # 绕过安全模式弹窗
            profile.set_preference("browser.safemode", True)                   # 启用安全模式
            

            profile.update_preferences()

            # 将创建的 profile 赋值给 FirefoxOptions 对象
            ops = webdriver.FirefoxOptions()
            ops.profile = profile
            ops.binary_location = self.firefox_path 
            ops.log.level = "trace"
            ops.page_load_strategy = 'eager'  # 不等待所有资源加载

            

            if self.use_xvfb:
                temp_lock = Lock()
                with temp_lock:
                    os.environ["DISPLAY"] = f":{self.display_port}"

            # self.browser = Firefox(firefox_binary=self.firefox_path,
            #                        executable_path=self.firefox_driver_path,
            #                        service_log_path=self.msg_path,
            #                        options=ops)

            if os.path.exists(self.msg_path):
                os.remove(self.msg_path)
            open(self.msg_path, 'w').close()

            # 创建 Service 对象指定 geckodriver 路径和日志路径
            service = Service(executable_path=self.firefox_driver_path, log_output=self.msg_path)


            # 启动 Firefox 浏览器
            self.browser = webdriver.Firefox(service=service, options=ops)

            logging.info(f"[{self.thread_id}]: end launching")
            browser_pid = self.browser.service.process.pid
            logging.info(f"[{self.thread_id}]: firefox pid: {browser_pid}")
            # self.browser_process = psutil.Process(browser_pid)
            self.browser.set_page_load_timeout(self.timeout_sec)
            self.browser.command_executor.set_timeout(self.timeout_sec)
            self.browser.implicitly_wait(self.timeout_sec)

            # ops.add_argument("--headless")
            # ops.add_argument(f"--MOZ_LOG=ObserverService:5")
            # ops.add_argument(f"--MOZ_LOG_FILE={self.msg_path}")
            # ops.add_argument("--display=:"+ str(13+self.thread_id))
            # ops.add_argument("--new-tab")
            # ops.add_argument(f"--profile={self.profile_dir}")
            # ops.add_argument("--url=http://www.baidu.com")
            # ops.log.level = "trace"
            # ops.binary_location = self.firefox_path
            # os.environ['FIREFOX_ERROR'] = self.firefox_error
            # self.browser = webdriver.WebDriver(
            # executable_path=self.firefox_driver_path,
            # options=ops,
            # desired_capabilities=self.caps,
            # firefox_profile = FirefoxProfile(self.profile_dir),
            # service_log_path=self.msg_path)

            # logging.info(f"[{self.thread_id}]: end launching")
            # browser_pid = self.browser.service.process.pid
            # self.browser_process = psutil.Process(browser_pid)
            # logging.info(f"[{self.thread_id}]: firefox pid: {browser_pid}")
        except KeyboardInterrupt as e:
            logging.info(f"interrupted by user: {e}")
        except BaseException as e:
            logging.error(f"[{self.thread_id}]: cannot launch browser. {repr(e)}")
            # raise
            logging.error(f"[{self.thread_id}]: try again")
            # exit(1)
            self.launch_browser()

    # def close_browser(self):
    #     if self.seperate:
    #         firefox_pid = self.firefox.pid
    #         processes = psutil.Process(firefox_pid).children(recursive=True)
    #     driver_pid = self.browser.service.process.pid
    #     process = psutil.Process(driver_pid)
    #     child_procs = process.children(recursive=True)
    #     try:
    #         self.browser.quit()
    #         logging.info(f"[{self.thread_id}]: successfully quit")
    #     except BaseException as e:
    #         logging.info(f"[{self.thread_id}]: cannot normally quit. cause: {repr(e)}")
    #         os.kill(driver_pid, signal.SIGKILL)
    #     if self.seperate:
    #         logging.info(f"[{self.thread_id}]: try to kill firefox pid: {firefox_pid}")
    #         try:
    #             os.kill(firefox_pid, signal.SIGKILL)
    #             logging.info(f"[{self.thread_id}]: successfully kill firefox pid: {firefox_pid}")
    #         except BaseException as e:
    #             logging.info(
    #                 f"[{self.thread_id}]: cannot kill firefox pid :{firefox_pid}; cause: {repr(e)}")
    #         for pid in processes:
    #             logging.info(f"[{self.thread_id}]: try to kill pid: {pid.pid}")
    #             try:
    #                 os.kill(pid.pid, signal.SIGKILL)
    #                 logging.info(f"[{self.thread_id}]: successfully kill pid {pid.pid}")
    #             except BaseException as e:
    #                 logging.info(f"[{self.thread_id}]: cannot kill {pid.pid}; cause: {repr(e)}")
    #     for pid in child_procs:
    #         # logging.info(f"[{self.thread_id}]: try to kill pid: {pid.pid}")
    #         try:
    #             os.kill(pid.pid, signal.SIGKILL)
    #             # logging.info(f"[{self.thread_id}]: successfully kill pid {pid.pid}")
    #         except BaseException as e:
    #             # logging.info(f"[{self.thread_id}]: cannot kill {pid.pid}; cause: {repr(e)}")
    #             pass
    #     self.browser = None

    def close_browser(self):
        # 使用 pgrep 获取所有 firefox 进程的 PID
        def get_firefox_processes():
            try:
                current_pid = self.browser.service.process.pid
                current_process = psutil.Process(current_pid)
                descendants = current_process.children(recursive=True)
                descendant_pids = {proc.pid for proc in descendants}

                # 执行 pgrep 命令，获取所有 firefox 进程的 PID
                result = subprocess.run(['pgrep', 'firefox'], capture_output=True, text=True, check=True)
                # 结果是一个字符串，每个 PID 在一行
                browser_pids = result.stdout.splitlines()
                # logging.error(f"[{self.thread_id}]: {browser_pids}")

                browser_pids = [int(pid) for pid in browser_pids if int(pid) in descendant_pids]
                browser_pids.append(current_pid)
                # logging.error(f"[{self.thread_id}]: {browser_pids}")
                
                return browser_pids
            except subprocess.CalledProcessError:
                print("No firefox processes found.")
                return []

        # 获取所有 firefox 进程的 PID
        firefox_pids = get_firefox_processes()

        # for pid in child_procs:
        for pid in firefox_pids:
            logging.info(f"[{self.thread_id}]: try to kill pid: {int(pid)}")
            try:
                os.kill(int(pid), signal.SIGKILL)
                logging.info(f"[{self.thread_id}]: successfully kill pid {int(pid)}")
            except ProcessLookupError as e:
                pass
            except BaseException as e:
                logging.info(f"[{self.thread_id}]: cannot kill {int(pid)}; cause: {repr(e)}")
        self.browser = None

    def close_all_tabs(self):
        try:
            handles = self.browser.window_handles
            if len(handles) == 1:
                return
            handle_0 = handles[0]
            for handle in handles:
                if handle_0 != handle:
                    self.browser.switch_to.window(handle)
                    # self.browser.close()
                    self.close_browser_with_timeout(self.browser)
                    if len(self.browser.window_handles) == 1:
                        break
            handle_0 = self.browser.window_handles[0]
            self.browser.switch_to.window(handle_0)
        except BaseException as e:
            raise
    
    def close_browser_with_timeout(self, driver, timeout=5):
        """
        尝试在指定的超时内关闭浏览器。
        :param driver: Selenium WebDriver 实例
        :param timeout: 超时时间，单位为秒，默认是 5 秒
        :return: None
        """
        def close_browser(driver):
            try:
                driver.close()
            except Exception as e:
                print(f"Error occurred while closing the browser: {e}")
                raise e

        # 使用 concurrent.futures 管理超时
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(close_browser, driver)

            try:
                # 设置超时时间
                future.result(timeout=timeout)  # 如果在指定的超时内没有关闭，抛出 TimeoutError
                print("浏览器已成功关闭")
                return True
            except concurrent.futures.TimeoutError:
                print(f"超时：浏览器未能及时关闭")
                # 这里可以进行清理工作，如强制退出进程等
                self.close_browser()
                self.launch_browser()
                # raise TimeoutError("浏览器关闭操作超时")

    def check_crash(self):
        logs = self.get_log()
        if "crash" in logs.lower():
            # print("检测到崩溃日志：", logs)
            return True

    def new_page(self):
        try:
            self.close_all_tabs()
            self.browser.switch_to.window(self.browser.window_handles[0])
            self.browser.execute_script("window.open('', '_blank');")
            self.browser.switch_to.window(self.browser.window_handles[1])
        except UnexpectedAlertPresentException as e:
            logging.info(f"[{self.thread_id}]: {repr(e)}!")
            self.browser.switch_to.alert.accept()
            return True
        except BaseException as e:
            logging.error(
                f"[{self.thread_id}]: cannot create a new page, try to restart the browser. reason: {repr(e)}")
            # logging.error(
            #     f"[{self.thread_id}]: {self.message()}"
            # )
            self.close_browser()
            self.launch_browser()
            self.new_page()

    def ready(self):
        if self.browser is None:
            self.launch_browser()
            self.new_page()
        else:
            try:
                self.browser.switch_to.alert.accept()
            except BaseException as e:
                pass
            try:
                r = random.random()
                if r < self.close_browser_prob:
                    logging.info(
                        f"restart browser because the random pick: {r} {self.close_browser_prob}")
                    self.close_browser()
                    self.launch_browser()
                self.new_page()
            except BaseException as e:
                logging.error(f"[{self.thread_id}]: cannot new a page. {repr(e)}")
                self.close_browser()
                self.launch_browser()
                self.new_page()

    def clone(self):
        cloned = copy.copy(self)
        cloned.browser = None
        return cloned

    def fuzz(self, path: str) -> bool:
        with open(path) as f:
            code = "\n".join(f.readlines())
        with open(path, 'w') as f:
            f.write(self.global_accessed_variables(code))

        path = "file://" + path
        try:
            self.browser.get(path)
            state = self.browser.execute_script("return 'I am ok!'")
            if state != 'I am ok!':
                print(f"sagem crash! I am bad...")
            return True
        except UnexpectedAlertPresentException as e:
            logging.info(f"[{self.thread_id}]: {repr(e)}!")
            try:
                self.browser.switch_to.alert.accept()
            except BaseException as e:
                logging.info(
                    f"[{self.thread_id}]: UnexpectedAlertPresentException, but cannot switch_to.alert {repr(e)}")
                # time.sleep(20)
                self.close_browser()
                self.launch_browser()
                self.new_page()
            return True
        except TimeoutException as e:
            logging.info(f"[{self.thread_id}]: timeout, {repr(e)}!")
            try:
                self.close_browser_with_timeout(self.browser)
            except BaseException as e:
                logging.info(
                    f"[{self.thread_id}]: timeout, but cannot close current window. {repr(e)}")
                # time.sleep(20)
                self.close_browser()
                self.launch_browser()
                self.new_page()
            return True
        except ReadTimeoutError as e:
            logging.info(f"[{self.thread_id}]: read timeout error, {repr(e)}!")
            try:
                self.close_browser_with_timeout(self.browser)
            except BaseException as e:
                logging.info(
                    f"[{self.thread_id}]: read timeout error, but cannot close current window. {repr(e)}")
                # time.sleep(20)
                self.close_browser()
                self.launch_browser()
                self.new_page()
            return True
        except BaseException as e:
            try:
                logging.info(f"[{self.thread_id}]: not finish, because: {repr(e)}")
                if 'JavascriptException' in str(repr(e)):
                    return 'JavascriptException'
                res = False # TimeoutException, ReadTimeoutError, InvalidSessionIdException，都有可能是tab crash。简直有毒。暂时排除纯html导致的timeout
                logging.info(f"[{self.thread_id}]: since we don't know how to catch a crash, so we save all the poc for double-check when exception occurs")
                # if 'WebDriverException' in str(repr(e)):
                #     res = False

                self.close_browser()
                self.launch_browser()
                self.new_page()
                logging.info(f"[{self.thread_id}]: browser can be closed!")
                return res

            except WebDriverException as e:
                self.close_browser()
                self.launch_browser()
                self.new_page()
                return False
                
            except BaseException as e:
                logging.info(f"[{self.thread_id}]: cannot close: {repr(e)}")
                # time.sleep(20)
                self.close_browser()
                self.launch_browser()
                self.new_page()
                return False

    def message(self) -> str:
        if self.termination_log:
            tmp = self.termination_log
            self.termination_log = None
            return tmp
        else:
            return self.get_log()

    def get_log(self) -> str:
        try:
            with open(self.msg_path, "r") as f:
                return f.read()
        except UnicodeDecodeError as e:
            return "fail to decode current file"
        except IOError as e:
            return f"[{self.thread_id}]: fail to open msg_path. {repr(e)}"

    def get_statement_valid_feedback(self) -> Optional[str]:
        try:
            feedback = self.browser.execute_script("if (typeof window.myFeedback === 'undefined') {window.myFeedback = [];} res = JSON.stringify(window.myFeedback); window.myFeedback = []; return res;")
            return feedback
        except BaseException as e:
            logging.info(f"get feed back failed: {str(repr(e))}")
            return None
    
    def get_valid_variables(self) -> Optional[str]:
        try:
            feedback = self.browser.execute_script("variables = []; for(var_name of Object.keys(window)){if (window[var_name] !== null){variables.push(var_name);}}; return JSON.stringify(variables);")
            # print(feedback)
            return eval(feedback)
        except BaseException as e:
            return []

    def execute_script(self, code):
        try:
            code = self.global_accessed_variables(code)
            feedback = self.browser.execute_script(code)

            state = self.browser.execute_script("return 'I am ok!'")
            if state != 'I am ok!':
                print(f"sagem crash! I am bad...")
            return True
        except UnexpectedAlertPresentException as e:
            logging.info(f"[{self.thread_id}]: {repr(e)}!")
            try:
                self.browser.switch_to.alert.accept()
            except BaseException as e:
                logging.info(
                    f"[{self.thread_id}]: UnexpectedAlertPresentException, but cannot switch_to.alert {repr(e)}")
                # time.sleep(20)
                self.close_browser()
                self.launch_browser()
                self.new_page()
            return True
        # except TimeoutException as e:
        #     logging.info(f"[{self.thread_id}]: timeout, {repr(e)}!")
        #     try:
        #         self.close_browser_with_timeout(self.browser)
        #     except BaseException as e:
        #         logging.info(
        #             f"[{self.thread_id}]: timeout, but cannot close current window. {repr(e)}")
        #         # time.sleep(20)
        #         self.close_browser()
        #         self.launch_browser()
        #         self.new_page()
        #     return True
        # except ReadTimeoutError as e:
        #     logging.info(f"[{self.thread_id}]: read timeout error, {repr(e)}!")
        #     try:
        #         self.close_browser_with_timeout(self.browser)
        #     except BaseException as e:
        #         logging.info(
        #             f"[{self.thread_id}]: read timeout error, but cannot close current window. {repr(e)}")
        #         # time.sleep(20)
        #         self.close_browser()
        #         self.launch_browser()
        #         self.new_page()
        #     return True
        except BaseException as e:
            try:
                logging.info(f"[{self.thread_id}]: not finish, because: {repr(e)}")
                if 'JavascriptException' in str(repr(e)):
                    return 'JavascriptException'
                res = False # TimeoutException, ReadTimeoutError, InvalidSessionIdException，都有可能是tab crash。简直有毒
                logging.info(f"[{self.thread_id}]: since we don't know how to catch a crash, so we save all the poc for double-check when exception occurs")
                # if 'WebDriverException' in str(repr(e)):
                #     res = False

                self.close_browser()
                self.launch_browser()
                self.new_page()
                logging.info(f"[{self.thread_id}]: browser can be closed!")
                return res

            except WebDriverException as e:
                self.close_browser()
                self.launch_browser()
                self.new_page()
                return False
                
            except BaseException as e:
                logging.info(f"[{self.thread_id}]: cannot close: {repr(e)}")
                # time.sleep(20)
                self.close_browser()
                self.launch_browser()
                self.new_page()
                return False