import config
import os
import logging
import signal
from typing import Optional
import re


def create_output_directory(path):
    # path = os.environ.get("OUTPUT_PATH")
    # if path is None:
    #     logging.error(f"doesn't have OUTPUT_PATH env var")
    #     exit()
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


class Timeout:
    def __init__(self, seconds=1, error_message='Timeout'):
        self.seconds = seconds
        self.error_message = error_message

    def handle_timeout(self, signum, frame):
        raise TimeoutError(self.error_message)

    def __enter__(self):
        signal.signal(signal.SIGALRM, self.handle_timeout)
        signal.alarm(self.seconds)

    def __exit__(self, type, value, traceback):
        signal.alarm(0)


class FuzzedBrowser(object):
    def ready(self):
        pass

    def clone(self):
        pass

    def fuzz(self, path: str) -> bool:
        pass

    def message(self) -> str:
        pass

    def get_statement_valid_feedback(self) -> Optional[str]:
        pass

    def get_valid_variables(self) -> Optional[str]:
        pass
    
    def execute_script(self, code):
        pass

    def global_accessed_variables(self, code):
        # 定义匹配变量名的正则表达式：
        #   \b 确保变量名完整
        #   (var\d+|htmlvar\d+|svgvar\d+) 捕获三种符合条件的变量
        var_pattern = r'\b(var\d+|htmlvar\d+|svgvar\d+)\b'

        # 定义匹配包含 try{...}catch(e){...} 的模式（注意：假设代码片段均在一行内）
        trycatch_pattern = r'try\s*{.*?catch\s*\(e\)\s*{'

        # 按行处理字符串，只处理包含 try{...}catch(e){...} 的代码行
        result_lines = []
        for line in code.split('\n'):
            if re.search(trycatch_pattern, line):
                # 对符合条件的行进行替换，将匹配到的变量前加 window.
                new_line = re.sub(var_pattern, r'window.\1', line)
                result_lines.append(new_line)
            else:
                result_lines.append(line)

        new_code = "\n".join(result_lines)
        return new_code


class CrashVerifier(object):

    def verify(self, binary_location, path):
        pass