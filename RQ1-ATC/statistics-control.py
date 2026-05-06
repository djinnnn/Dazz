import re
import argparse
from collections import defaultdict

# 预编译正则表达式
VAR_DECL_PATTERN = re.compile(r'^\s*(?:var|let|const)\s+([^=;]+)')
VAR_ASSIGN_PATTERN = re.compile(r'^\s*([a-zA-Z_$][\w$]*)\s*=[^=]')
VAR_USAGE_PATTERN = re.compile(r'\b([a-zA-Z_$][\w$]*)\b')

def calculate_median(numbers):
    if not numbers:
        return 0
    sorted_nums = sorted(numbers)
    n = len(sorted_nums)
    mid = n // 2
    return (sorted_nums[mid] + sorted_nums[-(mid+1)])/2 if n%2 ==0 else sorted_nums[mid]

class DisjointSet:
    __slots__ = ['parent', 'rank']
    def __init__(self):
        self.parent = {}
        self.rank = {}

    def find(self, x):
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 1
            return x
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x, y):
        root_x = self.find(x)
        root_y = self.find(y)
        if root_x == root_y:
            return
        if self.rank[root_x] < self.rank[root_y]:
            root_x, root_y = root_y, root_x
        self.parent[root_y] = root_x
        self.rank[root_x] += self.rank[root_y]

def process_log(log_data):
    code_snippets = []
    current_snippet = []
    for line in log_data.split('\n'):
        line = line.strip()
        if line.startswith('INFO:root:start processing feedback of HTML...'):
            if current_snippet:
                code_snippets.append(current_snippet)
                current_snippet = []
        elif line.startswith('INFO:root:process code:'):
            code = line.split('process code: ', 1)[1]
            current_snippet.append(code)
    if current_snippet:
        code_snippets.append(current_snippet)

    results = []
    for snippet in code_snippets:
        processed = [re.sub(r'/\*.*?\*/', '', line).strip() for line in snippet]
        processed = [re.sub(r'window\.(var\d+|htmlvar\d+|svgvar\d+)', r'\1', line) for line in processed]
        processed = [line for line in processed if line]
        total_lines = len(processed)

        # 变量声明和作用域分析
        var_decl_map = defaultdict(list)
        for line_num, line in enumerate(processed, 1):
            if decl_match := VAR_DECL_PATTERN.match(line):
                vars_part = decl_match.group(1)
                for var in re.split(r'\s*,\s*', vars_part):
                    var_name = var.split('=', 1)[0].strip()
                    var_decl_map[var_name].append(line_num)
            elif assign_match := VAR_ASSIGN_PATTERN.match(line):
                var_name = assign_match.group(1)
                var_decl_map[var_name].append(line_num)

        var_scopes = defaultdict(list)
        for var, decl_lines in var_decl_map.items():
            decl_lines.sort()
            for i, line in enumerate(decl_lines):
                end = decl_lines[i+1]-1 if i < len(decl_lines)-1 else total_lines
                var_scopes[var].append((line, end))

        # 变量使用分析
        var_instances = defaultdict(set)
        for line_num, line in enumerate(processed, 1):
            used_vars = set(VAR_USAGE_PATTERN.findall(line))
            for var in used_vars:
                if var not in var_scopes:
                    continue
                for decl_line, end_line in var_scopes[var]:
                    if decl_line <= line_num <= end_line:
                        var_instances[(var, decl_line)].add(line_num)
                        break

        # 合并集合
        dsu = DisjointSet()
        for s in var_instances.values():
            lines = sorted(s)
            root = lines[0]
            for line in lines[1:]:
                dsu.union(root, line)

        final_clusters = defaultdict(set)
        for line_num in range(1, total_lines+1):
            root = dsu.find(line_num)
            final_clusters[root].add(line_num)
        
        merged_sets = list(final_clusters.values())
        sizes = sorted([len(s) for s in merged_sets], reverse=True)
        
        # 计算Top 5指标
        top5_sizes = sizes[:1]
        top5_sum = sum(top5_sizes)
        top5_percentage = top5_sum / total_lines if total_lines > 0 else 0

        # 补全不足5个的情况
        if len(top5_sizes) < 5:
            top5_sizes += [0] * (5 - len(top5_sizes))

        stats = {
            "total_lines": total_lines,
            "top5_sizes": top5_sizes,
            "top5_sum": top5_sum,
            "top5_percentage": top5_percentage,
            "num_functions": len(merged_sets)
        }
        results.append(stats)

    # 汇总统计
    if not results:
        return defaultdict(float)
    
    # 计算Top 5各项平均值
    avg_top5 = [
        sum(r["top5_sizes"][i] for r in results)/len(results)
        for i in range(5)
    ]
    avg_top5_sum = sum(avg_top5)
    avg_top5_percentage = sum(r["top5_percentage"] for r in results)/len(results)

    return {
        "avg_code_lines": sum(r["total_lines"] for r in results)/len(results),
        "avg_top5_sizes": avg_top5,
        "avg_top5_sum": avg_top5_sum,
        "avg_top5_percentage": avg_top5_percentage,
        "avg_function_num": sum(r["num_functions"] for r in results)/len(results)
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Advanced Log Analyzer')
    parser.add_argument('--logfile', required=True, help='Path to log file')
    args = parser.parse_args()

    try:
        with open(args.logfile, 'r', encoding='utf-8') as f:
            log_content = f.read()
    except Exception as e:
        print(f"Error: {str(e)}")
        exit(1)

    stats = process_log(log_content)
    print("\nBasic Statistics:")
    print(f"Average code lines: {stats['avg_code_lines']:.2f}")
    print(f"Average function clusters: {stats['avg_function_num']:.2f}")
    
    print("\nTop 5 Cluster Analysis:")
    for i, size in enumerate(stats['avg_top5_sizes'], 1):
        print(f"Top {i} avg size: {size:.2f}")
    print(f"Top 5 total avg size: {stats['avg_top5_sum']:.2f}")
    print(f"Top 5 avg percentage: {(stats['avg_top5_sum']/stats['avg_code_lines']):.2%}")