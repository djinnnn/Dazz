

import argparse
import re

def process_log_file(filename):
    types = set()
    pattern = re.compile(r'\((.*?)\)')
    with open(filename) as f:
        while True:
            line = f.readline()
            if not line: break
            if "Dazz++: type-related API" not in line: continue
            
            match = pattern.search(line)
            if match:
                # print(match.group(1))
                types.add(match.group(1))

    for t in types:
        # print(t)
        if t.endswith(args.search):
            print(f"'{t}',")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="统计日志中 Dazz++: type-related API 相关的type")
    parser.add_argument("--logfile", type=str, required=True, help="日志文件的路径")
    parser.add_argument("--search", type=str, required=True, help="感兴趣的字符串")
    args = parser.parse_args()
    
    process_log_file(args.logfile)
