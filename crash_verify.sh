#!/bin/bash

# 设置标准输出为无缓冲模式
perl -e 'select STDOUT; $| = 1;'

# 使用 getopts 解析参数，添加 -o 参数
while getopts "b:i:o:" opt; do
    case $opt in
        b)
            browser_name="$OPTARG"
            ;;
        i)
            search_dir="$OPTARG"
            ;;
        o)
            outdir="$OPTARG"
            ;;
        \?)
            echo "Usage: $0 -b browser_name -i search_dir -o outdir"
            exit 1
            ;;
    esac
done

# 检查必须的参数是否齐全
if [ -z "$browser_name" ] || [ -z "$search_dir" ] || [ -z "$outdir" ]; then
    echo "Usage: $0 -b browser_name -i search_dir -o outdir"
    exit 1
fi

# 检查搜索目录是否存在
if [ ! -d "$search_dir" ]; then
    echo "$search_dir is not a valid directory."
    exit 1
fi

# 如果输出目录不存在，则创建它
if [ ! -d "$outdir" ]; then
    mkdir -p "$outdir"
fi

# 递归查找所有 html 文件，使用 -print0 处理文件名中可能包含的空格
find "$search_dir" -type f -name "*.html" -print0 | while IFS= read -r -d '' file; do
    # 如果文件名中包含 ".html.html" 则跳过
    if [[ "$file" == *".html.html"* ]]; then
        echo "[SKIP] $file"
        continue
    fi
    echo "Processing $file ..."

    # 调用 python 脚本，并传递 -b 和 -i 参数（这里 -i 参数传入当前文件名）
    output=$(python3 crash_verify.py -b "$browser_name" -i "$file")
    echo "$output"
    
    # 判断输出中是否包含 "sagem crash"
    if echo "$output" | grep -q "sagem crash"; then
        echo "[CRASH] $file is a crash!"
        # 如果触发 crash，则将该 html 文件复制到 outdir 目录下
        cp "$file" "$outdir"
    else
        echo "[DEBUG] $file is not a crash..."
    fi


    # 获取文件的基本名称（去掉最后一个 .html 后缀）
    base=$(basename "$file" .html)
    # 获取所在目录
    dir=$(dirname "$file")
    # 删除所有匹配 [name].html* 的文件
    rm -f "$dir"/"$base".html*

done
