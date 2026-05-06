from selenium.common.exceptions import WebDriverException
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.webkitgtk.options import Options
from selenium.webdriver.webkitgtk.service import Service
from selenium.webdriver.webkitgtk.webdriver import WebDriver as WebKitGTK
import time
import sys
import re
import os
from common import CrashVerifier
import logging


class WebkitCrashVerifier(CrashVerifier):

    def verify(self, path, binary_location=None):

        matches = []
        try:
            os.environ["WEBKIT_DISABLE_SANDBOX"] = "1"
            webkit_driver_path = binary_location if binary_location else os.environ["WEBKIT_WEBDRIVER_PATH"]

            option = Options()
            option.add_argument("--automation")
            option.add_argument("-f")
            option.set_capability("pageLoadStrategy", "normal")  # 可选："normal", "eager", "none"

            if "WEBKIT_BINARY_PATH" in os.environ:
                option.binary_location = os.environ["WEBKIT_BINARY_PATH"]
            else:
                logging.error(f"didn't set WEBKIT_BINARY_PATH env var")
                exit(1)


            log_path = path+".log"
            if os.path.exists(log_path):
                os.remove(log_path)
            open(log_path, 'w').close()

            # 设置全局环境变量（关键步骤）
            os.environ.update({
                "WEBKIT_DEBUG": "errors",  # 仅记录错误级别的日志
                "G_MESSAGES_DEBUG": "WebKit:3",  # 限制 WebKit 模块的日志级别
                "WEBKIT_DISABLE_SANDBOX": "1"  # 禁用沙盒模式，避免权限问题
            })

            # 创建 Service 对象指定 geckodriver 路径和日志路径
            service = Service(executable_path=webkit_driver_path, log_output=log_path)


            browser = WebKitGTK(
                service=service, options=option
                # desired_capabilities=caps,
                # service_log_path=msg_path
                )
            

            browser.set_page_load_timeout(100)
            browser.command_executor.set_timeout(100)

            # 设置窗口大小和位置
            browser.set_window_size(1024, 768)
            browser.set_window_position(100, 100)

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

            
            browser.get("file:///" + newpath)

        except BaseException as e:
            print(f"not finish, because: {repr(e)}")
            if 'JavascriptException' in str(repr(e)):
                pass
            if 'WebDriverException' in str(repr(e)):
                print(f"sagem crash! WebDriverException: {repr(e)}")
                return True

            return False

        for idx, code in enumerate(matches, 1):
            try:
                print(idx)
                browser.execute_script(code)

            except BaseException as e:
                print(f"not finish, because: {repr(e)}")
                if 'JavascriptException' in str(repr(e)):
                    pass
                if 'WebDriverException' in str(repr(e)):
                    print(f"sagem crash! WebDriverException: {repr(e)}")
                    return True

                return False
        
        return False
