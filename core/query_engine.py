import logging
import json
from openai import OpenAI
from config import settings
from core.neo4j_manager import Neo4jManager
from core.embedding import get_embedding

logger = logging.getLogger(__name__)

class GraphRAGQuery:
    def __init__(self):
        self.neo4j = Neo4jManager()
        self.llm_client = OpenAI(api_key=settings.API_KEY, base_url=settings.BASE_URL)
        
    def query(self, user_query, top_k=5):
        """
        执行完整的 RAG 检索与生成流程
        :param user_query: 用户问题
        :param top_k: 检索召回的 chunk 数量
        """
        if not user_query:
            return "❌ 问题不能为空"

        logger.info(f"🔎 收到查询: {user_query}")

        # 1. 问题向量化
        query_embedding = get_embedding(user_query)
        if not query_embedding:
            return "❌ 无法生成问题向量，请检查 Embedding 服务。", ""

        # 2. 混合检索（向量相似度 + 图谱关联）
        # 这一步通过 Neo4j 的向量索引查找相似 Chunk，并顺带把相关的 Concept 名字也查出来
        retrieved_info = self._vector_graph_search(query_embedding, top_k)
        
        if not retrieved_info:
            return "⚠️ 未在知识库中找到相关信息。", ""

        # 3. 构建上下文
        context_str = self._format_context(retrieved_info)
        
        # 4. 生成回答
        answer, full_prompt = self._generate_answer(user_query, context_str)
        
        return answer, full_prompt

    def direct_chat(self, user_query):
        """
        直接调用 LLM 进行问答（Vanilla RAG），用于对比
        """
        system_prompt = "你是一个智能助手。请直接回答用户的问题。"
        full_prompt = f"System: {system_prompt}\nUser: {user_query}"
        
        try:
            response = self.llm_client.chat.completions.create(
                model=settings.MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=settings.TEMPERATURE
            )
            return response.choices[0].message.content, full_prompt
        except Exception as e:
            return f"❌ 直接生成失败: {e}", full_prompt

    def _vector_graph_search(self, query_vec, top_k):
        """
        核心检索逻辑：
        1. 使用 vector index 找到最相似的 chunk
        2. 找到 chunk 所属的 subject (实体)
        3. 查找这些 subject 的其他关系作为补充（可选，暂时先只取 chunk 内容和 实体名）
        """
        if not self.neo4j.driver:
            return []

        # 注意：这里假设之前创建的索引名为 chunk_embedding_index
        # 使用 Neo4j 5.x 的 db.index.vector.queryNodes 过程
        cypher = f"""
        CALL db.index.vector.queryNodes('chunk_embedding_index', $top_k, $query_vec) 
        YIELD node AS chunk, score
        
        // 找到该 chunk 关联的实体（主语）
        OPTIONAL MATCH (s:Concept)-[:HAS_MENTION|DESCRIBES|RELATED_TO]->(chunk)
        
        RETURN chunk.content AS content, 
               s.name AS entity, 
               score
        """
        try:
            with self.neo4j.driver.session() as session:
                result = session.run(cypher, top_k=top_k, query_vec=query_vec)
                return [record.data() for record in result]
        except Exception as e:
            logger.error(f"❌ 检索失败: {e}")
            return []

    def _format_context(self, records):
        """将检索到的记录格式化为 LLM 可读的文本"""
        context_parts = []
        for i, rec in enumerate(records):
            content = rec['content']
            entity = rec['entity']
            score = rec['score']
            
            # 格式示例:
            # [参考片段 1] (相关度: 0.92, 关联实体: 闭包)
            # 内容: 闭包是一个函数...
            part = f"[参考片段 {i+1}] (相关度: {score:.3f}, 关联实体: {entity})\n内容: {content}"
            context_parts.append(part)
        
        return "\n\n".join(context_parts)

    def _generate_answer(self, query, context):
        """调用 LLM 生成最终回答，返回 (answer, full_prompt)"""
        system_prompt = """你是一个智能知识库助手。请根据下方提供的【参考信息】回答用户问题。
        如果参考信息不足以回答问题，请直接说明“知识库中未找到相关内容”，不要编造。
        回答要条理清晰，引用信息时请注明来源。
        """
        
        user_prompt = f"""
        【参考信息】
        {context}
        
        【用户问题】
        {query}
        """

        full_prompt = f"System: {system_prompt}\nUser: {user_prompt}"
        
        try:
            response = self.llm_client.chat.completions.create(
                model=settings.MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=settings.TEMPERATURE
            )
            return response.choices[0].message.content, full_prompt
        except Exception as e:
            return f"❌ 生成回答失败: {e}", full_prompt
