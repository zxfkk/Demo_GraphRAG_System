# 一个学习图数据库neo4j和graphrag流程的项目

# graphrag流程
图的构建：要存储3层维度的信息
1. 逻辑结构层，将原始文本送给大模型，让它提炼出其中的关系，实体
2. 原始文本层，将原始文本作为特殊的节点chunks
3. 向量索引层，将原始文本送给embedding模型，得到高维向量，存放在chunks的节点属性中

实际回答经历的步骤：
1. 用户询问一个问题，送入embedding模型，得到一个高维向量
2. 在图数据库中，对问题向量和图中存在的向量进行计算，找到和问题向量最匹配的几个向量，从而找到关键节点
3. 顺藤摸瓜，找到和这个节点有关的其他节点。
4. 将找到的关系组成句子，和原始文本一块打包送给大模型，让大模型根据这些信息回答问题。

# 项目简介
本项目是一个基于 Graph RAG (Graph Retrieval-Augmented Generation) 技术的个人知识库问答系统。它旨在解决传统 RAG（仅基于向量检索）在处理复杂关联信息时的“碎片化”问题。 通过解析 Obsidian Markdown 笔记，利用 LLM 提取知识图谱（实体与关系）并生成混合索引（图结构 + 向量索引），最终实现深度、精准的知识问答。

# 核心架构设计
系统主要分为 数据注入流水线 (Ingestion Pipeline) 和 问答检索 (Retrieval & QA) 两大模块。

# 技术栈
编程语言: Python 3.x
图数据库: Neo4j (5.x 版本，支持 Vector Index)
大模型 (LLM): Qwen-Max (通义千问，用于提取与回答)
向量模型 (Embedding): Text-Embedding-v3 (1024维)
框架/库: neo4j (官方驱动), openai (调用兼容接口)

# 数据流向图
Markdown 笔记 -> LLM 提取 -> 三元组 + 文本块 -> 混合存储 (Neo4j) -> 用户提问 -> 混合检索 -> 生成答案j

# 混合信息提取层 (Extraction Layer)
代码位置: core/extractor.py
这是系统的第一步，负责将非结构化的文本转化为结构化知识。
1. Prompt 工程: 利用专门设计的 Prompt，让 LLM 同时从文本中提取：
    1. Triplets (三元组): (Head) -[Relation]-> (Tail)，构建逻辑图谱。
    2. Chunks (文本块): 原始文本片段，作为事实锚点。
2. 多级缓存机制 (Smart Caching):
    1. Lejel 1 (LLM 缓存): 基于 "Prompt + 内容" 的 Hash 计算。如果文件内容未变，直接读取本地 JSON，零 Token 消耗。
    2. Level 2 (向量补全): 读取缓存后，自动检查是否缺失 Embedding 向量。如果缺失，单独调用 Embedding API 进行补全并回写缓存。

# 知识图谱与向量存储 (Storage Layer)
代码位置: core/neo4j_manager.py
为了支持高效检索，我在 Neo4j 中构建了独特的 Schema：
1. 节点设计:
    1. Concept: 实体节点，代表知识点（如 "闭包", "Python"）。
    2. Chunk: 文本块节点，存储原始文本和 Embedding 向量 (List[float])。
2. 索引优化:
    1. Vector Index: 创建 chunk_embedding_index，支持余弦相似度搜索。
    2. 唯一约束: 保证实体的唯一性，避免重复。
3. 幂等性写入:
    实现了 prune_source_data(source_id) 方法。每次写入前，自动清理该文件对应的旧 Chunk 和关系，防止多次运行导致数据重复膨胀。

# 智能流水线 (Pipeline with Version Control)
代码位置: core/pipeline.py
不仅是简单的 ETL，还引入了版本控制逻辑：
1. Hash 比对: 提取数据后，计算当前内容的 current_hash。
2. 元数据检查: 查询 Neo4j 中的 SourceMetadata 节点。
3. 智能跳过: 如果数据库中的 Hash 与当前一致，直接跳过写入操作，极大提升运行效率。

# 混合检索引擎 (Graph RAG Engine)
代码位置: core/query_engine.py
实现了 "向量检索 + 图谱关联" 的检索策略：
1. 向量召回: 将用户问题 Embedding 化，通过 Neo4j 的 db.index.vector.queryNodes 快速找到 Top-K 最相似的文本块。
2. 图谱扩展 (Graph Traversal): 利用 Cypher 查询 OPTIONAL MATCH，从找到的 Chunk 出发，反向查找它关联的 Concept 实体。
3. 上下文构建: 将检索到的 [内容] 与 [关联实体] 格式化喂给大模型。

# 评估与对比系统
代码位置: ask.py
为了验证 Graph RAG 的有效性，开发了对比交互终端：
1. 双路执行: 同时运行 GraphRAG 和 Vanilla LLM（直接问大模型）。
2. 日志审计: 分别记录两者的输入 Prompt 和输出结果到 rag_log.json 和 vanilla_log.json，方便通过真实案例展示 RAG 带来的准确性提升（如减少幻觉）。

# 项目亮点
1. 完整的 Graph RAG 闭环: 实现了从非结构化数据到结构化图谱，再到自然语言生成的全流程。
2. 原生向量支持: 没有使用额外的向量数据库（如 Chroma/Milvus），而是直接利用 Ne  o4j 5.x 的向量索引功能，降低了架构复杂度。
3. Hash 缓存避免重复计费。
4. 覆盖更新机制防止脏数据堆积。
5. 可观测性: 完善的日志记录和对比模式，直观展示 RAG 效果。