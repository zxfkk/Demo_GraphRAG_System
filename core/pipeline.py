import os
import logging
from config import settings
from core.extractor import extract_hybrid_data
from core.neo4j_manager import Neo4jManager

logger = logging.getLogger(__name__)

def run_graph_pipeline(notes_data, prompt_template):
    """
    执行图谱构建流水线：提取 -> 存入 Neo4j
    不再进行本地绘图
    """
    # 实例化 Neo4j 管理器
    neo4j_mgr = Neo4jManager()
    
    if not neo4j_mgr.graph:
        logger.error("❌ 无法连接到 Neo4j，流程终止。")
        return

    logger.info(f"🚀 开始构建知识图谱，共 {len(notes_data)} 篇笔记待处理...")

    for i, note_obj in enumerate(notes_data):
        # note_obj 是一个字典: {"filename": "...", "content": "..."}
        filename = note_obj.get('filename', f"note_{i}.md")
        note_content = note_obj.get('content', "")
        
        logger.info(f"[{i+1}/{len(notes_data)}] 正在分析: {filename} ...") 
        
        # 使用真实文件名生成 source_id (去掉 .md 后缀)
        base_name = os.path.splitext(filename)[0]
        # 再次确保文件名安全
        import re
        safe_name = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9_\-]', '_', base_name)
        source_id = f"note_{safe_name}"

        # 1. 提取三元组和块 (这里有缓存机制)
        triplets, chunks = extract_hybrid_data(note_content, prompt_template, source_id=source_id)
        
        # 2. 同步保存到 Neo4j
        logger.info(f"   └── 正在同步到 Neo4j (Source: {source_id}) ...")
        neo4j_mgr.save_triplets(triplets, source_id=source_id)
        neo4j_mgr.save_chunks(chunks, source_id=source_id)
        
    logger.info(f"✅ 所有笔记处理完成！")
