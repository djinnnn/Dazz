from common import FuzzedBrowser

import os
import random
import logging
import signal
import psutil
import copy
import concurrent.futures

from typing import List, Tuple, Optional

from selenium.webdriver.webkitgtk.options import Options
from selenium.webdriver.webkitgtk.service import Service
from selenium.webdriver.webkitgtk.webdriver import WebDriver as WebKitGTK
from selenium.common.exceptions import WebDriverException
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import UnexpectedAlertPresentException
from selenium.common.exceptions import NoAlertPresentException
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.utils import free_port
import subprocess


class WebKitSeleniumBrowser(FuzzedBrowser):
    def __init__(self, thread_id, timeout, port="gtk"):
        # 关闭 WebKitGTK 的 sandbox（注意：出于安全考虑，仅在调试或特定场景下使用）
        os.environ["WEBKIT_DISABLE_SANDBOX"] = "1"

        self.thread_id = thread_id
        self.timeout_sec = int(timeout) / 1000
        self.port = port
        self.browser = None
        self.tmp_dir = "/tmp/webkittmpdir" + str(self.thread_id) + "pid" + str(
            os.getpid()) + "rand" + str(random.random())
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.msg_path = self.tmp_dir + "/tmp_log"
        self.use_xvfb = True
        if "NO_XVFB" in os.environ:
            logging.info(f"[{self.thread_id}]: no xvfb")
            self.use_xvfb = False

        if self.use_xvfb:
            self.display_port = free_port()
            logging.info(f"[{self.thread_id}]: display port: {self.display_port}")
            self.xvfb = subprocess.Popen(
                ["Xvfb", f":{self.display_port}", "-ac", "-maxclients", "2048"])
        else:
            self.display_port = None
            self.xvfb = None

        # close the browser with this probability
        self.close_browser_prob = 0.01
        if "CLOSE_BROWSER_PROB" in os.environ:
            self.close_browser_prob = float(os.environ["CLOSE_BROWSER_PROB"])

        # configure for launching browser
        self.caps = DesiredCapabilities.WEBKITGTK.copy()
        self.caps["pageLoadStrategy"] = "normal"
        self.option = Options()
        self.option.add_argument("--automation")
        self.option.add_argument("-f")
        self.termination_log = None
        if "WEBKIT_WEBDRIVER_PATH" in os.environ:
            self.webkit_driver_path = os.environ["WEBKIT_WEBDRIVER_PATH"]
        else:
            logging.error(f"[{thread_id}]: didn't set WEBKIT_WEBDRIVER_PATH env var")
            exit(1)
        if "WEBKIT_BINARY_PATH" in os.environ:
            self.option.binary_location = os.environ["WEBKIT_BINARY_PATH"]
        else:
            logging.error(f"[{thread_id}]: didn't set WEBKIT_BINARY_PATH env var")
            exit(1)
        os.environ["FUZZER_TMP_PATH"] = self.msg_path
        self.launch_browser()

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
        logging.info(f"[{self.thread_id}]: start launching")
        if self.use_xvfb and self.xvfb.poll() is not None:
            logging.info(f"[{self.thread_id}]: xvfb has been kill. port: {self.display_port}")
            self.xvfb.kill()
            self.xvfb = subprocess.Popen(
                ["Xvfb", f":{self.display_port}", "-ac", "-maxclients", "2048"])
        try:
            if self.xvfb:
                # it's very very dangerous, but I can't find a better way
                # because selenium didn't export an API for setting env var
                os.environ["DISPLAY"] = f":{self.display_port}"
            
            if os.path.exists(self.msg_path):
                os.remove(self.msg_path)
            open(self.msg_path, 'w').close()

            # 设置全局环境变量（关键步骤）
            os.environ.update({
                "WEBKIT_DEBUG": "errors",  # 仅记录错误级别的日志
                "G_MESSAGES_DEBUG": "WebKit:3",  # 限制 WebKit 模块的日志级别
                "WEBKIT_DISABLE_SANDBOX": "1"  # 禁用沙盒模式，避免权限问题
            })

            # 创建 Service 对象指定 geckodriver 路径和日志路径
            service = Service(executable_path=self.webkit_driver_path, log_output=self.msg_path, env=os.environ.copy())


            self.browser = WebKitGTK(
                service=service, options=self.option
                # desired_capabilities=self.caps,
                # service_log_path=self.msg_path
                )
            self.browser.set_page_load_timeout(self.timeout_sec)
            self.browser.command_executor.set_timeout(self.timeout_sec)
            logging.info(f"[{self.thread_id}]: end launching")
            webdriver_pid = self.browser.service.process.pid
            logging.info(f"[{self.thread_id}]: webkit pid: {webdriver_pid}")
        except KeyboardInterrupt as e:
            logging.info(f"interrupted by user: {e}")
        except BaseException as e:
            logging.error(f"[{self.thread_id}]: cannot launch webkit browser. {repr(e)}")
            # raise
            logging.error(f"[{self.thread_id}]: try again")
            # exit(1)
            self.close_browser()
            self.launch_browser()

    def close_browser(self):
        if self.browser is None:
            return
        webdriver_pid = self.browser.service.process.pid
        process = psutil.Process(webdriver_pid)
        child_procs = process.children(recursive=True)
        try:
            self.browser.quit()
            logging.debug(f"[{self.thread_id}]: successfully quit")
        except BaseException as e:
            logging.debug(f"[{self.thread_id}]: cannot normally quit. cause: {repr(e)}")
        logging.debug(f"[{self.thread_id}]: try to kill webdriver pid: {webdriver_pid}")
        try:
            os.kill(webdriver_pid, signal.SIGKILL)
            logging.debug(f"[{self.thread_id}]: successfully kill webdriver pid: {webdriver_pid}")
        except ProcessLookupError as e:
            pass
        except BaseException as e:
            logging.error(
                f"[{self.thread_id}]: cannot kill webdriver pid :{webdriver_pid}; cause: {repr(e)}")
        for pid in child_procs:
            logging.debug(f"[{self.thread_id}]: try to kill pid: {pid.pid}")
            try:
                os.kill(pid.pid, signal.SIGKILL)
                logging.debug(f"[{self.thread_id}]: successfully kill pid {pid.pid}")
            except ProcessLookupError as e:
                pass
            except BaseException as e:
                logging.error(f"[{self.thread_id}]: cannot kill {pid.pid}; cause: {repr(e)}")
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
    
    def new_page(self):
        try:
            # handles = self.browser.window_handles
            # for handle in handles:
            #     if self.main_window != handle:
            #         self.browser.switch_to.window(handle)
            #         self.browser.close()
            # self.browser.switch_to.window(self.main_window)
            # self.browser.execute_script("window.open('','_blank');")
            self.close_all_tabs()
            self.browser.switch_to.window(self.browser.window_handles[0])
            self.browser.execute_script("window.open('','_blank');")
            self.browser.switch_to.window(self.browser.window_handles[1])
        except UnexpectedAlertPresentException as e:
            self.browser.switch_to.alert.accept()
            self.new_page()
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
                # self.new_page()
            except BaseException as e:
                logging.error(f"[{self.thread_id}]: cannot new a page. {repr(e)}")
                self.close_browser()
                self.launch_browser()
                # self.new_page()

    def clone(self):
        cloned = copy.copy(self)
        cloned.browser = None
        return cloned

    # Note: return true if the page does not crash
    def fuzz(self, path: str) -> bool:
        with open(path) as f:
            code = "\n".join(f.readlines())
        with open(path, 'w') as f:
            f.write(self.global_accessed_variables(code))

        path = "file://" + path
        try:
            self.browser.get(path)
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
            return True
        except BaseException as e:
            try:
                logging.info(f"[{self.thread_id}]: not finish, because: {repr(e)}")
                ret = True
                if 'JavascriptException' in str(repr(e)):
                    ret = 'JavascriptException'
                    return ret
                if 'WebDriverException' in str(repr(e)):
                    ret = False
                    
                self.close_browser()
                self.launch_browser()
        
                logging.info(f"[{self.thread_id}]: browser can be closed!")
                return ret

            except WebDriverException as e:
                logging.info(f"[{self.thread_id}]: cannot close: {repr(e)}")
                self.close_browser()
                self.launch_browser()
                return False
            except BaseException as e:
                logging.info(f"[{self.thread_id}]: cannot close: {repr(e)}")
                self.close_browser()
                self.launch_browser()
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

    def get_webdriver(self):
        return self.browser

    def get_statement_valid_feedback(self) -> Optional[str]:
        try:
            feedback = self.browser.execute_script("if (typeof myFeedback === 'undefined') {myFeedback = [];} res = JSON.stringify(myFeedback); myFeedback = []; return res;")
            return feedback
        except BaseException as e:
            return None
    
    def get_valid_variables(self) -> Optional[str]:
        try:
            feedback = self.browser.execute_script("variables = []; for(var_name of Object.keys(globalThis)){if (globalThis[var_name] !== null){variables.push(var_name);}}; return JSON.stringify(variables);")
            # logging.info(f"valid_variables.length = {len(eval(feedback))}")
            return eval(feedback)
        except BaseException as e:
            return []
    
    def execute_script(self, code):
        try:
            code = self.global_accessed_variables(code)
            feedback = self.browser.execute_script(code)
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
            return True
        except BaseException as e:
            try:
                logging.info(f"[{self.thread_id}]: not finish, because: {repr(e)}")
                ret = True
                if 'JavascriptException' in str(repr(e)):
                    ret = 'JavascriptException'
                    return ret
                if 'WebDriverException' in str(repr(e)):
                    ret = False
                    
                self.close_browser()
                self.launch_browser()
        
                logging.info(f"[{self.thread_id}]: browser can be closed!")
                return ret

            except WebDriverException as e:
                logging.info(f"[{self.thread_id}]: cannot close: {repr(e)}")
                self.close_browser()
                self.launch_browser()
                return False
            except BaseException as e:
                logging.info(f"[{self.thread_id}]: cannot close: {repr(e)}")
                self.close_browser()
                self.launch_browser()
                return False
