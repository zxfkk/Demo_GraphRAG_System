import logging
import sys
import os
import json
import time

# 确保项目根目录在 sys.path 中
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import settings
from core.query_engine import GraphRAGQuery

# 初始化日志
settings.setup_logging()
logger = logging.getLogger(__name__)

def save_log(filename, query, user_input, api_output):
    """追加写入日志"""
    log_entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "query": query,
        "input_to_api": user_input,
        "api_response": api_output
    }
    
    # 简单的追加模式：读取 -> append -> 写入
    # 注意：如果文件巨大，这种方式效率低，但用于测试足够了
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except:
            logs = []
    else:
        logs = []
        
    logs.append(log_entry)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

def main(): 
    print("🤖 欢迎使用 GraphRAG 问答系统 (对比模式)")
    print("输入 'exit' 或 'quit' 退出")
    print("-" * 50)
    
    rag = GraphRAGQuery()
    
    # 定义日志文件
    RAG_LOG_FILE = "rag_log.json"
    VANILLA_LOG_FILE = "vanilla_log.json"
    
    while True:
        try:
            query = input("\n👉 请提问: ").strip()
            if query.lower() in ["exit", "quit"]:
                print("👋 再见！")
                break
            
            if not query:
                continue
                
            print("\n⏳ [GraphRAG] 正在检索并生成回答...")
            rag_answer, rag_prompt = rag.query(query)
            print(f"\n📘 GraphRAG 回答:\n{rag_answer}\n")
            
            # 记录 GraphRAG 日志
            save_log(RAG_LOG_FILE, query, rag_prompt, rag_answer)
            print(f"✅ GraphRAG 日志已保存至 {RAG_LOG_FILE}")
            
            print("-" * 30)
            
            print("\n⏳ [Vanilla LLM] 正在直接询问大模型...")
            vanilla_answer, vanilla_prompt = rag.direct_chat(query)
            print(f"\n📙 Vanilla LLM 回答:\n{vanilla_answer}\n")
            
            # 记录 Vanilla 日志
            save_log(VANILLA_LOG_FILE, query, vanilla_prompt, vanilla_answer)
            print(f"✅ Vanilla 日志已保存至 {VANILLA_LOG_FILE}")
            
            print("-" * 50)
            
        except KeyboardInterrupt:
            print("\n👋 用户中断程序。")
            break
        except Exception as e:
            logger.error(f"发生错误: {e}")

if __name__ == "__main__":
    main()
