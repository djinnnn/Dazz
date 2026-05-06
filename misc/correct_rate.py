import argparse
import re

def process_log_file(filename):
    # 初始化HTML和JavaScript总的计数变量
    html_errors, html_total = 0, 0
    js_errors, js_total = 0, 0
    # 用于存储每个 JavaScript 版本的错误数和总数，键为版本号
    js_variants = {}

    # 正则表达式匹配第一个括号内的数字，如 (276/518)
    pattern = re.compile(r"\((\d+)/(\d+)\)")
    # 正则表达式提取 [JavaScript X] 中的 X
    js_variant_pattern = re.compile(r"\[JavaScript\s*(\d+)\]")

    with open(filename, "r") as f:
        for line in f:
            if "error rate:" in line:
                match = pattern.search(line)
                if match:
                    errors, total = map(int, match.groups())
                    # 如果是 HTML 行
                    if "[HTML]" in line:
                        html_errors += errors
                        html_total += total
                    # 如果是 JavaScript 行
                    elif "JavaScript" in line:
                        js_errors += errors
                        js_total += total
                        # 提取版本号
                        variant_match = js_variant_pattern.search(line)
                        if variant_match:
                            variant = variant_match.group(1)
                            if variant not in js_variants:
                                js_variants[variant] = [0, 0]  # [错误数, 总数]
                            js_variants[variant][0] += errors
                            js_variants[variant][1] += total

    # 计算正确率
    if html_total > 0:
        html_correct_rate = (html_total - html_errors) / html_total
    else:
        html_correct_rate = None

    if js_total > 0:
        js_correct_rate = (js_total - js_errors) / js_total
    else:
        js_correct_rate = None

    print("【总体统计】")
    if html_correct_rate is not None:
        print(f"HTML：初始代码正确率 = {html_correct_rate:.4f} ({html_total - html_errors}/{html_total})")
    else:
        print("没有 HTML 的数据。")
    
    if js_correct_rate is not None:
        print(f"JavaScript：优化代码正确率 = {js_correct_rate:.4f} ({js_total - js_errors}/{js_total})")
    else:
        print("没有 JavaScript 的数据。")
    
    # 若 HTML 数据存在，则计算JavaScript相对于HTML的提升率
    if html_correct_rate and html_correct_rate > 0 and js_correct_rate is not None:
        improvement_ratio = js_correct_rate / html_correct_rate
        print(f"正确率提升率：{improvement_ratio:.4f} ({js_correct_rate:.4f}/{html_correct_rate:.4f})")
    
    print("\n【各轮 JavaScript 统计】")
    # 对字典按照版本号进行排序后输出
    for variant, (v_errors, v_total) in sorted(js_variants.items(), key=lambda x: int(x[0])):
        if v_total > 0:
            correct_rate = (v_total - v_errors) / v_total
            print(f"JavaScript {variant}：代码正确率 = {correct_rate:.4f} ({v_total - v_errors}/{v_total})")
        else:
            print(f"JavaScript {variant}：无数据。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="统计日志中 [HTML] 与 [JavaScript] 的错误率及各个 JavaScript 版本的正确率")
    parser.add_argument("--logfile", type=str, required=True, help="日志文件的路径")
    args = parser.parse_args()
    
    process_log_file(args.logfile)
