import os
from neo4j import GraphDatabase
from config import settings

def verify_data():
    driver = GraphDatabase.driver(
        settings.NEO4J_URI, 
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    
    output_file = "verification_results.txt"
    
    try:
        with driver.session() as session:
            # 1. 统计概况
            stats_query = """
            MATCH (c:Chunk)
            RETURN count(c) as total_chunks, 
                   count(c.embedding) as chunks_with_embedding
            """
            stats = session.run(stats_query).single()
            
            # 2. 获取有向量的节点样本
            sample_query = """
            MATCH (c:Chunk)
            WHERE c.embedding IS NOT INTERESTING AND c.embedding IS NOT NULL
            RETURN c.content AS content, 
                   size(c.embedding) AS emb_size,
                   c.source AS source
            LIMIT 3
            """
            # Note: IS NOT NULL is enough
            sample_query = """
            MATCH (c:Chunk)
            WHERE c.embedding IS NOT NULL
            RETURN c.content AS content, 
                   size(c.embedding) AS emb_size,
                   c.source AS source
            LIMIT 3
            """
            samples = session.run(sample_query)
            
            with open(output_file, "w", encoding="utf-8") as f:
                f.write("=== Neo4j 数据统计 ===\n")
                f.write(f"总 Chunk 节点数: {stats['total_chunks']}\n")
                f.write(f"拥有 embedding 属性的节点数: {stats['chunks_with_embedding']}\n")
                f.write(f"缺失 embedding 属性的节点数: {stats['total_chunks'] - stats['chunks_with_embedding']}\n\n")
                
                if stats['chunks_with_embedding'] > 0:
                    f.write("=== 成功存入向量的节点示例 ===\n")
                    for i, rec in enumerate(samples):
                        f.write(f"\n示例 {i+1}:\n")
                        f.write(f"来源: {rec['source']}\n")
                        f.write(f"内容预览: {rec['content'][:100]}...\n")
                        f.write(f"✅ 向量维度: {rec['emb_size']}\n")
                else:
                    f.write("❌ 警告：库中没有任何节点包含 embedding 属性。\n")
                
                f.write("\n=== 结论与建议 ===\n")
                if stats['total_chunks'] > stats['chunks_with_embedding']:
                    f.write("检测到库中存在冗余的、没有向量的老数据。\n")
                    f.write("原因：之前的运行由于代码未完成，产生了没有向量的节点；由于代码使用 CREATE 语句，重复运行会产生新节点而不会覆盖老节点。\n")
                    f.write("建议：你可以调用 neo4j_mgr.clear_database() 清空后重新运行 main.py，或者手动执行 Cypher: MATCH (c:Chunk) WHERE c.embedding IS NULL DETACH DELETE c\n")

        print(f"验证完成！详细报告已写入: {output_file}")
            
    except Exception as e:
        print(f"验证失败: {e}")
    finally:
        driver.close()

if __name__ == "__main__":
    verify_data()
