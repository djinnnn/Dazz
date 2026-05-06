from selenium.common.exceptions import WebDriverException
from selenium.common.exceptions import TimeoutException
from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.chrome.service import Service
import time
import sys
import re
import os
from common import CrashVerifier



class ChromeCrashVerifier(CrashVerifier):

    def verify(self, path, binary_location=None):

        matches = []
        try:
            ops = ChromeOptions()
            # ops.binary_location = "/opt/google/chrome/chrome"
            ops.binary_location = binary_location if binary_location else os.environ["CHROMIUM_PATH"]
            ops.add_argument("--no-sandbox")
            ops.add_argument("--disable-setuid-sandbox")
            ops.add_argument("--no-zygote")
            ops.add_argument("--disable-dev-shm-usage" ) 
            ops.set_capability("goog:loggingPrefs", {"browser": "ALL"})
            ops.add_argument("--enable-logging")
            ops.add_argument("--vebose") 

            print(path)
            print(ops.binary_location)
            
            log_path = os.path.dirname(path) + "/log"
            if os.path.exists(log_path):
                os.remove(log_path)
            open(log_path, 'w').close()

            service = Service(log_output=log_path)
            browser = Chrome(service=service, options=ops)
            browser.set_page_load_timeout(10)
            browser.command_executor.set_timeout(10)

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
            print(f"not finish, because: {repr(e)}, {type(repr(e))}")
            logs = ""
            with open(log_path) as f:
                logs = "".join(f.readlines())
            if "tab crashed" in logs:
                print(f"sagem crash! tab crashed")
                return True
            # time.sleep(5)
            # if 'JavascriptException' in str(repr(e)):
            #     print(f"sagem JavascriptException: {repr(e)}")
            if 'WebDriverException' in str(repr(e)):
                print(f"sagem crash! WebDriverException: {repr(e)}")
                sys.stdout.flush()
                return True
                # time.sleep(20)
            else:
                print(f"Other Exception: {repr(e)}")
            return False


        # print(html_content)
        for idx, code in enumerate(matches, 1):
            try:
                print(idx)
                browser.execute_script(code)

            except BaseException as e:
                print(f"not finish, because: {repr(e)}, {type(repr(e))}")
                logs = ""
                with open(log_path) as f:
                    logs = "".join(f.readlines())
                if "tab crashed" in logs:
                    print(f"sagem crash! tab crashed")
                    return True
                # time.sleep(5)
                if 'JavascriptException' in str(repr(e)):
                    # print(f"sagem JavascriptException: {repr(e)}")
                    continue
                if 'WebDriverException' in str(repr(e)):
                    print(f"sagem crash! WebDriverException: {repr(e)}")
                    sys.stdout.flush()
                    return True
                return False
            
        # time.sleep(20)
        
        return False
