import logging
from neo4j import GraphDatabase
from config import settings

logger = logging.getLogger(__name__)

class Neo4jManager:
    def __init__(self):
        self.driver = None
        self.connect()

    def connect(self):
        """连接到 Neo4j 数据库并初始化约束"""
        try:
            self.driver = GraphDatabase.driver(
                settings.NEO4J_URI, 
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
            )
            
            self.driver.verify_connectivity()
            logger.info("✅ Neo4j 连接成功！")
            
            self.create_constraints()
            
        except Exception as e:
            logger.error(f"❌ Neo4j 连接失败: {e}")
            self.driver = None

    def close(self):
        """关闭驱动连接"""
        if self.driver:
            self.driver.close()

    def create_constraints(self):
        """创建唯一性约束和索引，保证Concept节点的name属性唯一，Chunk节点的content属性唯一"""
        if not self.driver:
            return
        
        try:
            with self.driver.session() as session:
                # 针对 Concept 创建约束 
                session.run("CREATE CONSTRAINT constraint_concept_name IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE")
                
                # 针对 Chunk 创建索引
                session.run("CREATE INDEX index_chunk_content IF NOT EXISTS FOR (c:Chunk) ON (c.content)")

                # 创建向量索引 (针对 Chunk 的 embedding 属性)
                # 注意: Neo4j 5.x 语法
                try:
                    # 检查索引是否存在 (简单检查，防止重复创建报错)
                    # 这里的维度必须与 settings.EMBEDDING_DIM 一致
                    vector_index_query = f"""
                    CREATE VECTOR INDEX chunk_embedding_index IF NOT EXISTS
                    FOR (c:Chunk) ON (c.embedding)
                    OPTIONS {{indexConfig: {{
                        `vector.dimensions`: {settings.EMBEDDING_DIM},
                        `vector.similarity_function`: 'cosine'
                    }}}}
                    """
                    session.run(vector_index_query)
                    logger.info("⚡ 向量索引 check/create 完成")
                except Exception as e:
                    logger.warning(f"⚠️ 创建向量索引时遇到问题 (如果是旧版本 Neo4j 请忽略): {e}")
            
            logger.info("⚡ Neo4j 索引/约束检查完毕")
        except Exception as e:
            logger.info(f"ℹ️ 尝试创建索引/约束: {e}")

    def save_triplets(self, triplets, source_id="unknown"):
        """
        高性能保存三元组：按关系类型分组 + UNWIND 批量写入
        :param triplets: List[Dict] [{"head":..., "relation":..., "tail":...}]
        :param source_id: 来源标识
        """
        if not self.driver or not triplets:
            return

        # 1. 内存分组
        grouped_data = {}
        for item in triplets:
            rel_type = item["relation"]
            safe_rel_type = "_".join(rel_type.split()).upper()
            if not safe_rel_type:
                safe_rel_type = "RELATED_TO"
                
            if safe_rel_type not in grouped_data:
                grouped_data[safe_rel_type] = []
            
            grouped_data[safe_rel_type].append({
                "h_name": item["head"],
                "t_name": item["tail"],
                "source": source_id
            })

        count = 0
        try:
            with self.driver.session() as session:
                # 使用事务写入
                with session.begin_transaction() as tx:
                    for rel_type, batch_data in grouped_data.items():
                        cypher = f"""
                        UNWIND $batch AS row
                        MERGE (h:Concept {{name: row.h_name}})
                        MERGE (t:Concept {{name: row.t_name}})
                        MERGE (h)-[r:`{rel_type}`]->(t)
                        SET r.source = row.source
                        """
                        tx.run(cypher, batch=batch_data)
                        count += len(batch_data)
                    
                    tx.commit()
            
            logger.info(f"💾 [Batch] 已向 Neo4j 存入 {count} 个关系 (Source: {source_id})")
            
        except Exception as e:
            logger.error(f"❌ 批量保存三元组失败: {e}")

    def save_chunks(self, chunks, source_id="unknown"):
        """
        高性能保存块：UNWIND 批量写入
        """
        if not self.driver or not chunks:
            return

        # 预处理
        batch_data = []
        for item in chunks:
            batch_data.append({
                "content": item["content"],
                "embedding": item.get("embedding", None), # 新增 embedding 字段
                "subject": item["subject"],
                "predicate": item.get("predicate", "HAS_MENTION"),
                "source": source_id
            })

        # 分组
        grouped_chunks = {}
        for item in batch_data:
            pred = "_".join(item["predicate"].split()).upper()
            if pred not in grouped_chunks:
                grouped_chunks[pred] = []
            grouped_chunks[pred].append(item)

        total = 0
        try:
            with self.driver.session() as session:
                with session.begin_transaction() as tx:
                    for pred, batch in grouped_chunks.items():
                        cypher = f"""
                        UNWIND $batch AS row
                        MERGE (s:Concept {{name: row.subject}})
                        CREATE (c:Chunk {{content: row.content, source: row.source}})
                        SET c.embedding = row.embedding  // 设置向量属性
                        CREATE (s)-[:`{pred}`]->(c)
                        """
                        tx.run(cypher, batch=batch)
                        total += len(batch)
                    tx.commit()
            
            logger.info(f"📄 [Batch] 已向 Neo4j 存入 {total} 个文本块节点")
            
        except Exception as e:
            logger.error(f"❌ 批量保存 Chunk 失败: {e}")

    def prune_source_data(self, source_id):
        """
        在写入新数据前，清理该 source_id 对应的旧数据（Chunk 和 关系）
        注意：不删除 Concept 节点，因为它们可能是公用的
        """
        if not self.driver or not source_id:
            return

        try:
            with self.driver.session() as session:
                # 1. 删除该来源的所有 Chunk 节点 (DETACH DELETE 会自动删除连接的关系)
                session.run("MATCH (c:Chunk {source: $source}) DETACH DELETE c", source=source_id)
                
                # 2. 删除该来源的所有关系 (也就是 Triplets 建立的关系)
                # 这里的逻辑是：删除属性 source = current_source 的所有边
                session.run("MATCH ()-[r]-() WHERE r.source = $source DELETE r", source=source_id)
                
            logger.info(f"🧹 已清理旧数据 (Source: {source_id})")
        except Exception as e:
            logger.error(f"❌ 清理旧数据失败: {e}")

    def get_source_hash(self, source_id):
        """获取指定源在数据库中存储的 Hash 版本"""
        if not self.driver or not source_id:
            return None
        try:
            with self.driver.session() as session:
                result = session.run(
                    "MATCH (m:SourceMetadata {id: $id}) RETURN m.hash AS hash LIMIT 1",
                    id=source_id
                ).single()
                return result["hash"] if result else None
        except Exception:
            return None

    def update_source_hash(self, source_id, new_hash):
        """更新源的 Hash 版本"""
        if not self.driver or not source_id:
            return
        try:
            with self.driver.session() as session:
                session.run(
                    "MERGE (m:SourceMetadata {id: $id}) SET m.hash = $hash",
                    id=source_id, hash=new_hash
                )
        except Exception as e:
            logger.error(f"❌ 更新元数据失败: {e}")

    def clear_database(self):
        """危险操作：清空数据库"""
        if self.driver:
            try:
                with self.driver.session() as session:
                    session.run("MATCH (n) DETACH DELETE n")
                logger.warning("⚠️ 数据库已清空！")
            except Exception as e:
                logger.error(f"清空失败: {e}")
