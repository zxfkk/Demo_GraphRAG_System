import logging
import sys
import os

# 确保项目根目录在 sys.path 中，防止模块导入错误
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import settings
from utils.file_ops import load_file_content, load_all_markdown_files
from core.pipeline import run_graph_pipeline

# 初始化日志
settings.setup_logging()
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("程序启动...")
    
    # 1. 读取 Prompt 模板
    logger.info(f"读取 Prompt: {settings.PROMPT_FILE}")
    prompt_content = load_file_content(settings.PROMPT_FILE)
    if not prompt_content:
        print(f"❌ 错误：无法读取 Prompt 文件: {settings.PROMPT_FILE}")
        exit()

    # 2. 读取 Data 目录下的所有笔记
    logger.info(f"读取数据目录: {settings.DATA_DIR}")
    notes_list = load_all_markdown_files(settings.DATA_DIR)
    if not notes_list:
        print(f"❌ 错误：在 {settings.DATA_DIR} 下没有找到 markdown 文件")
        exit()

    # 3. 开始构建
    try:
        run_graph_pipeline(notes_list, prompt_content)
    except Exception as e:
        logger.error(f"运行过程中发生错误: {e}", exc_info=True)
        print(f"❌ 程序运行出错，请查看日志: {e}")