import argparse
import subprocess
import re
import os
import shutil
import signal
import glob
import sys

from config import get_minimize_option

def run_crash_verify(browser, html_path):
    try:
        for _ in range(int(args['number'])):  # 进行3次验证
            result = subprocess.run(
                ["python3", "-u", "crash_verify.py", "-b", browser, "-i", html_path, "-n", args['number']],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            # print("stdout:", result.stdout)
            # print("stderr:", result.stderr)
            # 检查 stdout 和 stderr 中是否包含触发崩溃的关键字
            if "wow sagem" in result.stdout or "sagem crash" in result.stdout:
                return True  # 只要有一次触发崩溃，就返回 True
        return False  # 连续 3 次都未触发崩溃，才返回 False
    except Exception as e:
        print(f"Error running crash_verify.py: {e}")
        return False

def extract_fuzzers(html_content):
    css_match = re.search(r'/\*begincss\*/(.*?)/\*endcss\*/', html_content, re.DOTALL)
    html_match = re.search(r'<!--beginhtml-->(.*?)<!--endhtml-->', html_content, re.DOTALL)
    
    def extract_js_functions(content):
        js_functions = {}
        pattern = re.compile(r'function\s+(jsfuzzer\d*|eventhandler\d*|rdfuzz\d*)\(\)\s*{', re.DOTALL)
        for match in pattern.finditer(content):
            function_name = match.group(1)
            start = match.end()
            count = 1
            end = start
            while end < len(content) and count > 0:
                if content[end] == '{':
                    count += 1
                elif content[end] == '}':
                    count -= 1
                end += 1
            js_functions[function_name] = content[start:end-1].strip()
        return js_functions
    
    js_code_list = extract_js_functions(html_content)
    css_code = css_match.group(1) if css_match else ""
    html_code = html_match.group(1) if html_match else ""
    
    return css_code, html_code, js_code_list

def update_html(original_html, css_code, html_code, js_code_list):
    updated_html = re.sub(r'(/\*begincss\*/).*?(/\*endcss\*/)', 
                          lambda match: match.expand(r'\1') + css_code + match.expand(r'\2'), 
                          original_html, 
                          flags=re.DOTALL)
    
    updated_html = re.sub(r'(<!--beginhtml-->).*?(<!--endhtml-->)', 
                          lambda match: match.expand(r'\1') + html_code + match.expand(r'\2'), 
                          updated_html, 
                          flags=re.DOTALL)
    
    def extract_js_body(content, start):
        count = 1
        end = start
        while end < len(content) and count > 0:
            if content[end] == '{':
                count += 1
            elif content[end] == '}':
                count -= 1
            end += 1
        return content[start:end-1].strip()
    
    for function_name, function_body in js_code_list.items():
        pattern = re.compile(rf'function\s+{function_name}\(\)\s*{{', re.DOTALL)
        match = pattern.search(updated_html)
        if match:
            start = match.end()
            extracted_body = extract_js_body(updated_html, start)
            updated_html = updated_html[:start] + function_body + updated_html[start + len(extracted_body):]
    
    return updated_html

def recursive_minimize(browser, original_html, html_path, output_path, code, marker, css_code, html_code, js_code_list, js_index=None):
    if marker == "js" and js_index in args['bypass']: return code
    lines = code.split('\n')

    def get_temp_html(end, right_part):
        test_code = '\n'.join(lines[:end]) + "\n" + right_part  # 仅测试前半部分

        temp_js_code_list = dict(js_code_list)
        if marker == "js" and js_index is not None:
            temp_js_code_list[js_index] = test_code
        
        temp_html = update_html(original_html, 
                                test_code if marker == "css" else css_code,
                                test_code if marker == "html" else html_code,
                                temp_js_code_list)

        temp_path = html_path + ".tmp.html"
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(temp_html)
        
        return temp_path
    
    def minimize_range(start, end, right_part=""):
        # clear_browser(browser)
        print(f"Processing range: start={start}, end={end}")
        if start + 1 >= end:
            temp_path = get_temp_html(start, right_part)
            # if not run_crash_verify(browser, temp_path): # 不要start这一行如果就不行
            #     final_lines = '\n'.join(lines[start:end]) + "\n" + right_part
            # else: final_lines = right_part
            # print(f"Final lines: {final_lines}")
            if run_crash_verify(browser, temp_path): # 不要start这一行如果也可以
                final_lines = right_part
            else: 
                final_lines = '\n'.join(lines[start:end]) + "\n" + right_part
            print(f"Final lines: {final_lines}")
            return final_lines
        
        # 先看看全删了能不能行得通
        if start == 0:
            temp_path = get_temp_html(start, right_part)
            if run_crash_verify(browser, temp_path):
                return right_part
        
        # 不行就二分去找最下面一行right line
        mid = (start + end) // 2
        print(f"Midpoint: {mid}")
        print(f"Right Part: {right_part}")
       
        temp_path = get_temp_html(mid, right_part)
        if run_crash_verify(browser, temp_path):
            print(f"Range [{mid}, {end}] can be removed, proceeding with [{start}, {mid}]")
            shutil.move(temp_path, output_path)  # 直接更新 output_path
            return minimize_range(start, mid, right_part)  # 继续二分前半部分
        else:
            print(f"Range [{mid}, {end}] cannot be removed, processing recursively")
            temp_right_part = right_part
            right_part = minimize_range(mid, end, temp_right_part)  # 递归最小化右半部分

            # 找到一个新的关键行，就将其之前的所有部分合起来重新trim，会比递归倒回去要快（递归回去需要1，2，4，8慢慢倒回去）
            minimized_result = minimize_range(start, mid, right_part) # 组合两部分
            
            if marker == "js" and js_index is not None:
                js_code_list[js_index] = minimized_result
        
        return minimized_result
    
    # return minimize_range(0, len(lines), right_part= "for (let i = 0; i < 100000; i++) console.log(i);" if marker == "js" else "")
    return minimize_range(0, len(lines), right_part="")

def clear_browser(browser):
    clear_name = browser
    if browser == "chromium":
        clear_name = "chrome"
    elif browser == "firefox":
        clear_name = "firefox"
    
    try:
        # 执行 pgrep 命令，获取所有 chrome 进程的 PID
        result = subprocess.run(['pgrep', clear_name], capture_output=True, text=True, check=True)
        # 结果是一个字符串，每个 PID 在一行
        pids = result.stdout.splitlines()
    
        # for pid in child_procs:
        for pid in pids:
            print(f"try to kill pid: {int(pid)}")
            try:
                os.kill(int(pid), signal.SIGKILL)
                print(f"successfully kill pid {int(pid)}")
            except ProcessLookupError as e:
                pass
            except BaseException as e:
                print(f"cannot kill {int(pid)}; cause: {repr(e)}")
    except:
        pass


def minimize_and_update(browser, original_html, html_path, output_path, code, marker, css_code, html_code, js_code_list, js_index=None):
    minimized_code = recursive_minimize(browser, original_html, html_path, output_path, code, marker, css_code, html_code, js_code_list, js_index)
    
    if marker == "css":
        css_code = minimized_code
    elif marker == "html":
        html_code = minimized_code
    elif marker == "js" and js_index is not None:
        js_code_list[js_index] = minimized_code
    
    updated_html = update_html(original_html, css_code, html_code, js_code_list)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(updated_html)
    
    # clear_browser(browser)

    return updated_html, css_code, html_code, js_code_list

def minimize_html(browser, html_path, output_path):
    if run_crash_verify(browser, html_path) == False:
        print(f"Cannot reproduce the crash, exit...")
        return
    
    with open(html_path, "r", encoding="utf-8") as f:
        original_html = f.read()
    
    css_code, html_code, js_code_list = extract_fuzzers(original_html)

    for function_name in reversed(list(js_code_list.keys())):
        print(f"Start to minimize function: {function_name}...")
        js_code = js_code_list[function_name]
        original_html, css_code, html_code, js_code_list = minimize_and_update(browser, original_html, html_path, output_path, js_code, "js", css_code, html_code, js_code_list, function_name)
    
    print(f"Start to minimize html...")
    original_html, css_code, html_code, js_code_list = minimize_and_update(browser, original_html, html_path, output_path, html_code, "html", css_code, html_code, js_code_list)
    print(f"Start to minimize css...")
    original_html, css_code, html_code, js_code_list = minimize_and_update(browser, original_html, html_path, output_path, css_code, "css", css_code, html_code, js_code_list)

def cleanup(output_path):
    # output_path = os.path.join(os.path.dirname(args['input']))
    # 构造文件匹配模式，用于查找所有包含 ".html.html" 的文件
    pattern = os.path.join(output_path, "*tmp.html")

    # 使用 glob 模块获取该目录下所有符合条件的文件列表
    files_to_delete = glob.glob(pattern)

    # 逐个删除匹配的文件
    for file in files_to_delete:
        try:
            os.remove(file)
            # print(f"已删除文件: {file}")
        except Exception as error:
            print(f"删除文件 {file} 时出错: {error}")

def main():
    output = os.path.join(os.path.dirname(args['input']), "trimmed_" + os.path.basename(args['input']))

    minimize_html(args['browser'], args['input'], output)

try:
    if __name__ == "__main__":
        args = get_minimize_option()
        main()
        cleanup(os.path.join(os.path.dirname(args['input'])))
except KeyboardInterrupt:
    cleanup(os.path.join(os.path.dirname(args['input'])))
    sys.exit(0)