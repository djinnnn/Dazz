import argparse
import re

def process_log_file(filename):
    # 初始化HTML和JavaScript总的计数变量
    html_errors, html_total = 0, 0
    js_errors, js_total = 0, 0
    js_variants = {}

     # 用于存储执行和生成时间
    html_exec_times, html_gen_times = [], []
    js_exec_times, js_gen_times = [], []


    # 正则表达式
    error_pattern = re.compile(r"\((\d+)/(\d+)\)")
    js_variant_pattern = re.compile(r"\[JavaScript\s*(\d+)\]")
    exec_time_pattern = re.compile(r"(html|js) execution time:\s*([0-9.]+)\s*s", re.IGNORECASE)
    gen_time_pattern = re.compile(r"(html|js) generat(?:e|ion) time:\s*([0-9.]+)\s*s", re.IGNORECASE)

    with open(filename, "r") as f:
        for line in f:
            # 解析错误率行
            if "error rate:" in line:
                match = error_pattern.search(line)
                if match:
                    errors, total = map(int, match.groups())
                    if "[HTML]" in line:
                        html_errors += errors
                        html_total += total
                    elif "JavaScript" in line:
                        js_errors += errors
                        js_total += total
                        variant_match = js_variant_pattern.search(line)
                        if variant_match:
                            variant = variant_match.group(1)
                            if variant not in js_variants:
                                js_variants[variant] = [0, 0]
                            js_variants[variant][0] += errors
                            js_variants[variant][1] += total

            # 解析执行时间
            exec_match = exec_time_pattern.search(line)
            if exec_match:
                kind, time = exec_match.groups()
                time = float(time)
                if kind.lower() == 'html':
                    html_exec_times.append(time)
                else:
                    js_exec_times.append(time)

            # 解析生成时间（兼容 generate / generation）
            gen_match = gen_time_pattern.search(line)
            if gen_match:
                kind, time = gen_match.groups()
                time = float(time)
                if kind.lower() == 'html':
                    html_gen_times.append(time)
                else:
                    js_gen_times.append(time)

    # 计算正确率
    html_correct_rate = ((html_total - html_errors) / html_total) if html_total > 0 else None
    js_correct_rate = ((js_total - js_errors) / js_total) if js_total > 0 else None

    # 输出统计
    print("【总体统计】")
    if html_correct_rate is not None:
        print(f"HTML：初始代码正确率 = {html_correct_rate:.4f} ({html_total - html_errors}/{html_total})")
    else:
        print("没有 HTML 的数据。")
    
    if js_correct_rate is not None:
        print(f"JavaScript：优化代码正确率 = {js_correct_rate:.4f} ({js_total - js_errors}/{js_total})")
    else:
        print("没有 JavaScript 的数据。")
    
    if html_correct_rate and js_correct_rate:
        total_correct_rate = (html_total + js_total - html_errors - js_errors) / (html_total + js_total)
        print(f"整体代码正确率 = {total_correct_rate:.4f} ({html_total + js_total - html_errors - js_errors}/{html_total + js_total})")

    # 提升率
    if html_correct_rate and html_correct_rate > 0 and js_correct_rate is not None:
        improvement_ratio = js_correct_rate / html_correct_rate
        print(f"正确率提升率：{improvement_ratio:.4f} ({js_correct_rate:.4f}/{html_correct_rate:.4f})")

    # 平均时间
    def avg(lst):
        return sum(lst) / len(lst) if lst else 0.0

    print("\n【平均时间统计】")
    print(f"HTML 平均执行时间: {avg(html_exec_times):.4f} s")
    print(f"HTML 平均生成时间: {avg(html_gen_times):.4f} s")
    print(f"JavaScript 平均执行时间: {avg(js_exec_times):.4f} s")
    print(f"JavaScript 平均生成时间: {avg(js_gen_times):.4f} s")

    print("\n【各轮 JavaScript 统计】")
    for variant, (v_errors, v_total) in sorted(js_variants.items(), key=lambda x: int(x[0])):
        if v_total > 0:
            correct_rate = (v_total - v_errors) / v_total
            print(f"JavaScript {variant}：代码正确率 = {correct_rate:.4f} ({v_total - v_errors}/{v_total})")
        else:
            print(f"JavaScript {variant}：无数据。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="统计日志中 [HTML] 与 [JavaScript] 的错误率及平均时间")
    parser.add_argument("--logfile", type=str, required=True, help="日志文件的路径")
    args = parser.parse_args()
    process_log_file(args.logfile)
