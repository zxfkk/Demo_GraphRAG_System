import logging
from py2neo import Graph, Node, Relationship
from config import settings

logger = logging.getLogger(__name__)

class Neo4jManager:
    def __init__(self):
        self.graph = None
        self.connect()

    def connect(self):
        """连接到 Neo4j 数据库"""
        try:
            self.graph = Graph(
                settings.NEO4J_URI, 
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
            )
            # 测试连接
            self.graph.run("RETURN 1").evaluate()
            logger.info("✅ Neo4j 连接成功！")
        except Exception as e:
            logger.error(f"❌ Neo4j 连接失败: {e}")
            self.graph = None

    def save_triplets(self, triplets, source_id=None):
        """
        保存三元组到 Neo4j
        :param triplets: List[Dict] [{"head":..., "relation":..., "tail":...}]
        :param source_id: 来源标识 (如文件名)，可作为属性存入关系中
        """
        if not self.graph:
            logger.warning("Neo4j 未连接，跳过保存。")
            return

        tx = self.graph.begin()
        count = 0
        
        try:
            for item in triplets:
                # 1. 创建/匹配头节点
                head_node = Node("Concept", name=item["head"])
                tx.merge(head_node, "Concept", "name")
                
                # 2. 创建/匹配尾节点
                tail_node = Node("Concept", name=item["tail"])
                tx.merge(tail_node, "Concept", "name")
                
                # 3. 创建关系
                # 注意: Relationship 在 merge 时需要指定匹配规则，py2neo 的 merge 有点特殊
                # 这里我们简化逻辑：先查询是否存在关系，不存在则创建
                # 或者直接使用 merge (需要小心重复创建)
                
                # 更稳健的做法：使用 Cypher 语句，特别是对于关系
                # MERGE (h:Concept {name: $h_name})
                # MERGE (t:Concept {name: $t_name})
                # MERGE (h)-[r:RELATION {type: $rel_type}]->(t)
                
                # 为了简单和性能，我们用 Python 层的 merge 对象
                # py2neo 的 graph.merge 能处理节点，但处理带属性的动态关系比较麻烦
                # 我们这里构建一个简单的关系对象
                
                rel = Relationship(head_node, item["relation"], tail_node)
                if source_id:
                    rel["source"] = source_id
                
                tx.merge(rel, "Concept", "name") # 这一步其实是 merge 整个子图
                
                count += 1
            
            self.graph.commit(tx)
            logger.info(f"💾 已向 Neo4j 存入 {count} 个关系 (Source: {source_id})")
            
        except Exception as e:
            self.graph.rollback(tx)
            logger.error(f"❌ 保存三元组失败: {e}")

    def save_chunks(self, chunks, source_id=None):
        """
        保存文本块节点
        :param chunks: List[Dict]
        """
        if not self.graph:
            return

        tx = self.graph.begin()
        try:
            for item in chunks:
                # 创建 Chunk 节点
                # 属性包含全文，方便检索
                chunk_node = Node("Chunk", 
                                  content=item["content"],
                                  source=source_id or "unknown",
                                  predicate=item.get("predicate", "mention"))
                
                # 我们通常希望 Chunk 连接到一个实体，或者它自己就是个实体
                # 在 extract_hybrid_data 中: {"subject": "UE5", "predicate": "包含信息", "content": "..."}
                
                # 1. 确保 Subject 存在
                subj_node = Node("Concept", name=item["subject"])
                tx.merge(subj_node, "Concept", "name")
                
                # 2. 创建 Chunk 节点 (使用 content 的哈希作为唯一键可能更好，这里暂不设置主键)
                # 由于内容可能重复，我们暂时只是 create，或者根据内容 merge (如果内容太长作为 key 不太好)
                # 简单起见，我们 create，因为 chunk 通常是独特的
                tx.create(chunk_node)
                
                # 3. 建立连接 (Subject -> Chunk)
                rel = Relationship(subj_node, item["predicate"], chunk_node)
                tx.create(rel)
                
            self.graph.commit(tx)
            logger.info(f"📄 已向 Neo4j 存入 {len(chunks)} 个文本块节点")
            
        except Exception as e:
            self.graph.rollback(tx)
            logger.error(f"❌ 保存 Chunk 失败: {e}")

    def clear_database(self):
        """危险操作：清空数据库"""
        if self.graph:
            self.graph.delete_all()
            logger.warning("⚠️ 数据库已清空！")
