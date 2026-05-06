from selenium.webdriver.firefox.firefox_profile import FirefoxProfile
from selenium.webdriver.firefox.service import Service
from selenium import webdriver

import tempfile
import time
import sys
import re
import os
from common import CrashVerifier
import subprocess
import signal



class FirefoxCrashVerifier(CrashVerifier):

    def __init__(self):
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
    

    def new_page(self):
        try:
            self.close_all_tabs()
            self.browser.switch_to.window(self.browser.window_handles[0])
            self.browser.execute_script("window.open('', '_blank');")
            self.browser.switch_to.window(self.browser.window_handles[1])
        except UnexpectedAlertPresentException as e:
            print(f"{repr(e)}!")
            self.browser.switch_to.alert.accept()
            return True
        except BaseException as e:
            print(f"cannot create a new page, try to restart the browser. reason: {repr(e)}")


    def verify(self, path, binary_location=None):

        matches = []
        try:
            profile_path = os.path.dirname(path) + "/profile"
            if not os.path.exists(profile_path):
                print(profile_path)
                os.makedirs(profile_path)

            # 在 self.tmp_dir 内创建一个临时子目录来存放 profile
            temp_profile_dir = profile_path

            # 使用该目录创建 FirefoxProfile 对象
            profile = FirefoxProfile(temp_profile_dir)
            profile.set_preference("app.update.auto", False)
            profile.set_preference("app.update.enabled", False)
            profile.set_preference("accessibility.blockautorefresh", True)
            profile.set_preference("dom.report_all_js_exceptions", False)

            profile.update_preferences()

            # 将创建的 profile 赋值给 FirefoxOptions 对象
            ops = webdriver.FirefoxOptions()
            ops.profile = profile
            ops.binary_location = os.environ["FIREFOX_PATH"]
            ops.log.level = "trace"
            ops.page_load_strategy = 'eager'  # 不等待所有资源加载

            # 创建 Service 对象指定 geckodriver 路径和日志路径
            log_path = os.path.dirname(path) + "/log"
            if os.path.exists(log_path):
                os.remove(log_path)
            open(log_path, 'w').close()

            service = Service(executable_path=os.environ["FIREFOXDRIVER_PATH"], log_output=log_path)

            # 启动 Firefox 浏览器
            self.browser = webdriver.Firefox(service=service, options=ops)
            

            self.browser.set_page_load_timeout(2000)
            self.browser.command_executor.set_timeout(2000)
            self.browser.implicitly_wait(2000)

            html_content = ""
            with open(path) as f:
                html_content = "".join(f.readlines())

            # print(html_content)

            pattern = re.compile(r"<script>\n\s*function rdfuzz\d+\s*\([^)]*\)\s*\{([\s\S\n\{\}]*?)\}\n\s*setTimeout\(rdfuzz\d+, \d+\);\s*\n</script>", re.MULTILINE)
            matches = pattern.findall(html_content)
            print(len(matches))

            html_content = re.sub(pattern, "", html_content)
            newpath = path + '.html'
            with open(newpath, 'w') as f:
                f.write(html_content)

            self.browser.get("file:///" + newpath)
            self.browser.current_url
            state = self.browser.execute_script("return document.title")
            if len(self.browser.window_handles) == 0:
                print(f"sagem crash! there are no handles")
                return True
            
        except BaseException as e:
            # time.sleep(5)
            print(f"not finish, because: {repr(e)}, {type(repr(e))}")

            if 'WebDriverException' in str(repr(e)):
                print(f"sagem crash! WebDriverException: {repr(e)}")
                sys.stdout.flush()
                return True
                # time.sleep(20)
            return False

        for idx, code in enumerate(matches, 1):
            try:
                print(idx)
                # code = self.global_accessed_variables(code)
                self.browser.execute_script(code)
                self.browser.current_url
                if len(self.browser.window_handles) == 0:
                    print(f"sagem crash! there are no handles")
                    return True

                state = self.browser.execute_script("return document.title")
            
                if len(self.browser.window_handles) == 0:
                    print(f"sagem crash! there are no handles")
                    return True

            except BaseException as e:
                # time.sleep(5)
                print(f"not finish, because: {repr(e)}, {type(repr(e))}")

                if 'JavascriptException' in str(repr(e)):
                    # print(f"sagem JavascriptException: {repr(e)}")
                    continue
                if 'WebDriverException' in str(repr(e)):
                    print(f"sagem crash! WebDriverException: {repr(e)}")
                    sys.stdout.flush()
                    return True
                return False
            
        return False
