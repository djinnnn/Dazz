#!/bin/bash

# —— 捕捉 Ctrl-C (SIGINT) 和 SIGTERM，转发给整个进程组并退出 —— 
trap 'echo "收到中断，正在退出…"; kill -- -$$; exit 1' INT TERM

# —— 环境变量 —— 
export SAGE_PATH=/home/sagem/Projects/SAGEM
export COLLECT_TREE_INFO=true                                  
export USE_INVALID_TREE=true
export PRINT_TIME=true
export INVALID_TREE_PATH="$SAGE_PATH/invalid_tree/invalid_tree.pickle"
export RULE_INFO_PATH="$SAGE_PATH/invalid_tree/global_info.pickle"

export FIREFOX_PATH=/home/sagem/.cache/ms-playwright/firefox-1475/firefox/firefox

export DOMATO_PATH=/home/sagem/Toolchains/domato/generator.py
export FREEDOM_PATH=/home/sagem/Toolchains/freedom/main.py 
export MINERVA_PATH=/home/sagem/Toolchains/Minerva/generator.py 
export MEM_DEP_JSON_PATH=/home/sagem/Toolchains/Minerva/mod_ref_helper/mem_dep.json  

# 设置标准输出为无缓冲模式
perl -e 'select STDOUT; $| = 1;'

# —— 解析参数 —— 
while getopts "f:o:" opt; do
    case $opt in
        f)
            fuzzer_name="$OPTARG"
            ;;
        o)
            outdir="$OPTARG"
            ;;
        \?)
            echo "Usage: $0 -f fuzzer_name -o outdir"
            exit 1
            ;;
    esac
done

# 检查必须的参数是否齐全
if [ -z "$fuzzer_name" ] || [ -z "$outdir" ]; then
    echo "Usage: $0 -f fuzzer_name -o outdir"
    exit 1
fi

# 如果输出目录不存在，则创建它
if [ ! -d "$outdir" ]; then
    mkdir -p "$outdir"
fi

fuzzer_stdout=$outdir/fuzzerlog

# —— 启动 fuzzer，并放到后台 —— 
timeout --foreground 24h python3 firefox_fuzzer.py -f "$fuzzer_name" -o "$outdir" -p 1 -t 10000 > $fuzzer_stdout 2>&1 &

# 保存子进程 PID
child=$!

# 等待子进程结束；在此期间按 Ctrl-C 会触发上面的 trap
wait $child