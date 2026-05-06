
from selenium import webdriver
import time
import sys
import re
import os
from common import CrashVerifier
import logging


class SafariCrashVerifier(CrashVerifier):

    def verify(self, path, binary_location=None):

        matches = []
        try:
            log_path = path+".log"
            if os.path.exists(log_path):
                os.remove(log_path)
            open(log_path, 'w').close()

            options = webdriver.SafariOptions()
            # 如果需要允许本地文件访问（避免安全限制）：
            options.set_capability('safari:allowFileAccessFromFileURLs', True)

            # 启动 Safari 驱动
            browser = webdriver.Safari(options=options)

            browser.set_page_load_timeout(30)
            browser.command_executor.set_timeout(30)

            html_content = ""
            with open(path) as f:
                html_content = "".join(f.readlines())

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
