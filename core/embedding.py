import logging
from openai import OpenAI
from config import settings

logger = logging.getLogger(__name__)

def get_embedding(text):
    """
    调用 embedding 模型将文本转换为向量
    :param text: 输入文本
    :return: 向量 (List[float])
    """
    if not text or not isinstance(text, str):
        return []

    client = OpenAI(api_key=settings.API_KEY, base_url=settings.BASE_URL)

    try:
        # 注意: 这里的 model 必须是 embedding 模型名称
        response = client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=text,
            dimensions=settings.EMBEDDING_DIM, # 部分模型支持指定维度
            encoding_format="float"
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"❌ Embedding 生成失败: {e}")
        return []

def get_embeddings_batch(texts):
    """
    批量生成向量
    """
    if not texts:
        return []
    
    client = OpenAI(api_key=settings.API_KEY, base_url=settings.BASE_URL)
    
    try:
        response = client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=texts,
            dimensions=settings.EMBEDDING_DIM,
            encoding_format="float"
        )
        # 按照 index 排序返回，保证顺序一致
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]
    except Exception as e:
        logger.error(f"❌ 批量 Embedding 生成失败: {e}")
        return [None] * len(texts)
