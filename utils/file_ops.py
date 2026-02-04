# utils/file_ops.py
import os
import yaml
import logging

def load_yaml_config(filepath):
    """加载 yaml 配置文件"""
    if not os.path.exists(filepath):
        # 尝试使用绝对路径或相对于当前文件的路径
        if not os.path.isabs(filepath):
             filepath = os.path.abspath(filepath)
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"配置文件 {filepath} 不存在")
            
    with open(filepath, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def load_file_content(filepath):
    """读取单个文本文件内容 (用于读取 Prompt)，返回字符串"""
    if not os.path.exists(filepath):
        logging.error(f"文件不存在: {filepath}")
        return ""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read().strip()

def load_all_markdown_files(directory):
    """
    读取指定目录下所有的 .md 文件内容
    返回: List[Dict], 每个元素形如 {"filename": "xxx.md", "content": "...", "filepath": "..."}
    """
    notes = []
    if not os.path.exists(directory):
        logging.warning(f"目录不存在: {directory}")
        return notes

    files = [f for f in os.listdir(directory) if f.endswith('.md')]
    logging.info(f"在 {directory} 中发现 {len(files)} 个 Markdown 文件")

    for filename in files:
        filepath = os.path.join(directory, filename)
        content = load_file_content(filepath)
        if content:
            # 返回结构化数据，保留文件名信息
            notes.append({
                "filename": filename,
                "filepath": filepath,
                "content": content
            })
            
    return notes
