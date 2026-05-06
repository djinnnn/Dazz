from common import CrashVerifier
import logging
import sys
from browser_crash_verifiers.chromium import ChromeCrashVerifier
from browser_crash_verifiers.firefox import FirefoxCrashVerifier
from browser_crash_verifiers.webkit import WebkitCrashVerifier
from browser_crash_verifiers.safari import SafariCrashVerifier
import time
import os
import subprocess
import psutil
import signal
import glob

from config import get_verify_option


def get_verifier(threadId=0, browser_name="chromium") -> CrashVerifier:
    verifier = None
    if browser_name == "chromium":
        verifier = ChromeCrashVerifier()
    elif browser_name == "chrome":
        verifier = ChromeCrashVerifier()
    elif browser_name == 'firefox':
        verifier = FirefoxCrashVerifier()
    elif browser_name == "webkit":
        verifier = WebkitCrashVerifier()
    elif browser_name == "safari":
        verifier = SafariCrashVerifier()
    else:
        logging.error(f"[{threadId}]: invalid browser: {browser_name}")
        exit()

    assert verifier is not None
    return verifier


def close_browser(browser_name, browser_pids=None):
    # 使用 pgrep 获取所有 firefox 进程的 PID
    def get_browser_processes(browser_name, browser_pids=None):
        try:
            if not browser_pids:
                current_pid = os.getpid()
                current_process = psutil.Process(current_pid)
                descendants = current_process.children(recursive=True)
                descendant_pids = {proc.pid for proc in descendants}

                # 执行 pgrep 命令，获取所有 firefox 进程的 PID
                result = subprocess.run(['pgrep', browser_name], capture_output=True, text=True, check=True)
                # 结果是一个字符串，每个 PID 在一行
                browser_pids = result.stdout.splitlines()
                browser_pids = [int(pid) for pid in browser_pids if int(pid) in descendant_pids]
            # print(browser_pids)
            return browser_pids
        except subprocess.CalledProcessError:
            print(f"No {browser_name} processes found.")
            return []

    # 获取所有 firefox 进程的 PID
    if browser_name == "chromium":
        browser_name = "chrome"
    elif browser_name == "webkit":
        browser_name = "MiniBrowser"
    elif browser_name == "safari":
        browser_name = "Safari"
    browser_pids = get_browser_processes(browser_name)

    # for pid in child_procs:
    for pid in browser_pids:
        # print(f"try to kill pid: {int(pid)}")
        try:
            os.kill(int(pid), signal.SIGKILL)
            # print(f"successfully kill pid {int(pid)}")
        except ProcessLookupError as e:
            pass
        except BaseException as e:
            print(f"cannot kill {int(pid)}; cause: {repr(e)}")


def cleanup(output_path):
    # output_path = os.path.join(os.path.dirname(args['input']))
    # 构造文件匹配模式，用于查找所有包含 ".html.html" 的文件
    pattern = os.path.join(output_path, "*html.html")

    # 使用 glob 模块获取该目录下所有符合条件的文件列表
    files_to_delete = glob.glob(pattern)

    # 逐个删除匹配的文件
    for file in files_to_delete:
        try:
            os.remove(file)
            # print(f"已删除文件: {file}")
        except Exception as error:
            print(f"删除文件 {file} 时出错: {error}")

try:
    if __name__ == "__main__":

        ops = get_verify_option()
        path = ops['poc_path']
        browser = ops['browser']
        waittime = int(ops['waittime'])
        times = int(ops['number'])
        verifier = get_verifier(browser_name=browser)
        for _ in range(times):
            res = verifier.verify(path)
            # time.sleep(3)
            if res == True:
                print(f"{path} is a crash! wow sagem!")
                sys.stdout.flush()
                time.sleep(waittime)
                close_browser(browser)
                break
            time.sleep(waittime)
            close_browser(browser)
            cleanup(os.path.join(os.path.dirname(ops['poc_path'])))

except KeyboardInterrupt:
    cleanup(os.path.join(os.path.dirname(ops['poc_path'])))   
    sys.exit(0)