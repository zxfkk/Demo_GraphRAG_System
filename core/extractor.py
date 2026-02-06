import json
import logging
import os
import hashlib
from openai import OpenAI
from config import settings
from core.embedding import get_embeddings_batch

logger = logging.getLogger(__name__)

def get_cache_path(content, key_identifier):
    """
    计算内容的哈希值并返回缓存文件路径
    并且会清理掉该 key_identifier (通常是文件名) 对应的旧缓存
    """
    # 确保存储目录存在
    storage_dir = os.path.join(settings.ROOT_DIR, 'storage')
    if not os.path.exists(storage_dir):
        os.makedirs(storage_dir)

    # 计算新 Hash
    hash_md5 = hashlib.md5(content.encode('utf-8')).hexdigest()
    
    # 构造新的缓存文件名: 这里的 key_identifier 建议传入文件名，例如 "UE5"
    # 文件名格式: {文件名}.{Hash}.json
    # 这样做的好处是我们可以通过前缀快速找到旧版本缓存
    new_cache_filename = f"{key_identifier}.{hash_md5}.json"
    new_cache_path = os.path.join(storage_dir, new_cache_filename)
    
    # 如果这个确切的文件已经存在，说明完全没变，直接返回
    if os.path.exists(new_cache_path):
        return new_cache_path

    # 如果这个文件不存在，说明内容变了（Hash变了）
    # 此时我们需要清理掉这个 key_identifier 对应的所有人旧缓存
    # 遍历 storage 目录
    for filename in os.listdir(storage_dir):
        # 检查是否是同一个文件的旧缓存 (以 key_identifier + "." 开头，且不是当前这个新文件)
        if filename.startswith(f"{key_identifier}.") and filename != new_cache_filename:
            old_path = os.path.join(storage_dir, filename)
            try:
                os.remove(old_path)
                logger.info(f"🧹 清理旧缓存: {filename}")
            except OSError as e:
                logger.warning(f"无法删除旧缓存 {filename}: {e}")

    return new_cache_path

def extract_hybrid_data(text, prompt_template, source_id="unknown_source"):
    """
    利用 LLM 提取三元组和块信息
    :param source_id: 唯一标识符，通常传文件名，用于缓存管理
    """
    client = OpenAI(api_key=settings.API_KEY, base_url=settings.BASE_URL)
    
    # 替换 Prompt 中的占位符
    if "CONTENT_PLACEHOLDER" not in prompt_template:
        logger.warning("Prompt 模板中未找到 CONTENT_PLACEHOLDER，可能导致提取失败。")
        
    prompt = prompt_template.replace("CONTENT_PLACEHOLDER", text)

    logger.info("="*15 + f" 开始分析新笔记 [{source_id}] " + "="*15)
    
    # 1. 打印详细 Prompt (前100字 + 后100字)
    if len(prompt) > 200:
        log_prompt = f"{prompt[:100]} ... [省略 {len(prompt)-200} 字] ... {prompt[-100:]}"
    else:
        log_prompt = prompt
    logger.info(f"📤 [Request] 发送给 API 的实际内容:\n{log_prompt}")
    
    # 2. 检查缓存 (传入 source_id)
    cache_file = get_cache_path(prompt, source_id)
    content = ""
    is_cached = False
    
    if os.path.exists(cache_file):
        logger.info(f"📦 此内容已在 storage 中找到缓存 ({os.path.basename(cache_file)})，跳过 API 调用。")
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                content = f.read()
            is_cached = True
        except Exception as e:
            logger.error(f"读取缓存文件失败: {e}，准备重新调用 API。")
            content = ""
    
    # 3. 如果无缓存，调用 API
    if not content:
        try:
            response = client.chat.completions.create(
                model=settings.MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=settings.TEMPERATURE
            )
            content = response.choices[0].message.content.strip()
            
            # 存入缓存
            try:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                logger.info(f"💾 API 返回值已保存至缓存: {cache_file}")
            except Exception as e:
                logger.error(f"缓存写入失败: {e}")
                
        except Exception as e:
            logger.error(f"❌ LLM 处理出错: {str(e)}")
            return [], [], ""

    # 4. 打印详细 Response
    if len(content) > 200:
        log_content = f"{content[:100]} ... [省略 {len(content)-200} 字] ... {content[-100:]}"
    else:
        log_content = content
    logger.info(f"📥 [Response] API 返回详细内容:\n{log_content}")

    try:
        # 清洗 JSON
        cleaned_content = content
        if cleaned_content.startswith("```"):
            cleaned_content = cleaned_content.replace("```json", "").replace("```", "")
        
        data = json.loads(cleaned_content)
        
        triplets = data.get("triplets", [])
        chunks = data.get("chunks", [])

        # ================= Embedding 补全逻 =================
        # 检查 chunks 中是否缺失 embedding
        missing_embeddings_indices = []
        texts_to_embed = []

        for i, chunk in enumerate(chunks):
            if "embedding" not in chunk or not chunk["embedding"]:
                missing_embeddings_indices.append(i)
                texts_to_embed.append(chunk["content"])

        if texts_to_embed:
            logger.info(f"🧩 检测到 {len(texts_to_embed)} 个文本块缺失 Embedding (共 {len(chunks)} 个)，正在补全...")
            
            embeddings = get_embeddings_batch(texts_to_embed)
            
            # 填回 chunks
            for idx, emb in zip(missing_embeddings_indices, embeddings):
                chunks[idx]["embedding"] = emb
            
            # 更新 data 对象
            data["chunks"] = chunks
            
            # 回写缓存 (覆盖旧文件)
            try:
                # 注意：这里我们覆盖写入的是完整的 JSON 对象，不再是 LLM 原始返回的所谓 Markdown 字符串
                # 为了保持通过 "content" 变量的一致性，虽然稍微改变了存储格式(纯JSON vs Markdown包裹)，
                # 但下一次读取时 json.loads 依然能解析纯 JSON
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info(f"💾 Embedding 已补全并更新缓存: {cache_file}")
            except Exception as e:
                logger.error(f"❌ 缓存回写失败: {e}")
        else:
            logger.info(f"⏩ 所有文本块均包含 Embedding，跳过向量计算。")
        # ===================================================
        
        token_info = " (Cached)" if is_cached else ""
        logger.info(f"✅ 提取成功: {len(triplets)} 个三元组, {len(chunks)} 个块。{token_info}")
        
        # 返回 hash_md5 方便上层做版本控制
        # 注意：这里的 content 是 API 返回的内容，不是原始笔记内容的 hash。
        # 我们应该返回原始笔记 prompt 的 hash，即生成 cache_file 时用的 hash。
        # 上面 get_cache_path 里算过一次，但没有返回。
        # 我们重新计算一次或者让 get_cache_path 返回。
        # 简单起见，重新计算 prompt 的 hash (它包含了原始文本)
        current_hash = hashlib.md5(prompt.encode('utf-8')).hexdigest()
        
        return triplets, chunks, current_hash

    except Exception as e:
        logger.error(f"❌ JSON 解析出错: {str(e)}", exc_info=True)
        return [], [], ""
