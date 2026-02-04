import os
import logging
import sys
import io
from dotenv import load_dotenv
from utils import load_yaml_config

# 强制设置标准输出为 UTF-8，解决 Windows 下 Emoji 导致的 GBK 编码错误
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except AttributeError:
        # 在某些 IDE (如 pytest 或旧版 Notebook) 中 buffer 可能不可用
        pass

# 项目根目录
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 1. 加载环境变量 (读取 .env)
# 显式指定 .env 路径，防止在不同目录下运行找不到
load_dotenv(os.path.join(ROOT_DIR, '.env'))

# 2. 读取 YAML 配置
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')

try:
    _yaml_conf = load_yaml_config(CONFIG_PATH)
except Exception as e:
    print(f"❌ 加载配置文件 {CONFIG_PATH} 失败: {e}")
    _yaml_conf = {}

# ================= 导出配置变量 =================

# API 相关
API_KEY = os.getenv("DASHSCOPE_API_KEY")
if not API_KEY:
    # 尝试从 yaml 中读取? 通常 API Key 不放 yaml。
    # 这里保持原有逻辑，抛出异常或警告
    print("⚠️ 警告: 未找到 DASHSCOPE_API_KEY，请确保 .env 文件存在且已配置。")

# 模型相关
LLM_SETTINGS = _yaml_conf.get('llm', {})
MODEL_NAME = LLM_SETTINGS.get('model_name', 'qwen-max')
BASE_URL = LLM_SETTINGS.get('base_url', '')
TEMPERATURE = LLM_SETTINGS.get('temperature', 0.1)

# 路径相关
PATHS = _yaml_conf.get('paths', {})

# 将相对路径转换为绝对路径，确保在任何地方调用都正确
def get_abs_path(path_str, default_folder=""):
    if not path_str:
        return os.path.join(ROOT_DIR, default_folder)
    if os.path.isabs(path_str):
        return path_str
    return os.path.join(ROOT_DIR, path_str)

DATA_DIR = get_abs_path(PATHS.get('data_dir', 'data'))
PROMPT_FILE = get_abs_path(PATHS.get('prompt_file', 'prompt/standardize.md'))

# 日志文件存放在 logs 目录下
log_filename = PATHS.get('log_file', 'app.log')
LOG_FILE = os.path.join(ROOT_DIR, 'logs', log_filename)

# 绘图相关
PLOT_SETTINGS = _yaml_conf.get('plot', {})

# Neo4j 数据库配置
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("DATABASE_KEY")

if not NEO4J_PASSWORD:
    print("⚠️ 警告: 未找到 DATABASE_KEY，数据库连接可能会失败。")

# ================= 初始化日志配置 =================
def setup_logging():
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 显式创建 Handlers 以解决编码问题
    # 1. 终端输出 Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    
    # 2. 文件输出 Handler
    file_handler = logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # 清除默认的 handlers 防止重复打印
    root_logger.handlers = []
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
