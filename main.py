import logging
import re
import signal
import threading
import os
import shutil
import json
import sys

import config
import common
from fuzzer import get_fuzzer, EvoGrammarFuzzer
from browser_selenium import get_browser
import time
from collections import defaultdict


class FastCodeUsageAnalyzer:
    def __init__(self):
        self.all_valid_code_lines = []
        self.max_group_vars = []
        self.is_initial = True
        self.known_variables = set()  # 用于快速查找已知变量

    def analyze_new_code(self, new_code_lines, valid_variables):
        processed_lines = self._preprocess_code(new_code_lines)
        self.all_valid_code_lines.extend(processed_lines)
        
        # 更新有效变量集合（合并新旧变量）
        current_valid_vars = set(valid_variables)
        self.known_variables.update(current_valid_vars)
        
        if self.is_initial:
            self._initial_analysis(processed_lines, current_valid_vars)
            self.is_initial = False
        else:
            self._dynamic_expansion_analysis(processed_lines, current_valid_vars)
        
        logging.info(f'after fast analyze_new_code: valid_variables = {len(self.max_group_vars)} / {len(valid_variables)}') 

        return self.max_group_vars

    def _initial_analysis(self, processed_lines, valid_vars):
        # 首次分析的原始逻辑
        var_line_indices = defaultdict(set)
        for var in valid_vars:
            pattern = re.compile(r'\b{}\b'.format(re.escape(var)))
            for line_idx, line in enumerate(processed_lines):
                if pattern.search(line):
                    var_line_indices[var].add(line_idx)
        
        # 分组和合并逻辑
        groups = []
        for var, lines in var_line_indices.items():
            if lines:
                groups.append({'vars': {var}, 'lines': lines})
        
        # 合并分组
        merged = True
        while merged:
            merged = False
            new_groups = []
            used = set()
            for i in range(len(groups)):
                if i not in used:
                    group = groups[i]
                    for j in range(i+1, len(groups)):
                        if j not in used and group['lines'].intersection(groups[j]['lines']):
                            group['vars'].update(groups[j]['vars'])
                            group['lines'].update(groups[j]['lines'])
                            used.add(j)
                            merged = True
                    new_groups.append(group)
                    used.add(i)
            groups = new_groups
        
        # 找到最大分组
        max_group = max(groups, key=lambda g: len(g['lines']), default=None)
        if max_group:
            self.max_group_vars = sorted(max_group['vars'])
            self.known_variables.update(self.max_group_vars)

    def _dynamic_expansion_analysis(self, processed_lines, valid_vars):
        current_max_vars = set(self.max_group_vars)
        valid_vars_set = valid_vars.intersection(self.known_variables)
        
        # 构建变量匹配模式
        var_pattern = re.compile(
            r'\b(' + '|'.join(map(re.escape, valid_vars_set)) + r')\b'
        ) if valid_vars_set else None
        
        changed = True
        while changed:
            changed = False
            for line in processed_lines:
                # 快速预筛选
                if not any(var in line for var in current_max_vars):
                    continue
                
                # 精确匹配
                if var_pattern:
                    found_vars = set(var_pattern.findall(line))
                    relevant_vars = found_vars & valid_vars_set
                    if relevant_vars & current_max_vars:
                        new_vars = relevant_vars - current_max_vars
                        if new_vars:
                            current_max_vars.update(new_vars)
                            changed = True
        
        self.max_group_vars = sorted(current_max_vars)
        self.known_variables.update(current_max_vars)

    def _preprocess_code(self, code_lines):
        # 优化后的预处理
        processed = []
        for line in code_lines:
            # 移除注释
            clean_line = re.sub(r'/\*.*?\*/', '', line).strip()
            # 简化window变量处理
            clean_line = re.sub(
                r'window\.(var\d+|htmlvar\d+|svgvar\d+)', 
                r'\1', 
                clean_line
            )
            if clean_line:
                processed.append(clean_line)
        return processed


class CodeUsageAnalyzer:
    def __init__(self):
        self.all_valid_code_lines = []  # 存储所有处理后的代码行
        self.var_line_indices = defaultdict(set)  # 变量到行索引的映射
        self.merged_groups = []  # 合并后的分组
        self.max_group_vars = []  # 最大分组的变量列表

    def analyze_new_code(self, new_code_lines, valid_variables):
        # 预处理新的代码行
        processed_lines = self._preprocess_code(new_code_lines)
        offset = len(self.all_valid_code_lines)
        
        # 更新变量行号映射
        valid_vars_set = set(valid_variables)
        if valid_variables:
            # 构建匹配所有有效变量的正则表达式
            pattern = re.compile(r'\b(' + '|'.join(map(re.escape, valid_variables)) + r')\b')
            for line_idx, line in enumerate(processed_lines):
                global_line_idx = offset + line_idx
                matches = pattern.findall(line)
                for var in set(matches):
                    if var in valid_vars_set:
                        self.var_line_indices[var].add(global_line_idx)
        
        # 将处理后的行添加到总列表中
        self.all_valid_code_lines.extend(processed_lines)
        
        # 生成初始分组
        groups = []
        for var, lines in self.var_line_indices.items():
            if lines:
                groups.append({'vars': {var}, 'lines': lines.copy()})
        
        # 合并有交集的分组
        i = 0
        while i < len(groups):
            j = i + 1
            merged = False
            while j < len(groups):
                if groups[i]['lines'].intersection(groups[j]['lines']):
                    groups[i]['vars'].update(groups[j]['vars'])
                    groups[i]['lines'].update(groups[j]['lines'])
                    del groups[j]
                    merged = True
                    i = 0  # 合并后重置索引，重新检查所有分组
                    break
                else:
                    j += 1
            if not merged:
                i += 1
        
        # 生成合并后的分组结果
        self.merged_groups = []
        for group in groups:
            sorted_line_indices = sorted(group['lines'])
            code_lines = [self.all_valid_code_lines[idx] for idx in sorted_line_indices]
            variables = sorted(group['vars'])
            self.merged_groups.append({'variables': variables, 'code_lines': code_lines})
        
        # 找出最大的分组
        max_size = -1
        max_group = []
        for group in self.merged_groups:
            if len(group['code_lines']) > max_size:
                max_size = len(group['code_lines'])
                max_group = group['variables']
        self.max_group_vars = max_group

        logging.info(f'after analyze_new_code: code block size = {max_size}/{len(self.all_valid_code_lines)}, valid_variables = {len(max_group)} / {len(valid_variables)}') 

        return self.max_group_vars

    def _preprocess_code(self, code_lines):
        # 去除注释
        no_comments = [re.sub(r'/\*.*?\*/', '', line).strip() for line in code_lines]
        # 替换window.变量
        replaced = [re.sub(r'window\.(var\d+|htmlvar\d+|svgvar\d+)', r'\1', line) for line in no_comments]
        # 过滤空行
        non_empty = [line for line in replaced if line]
        return non_empty


def check_if_semantic_error(s: str) -> bool:
    if 'Valid' == s: return False
    return True


def process_feedback(feedback, prefix=None):
    logging.info(f"start processing feedback of {prefix}...")
    total_num = 0
    error_num = 0
    valid_code = []
    for line in feedback:
        if not isinstance(line, list):
            continue
        if len(line) != 2:
            continue
        if "GetVariable" in line[0] or "SetVariable" in line[0]:
            continue
        error = check_if_semantic_error(line[1])
        if not error:
            # logging.info(f"process code: {line[0]}")
            valid_code.append(line[0])
        # logging.info(f"process code: {line[0]}, {line[1]}")
        total_num += 1
        error_num += 1 if error else 0
    if total_num != 0:
        logging.info(f"[{prefix}] error rate: {error_num / total_num} ({error_num}/{total_num}) ({time.time()})")
    
    return valid_code
    



class FuzzingLoop(threading.Thread):
    # class FuzzingLoop:
    def __init__(self, threadId, options):
        threading.Thread.__init__(self)
        self.threadId = threadId
        self.options = options
        self.exit_time = None
        if self.options["time_to_exit"]:
            self.exit_time = int(self.options["time_to_exit"]) * 3600
        self.execution_iteration = None
        if self.options["execution_iteration"]:
            self.execution_iteration = int(self.options["execution_iteration"])
        self.dir = os.path.join(self.options["output_dir"], f"thread-{threadId}")
        self.crash = os.path.join(self.dir, "crash")
        self.interesting = os.path.join(self.dir, "interesting")
        os.makedirs(self.dir, exist_ok=True)
        os.makedirs(self.crash, exist_ok=True)
        os.makedirs(self.interesting, exist_ok=True)

        self.print_time = False
        self.print_time_start = time.time()
        if "PRINT_TIME" in os.environ:
            self.print_time = os.environ["PRINT_TIME"] == "true"

    def move_to_crash(self, source_path, message, dest_path):
        shutil.copy(source_path, os.path.join(self.crash, dest_path))
        logging.info(f"shutil.copy({source_path}, {os.path.join(self.crash, dest_path)})")
        with open(os.path.join(self.crash, dest_path + ".log"), "w") as f:
            f.write(message)

    def move_to_interesting(self, source_path, dest_path):
        shutil.move(source_path, os.path.join(self.interesting, dest_path))

    def run(self):
        # with sync_playwright() as playwright:
        fuzzer = get_fuzzer('dazz++', self.threadId)
        # fuzzer = get_fuzzer(self.options["fuzzer"], self.threadId)
        browser = get_browser(self.threadId, self.options["browser"],
                              int(self.options["timeout"]))

        start_time = time.time()
        try:
            i = 0
            while True:
                if self.print_time:
                    self.print_time_start = time.time()

                path = fuzzer.generate_input()
                # codeUsageAnalyzer = CodeUsageAnalyzer()
                fast_codeUsageAnalyzer = FastCodeUsageAnalyzer()

                if self.print_time:
                    logging.info(f"html generation time: {time.time() - self.print_time_start} s")
                    self.print_time_start = time.time()
                browser.ready()
                if i % 10 == 0:
                    logging.info(f"[{self.threadId}]: iteration: {i}")

                if self.exit_time is not None:
                    if (time.time() - start_time) > self.exit_time:
                        return
                if self.execution_iteration is not None:
                    if i >= self.execution_iteration:
                        return

                logging.info(f"[{self.threadId}]: timestamp of the begin of iteration {i}: {int(time.time())}")
                self.print_time_start = time.time()
                # if i == 0, then we just omit it because we need a baseline coverage that exclude excution.
                if i != 0:
                    res = browser.fuzz(path)

                    if self.print_time:
                        logging.info(f"html execution time: {time.time() - self.print_time_start} s")
                        self.print_time_start = time.time()
                    # if res == "JavascriptException": exit()
                    if res == False:
                        message = browser.message()
                        self.move_to_crash(path, message, str(i) + ".html")
                        # logging.info(f"[{self.threadId}]: error message: \n{message}")
                    elif fuzzer.is_interesting():
                        self.move_to_interesting(path, str(i) + ".html")
                    else:  # normal execution
                        valid_variables = browser.get_valid_variables()
                        feed_back_str = browser.get_statement_valid_feedback()
                        if feed_back_str is not None and len(valid_variables) > 0:
                            feedback_raw = json.loads(feed_back_str)
                            new_code = process_feedback(feedback_raw, prefix="HTML")
                            valid_variables = fast_codeUsageAnalyzer.analyze_new_code(new_code, valid_variables)
                            # valid_variables = codeUsageAnalyzer.analyze_new_code(new_code, valid_variables)
                        # else: 
                        #     logging.info(f"feed_back_str is None, record the test case for further analysis...")
                        #     res = False

                        codes = []
                        crash = False
                        if not isinstance(fuzzer, EvoGrammarFuzzer): continue
                        jsexp_times = 0
                        for j in range(0, 20):
                            # logging.info(f"valid_variables: {valid_variables}")
                            if len(valid_variables) == 0:
                                break
                            # logging.info(len(valid_variables))
                            # logging.info(valid_variables)
                            if self.print_time:
                                self.print_time_start = time.time()

                            code = fuzzer.generate_code(valid_variables)
                            codes.append(code)

                            if self.print_time:
                                logging.info(f"js generation time: {time.time() - self.print_time_start} s")
                                self.print_time_start = time.time()

                            res = browser.execute_script(code)

                            if res == False:
                                with open(path, 'a') as f:
                                    j = 0
                                    for code in codes:
                                        f.write(f'<script>\nfunction rdfuzz{j + 1}(){{')
                                        code = browser.global_accessed_variables(code)
                                        f.write(code)
                                        f.write(f'}}\n')
                                        f.write(f'setTimeout(rdfuzz{j + 1}, {(j + 1) * 2000});\n')
                                        f.write(f'</script>\n')
                                        j += 1


                                message = browser.message()
                                self.move_to_crash(path, message, str(i) + ".html")

                                crash = True
                                break

                            if self.print_time:
                                logging.info(f"js execution time: {time.time() - self.print_time_start} s")
                                self.print_time_start = time.time()
                            # logging.info(f"[{self.threadId}]: timestamp after browser.execute_script(code) {j}: {int(time.time())}")

                            valid_variables = browser.get_valid_variables()
                            feed_back_str = browser.get_statement_valid_feedback()
                            if feed_back_str is not None and len(valid_variables) > 0:
                                feedback_raw = json.loads(feed_back_str)
                                new_code = process_feedback(feedback_raw, prefix=f"JavaScript {j}")
                                valid_variables = fast_codeUsageAnalyzer.analyze_new_code(new_code, valid_variables)
                                # valid_variables = codeUsageAnalyzer.analyze_new_code(new_code, valid_variables)


                logging.info(f"[{self.threadId}]: timestamp of the end of iteration {i}: {int(time.time())}")
                i += 1
        except KeyboardInterrupt as e:
            logging.info(f"exit the loop: thread id: {self.threadId}, event: {e}")
            return


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
