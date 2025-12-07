"""
AI模型模块
提供统一的多模型管理接口
"""

from .model_manager import (
    # 模型提供商枚举
    ModelProvider,

    # 模型配置
    ModelConfig,

    # 基础模型类
    BaseAIModel,

    # 具体模型实现
    OpenAIModel,
    ClaudeModel,
    GeminiModel,

    # 模型管理器
    ModelManager,
    model_manager,

    # 便捷函数
    chat_with_ai,
    get_text_embeddings,
    get_available_ai_models,
)

from .model_comparison import (
    # 评估指标
    ModelEvaluationMetrics,
    ComparisonResult,

    # 模型比较器
    ModelComparator,
    model_comparator,

    # 便捷函数
    run_model_comparison,
)

__all__ = [
    # 枚举和配置
    "ModelProvider",
    "ModelConfig",

    # 基础类
    "BaseAIModel",

    # 模型实现
    "OpenAIModel",
    "ClaudeModel",
    "GeminiModel",

    # 管理器
    "ModelManager",
    "model_manager",

    # 比较器
    "ModelComparator",
    "model_comparator",

    # 数据类型
    "ModelEvaluationMetrics",
    "ComparisonResult",

    # 便捷函数
    "chat_with_ai",
    "get_text_embeddings",
    "get_available_ai_models",
    "run_model_comparison",
]

# 初始化函数
def init_ai_models():
    """初始化AI模型模块"""
    logger = logging.getLogger(__name__)

    # 获取可用模型
    available_models = get_available_ai_models()
    logger.info(f"Available AI models: {len(available_models)}")

    for model in available_models:
        logger.info(f"- {model['id']}: {model['name']} ({model['provider']})")

    logger.info("AI models module initialized")