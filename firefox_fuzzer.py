# from playwright.sync_api import sync_playwright
import logging
import re
import signal
import threading
import os
import shutil
import json
import sys
import asyncio

import config
import common
from fuzzer import get_fuzzer, EvoGrammarFuzzer
from browser_adapters.firefox_playwright import FirefoxPlaywrightBrowser
import time


def check_if_semantic_error(s: str) -> bool:
    if 'Valid' == s: return False
    return True

def process_feedback(feedback, prefix=None):
    logging.info(f"start processing feedback of {prefix}...")
    total_num = 0
    error_num = 0
    for line in feedback:
        if not isinstance(line, list):
            continue
        if len(line) != 2:
            continue
        if "GetVariable" in line[0] or "SetVariable" in line[0]:
            continue
        error = check_if_semantic_error(line[1])
        total_num += 1
        error_num += 1 if error else 0
    if total_num != 0:
        logging.info(f"[{prefix}] error rate: {error_num / total_num} ({error_num}/{total_num}) ({time.time()})")
    

class AsyncFuzzingTask:
    def __init__(self, thread_id, options, fuzzer, browser):
        self.thread_id = thread_id
        self.options = options
        self.fuzzer = fuzzer
        self.browser = browser
        self.exit_time = None
        if self.options["time_to_exit"]:
            self.exit_time = int(self.options["time_to_exit"]) * 3600
        self.execution_iteration = None
        if self.options["execution_iteration"]:
            self.execution_iteration = int(self.options["execution_iteration"])
        self.dir = os.path.join(self.options["output_dir"], f"thread-{thread_id}")
        self.crash = os.path.join(self.dir, "crash")
        self.interesting = os.path.join(self.dir, "interesting")
        os.makedirs(self.dir, exist_ok=True)
        os.makedirs(self.crash, exist_ok=True)
        os.makedirs(self.interesting, exist_ok=True)
        self.print_time = False
        self.print_time_start = time.time()
        if "PRINT_TIME" in os.environ:
            self.print_time = os.environ["PRINT_TIME"] == "true"

    async def run(self):
        start_time = time.time()
        try:
            i = 0
            while True:
                if self.print_time:
                    self.print_time_start = time.time()

                path = self.fuzzer.generate_input()

                if self.print_time:
                    logging.info(f"html generation time: {time.time() - self.print_time_start} s")
                    self.print_time_start = time.time()
                
                await self.browser.ready()  # 异步调用
                
                if i % 10 == 0:
                    logging.info(f"[{self.thread_id}]: iteration: {i}")

                if self.exit_time is not None:
                    if (time.time() - start_time) > self.exit_time:
                        return
                if self.execution_iteration is not None:
                    if i >= self.execution_iteration:
                        return

                logging.info(f"[{self.thread_id}]: timestamp of the begin of iteration {i}: {int(time.time())}")
                self.print_time_start = time.time()
                
                if i != 0:
                    res = await self.browser.fuzz(path)  # 异步调用

                    if self.print_time:
                        logging.info(f"html execution time: {time.time() - self.print_time_start} s")
                        self.print_time_start = time.time()

                    if res == False:
                        message = self.browser.message()
                        self.move_to_crash(path, message, str(i) + ".html")
                    else:
                        feed_back_str = await self.browser.get_statement_valid_feedback()  # 异步调用
                        if feed_back_str is not None:
                            feedback_raw = json.loads(feed_back_str)
                            process_feedback(feedback_raw, prefix="HTML")

                        codes = []
                        crash = False
                        if not isinstance(self.fuzzer, EvoGrammarFuzzer): continue
                        for j in range(0, 20):
                            valid_variables = await self.browser.get_valid_variables()  # 异步调用
                            if len(valid_variables) == 0:
                                break
                            if self.print_time:
                                self.print_time_start = time.time()

                            code = self.fuzzer.generate_code(valid_variables)
                            codes.append(code)

                            if self.print_time:
                                logging.info(f"js generation time: {time.time() - self.print_time_start} s")
                                self.print_time_start = time.time()

                            res = await self.browser.execute_script(code)  # 异步调用

                            if self.print_time:
                                logging.info(f"js execution time: {time.time() - self.print_time_start} s")
                                self.print_time_start = time.time()

                            feed_back_str = await self.browser.get_statement_valid_feedback()  # 异步调用
                            if feed_back_str is not None:
                                feedback_raw = json.loads(feed_back_str)
                                process_feedback(feedback_raw, prefix=f"JavaScript {j}")

                            if not res:
                                with open(path, 'a') as f:
                                    for idx, code in enumerate(codes):
                                        f.write(f'<script>\nfunction rdfuzz{idx + 1}(){{')
                                        code = self.browser.global_accessed_variables(code)
                                        f.write(code)
                                        f.write(f'}}\n')
                                        f.write(f'setTimeout(rdfuzz{idx + 1}, {(idx + 1) * 2000});\n')
                                        f.write(f'</script>\n')

                                message = self.browser.message()
                                self.move_to_crash(path, message, str(i) + ".html")
                                crash = True
                                break

                logging.info(f"[{self.thread_id}]: timestamp of the end of iteration {i}: {int(time.time())}")
                i += 1
        except KeyboardInterrupt as e:
            logging.info(f"exit the loop: thread id: {self.thread_id}, event: {e}")
        finally:
            await self.browser.close_browser()  # 异步关闭

    def move_to_crash(self, source_path, message, dest_path):
        shutil.copy(source_path, os.path.join(self.crash, dest_path))
        logging.info(f"shutil.copy({source_path}, {os.path.join(self.crash, dest_path)})")
        with open(os.path.join(self.crash, dest_path + ".log"), "w") as f:
            f.write(message)

class FuzzingLoop(threading.Thread):
    def __init__(self, threadId, options):
        super().__init__()
        self.threadId = threadId
        self.options = options

    def run(self):
        # 每个线程创建独立的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        fuzzer = get_fuzzer(self.options["fuzzer"], self.threadId)
        browser = FirefoxPlaywrightBrowser(self.threadId, int(self.options["timeout"]))
        
        task = AsyncFuzzingTask(
            thread_id=self.threadId,
            options=self.options,
            fuzzer=fuzzer,
            browser=browser
        )
        
        try:
            loop.run_until_complete(task.run())
        finally:
            loop.close()

def main():
    logging.basicConfig(level=logging.INFO)
    options = config.get_main_option()
    common.create_output_directory(options["output_dir"])

    threads = []
    for i in range(int(options["parallel"])):
        thread = FuzzingLoop(i, options)
        thread.start()
        threads.append(thread)
    
    for t in threads:
        t.join()
    
    logging.info("normal exit the fuzzing")

if __name__ == '__main__':
    main()