"""
AI模型比较和评估工具
"""

import asyncio
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import json
import statistics
from datetime import datetime

from .model_manager import model_manager, chat_with_ai

logger = logging.getLogger(__name__)

@dataclass
class ModelEvaluationMetrics:
    """模型评估指标"""
    model_name: str
    response_time: float
    token_count: int
    response_quality: float  # 0-10
    relevance_score: float   # 0-10
    error_count: int
    success_count: int
    total_cost: float

@dataclass
class ComparisonResult:
    """比较结果"""
    models: List[ModelEvaluationMetrics]
    winner_speed: str
    winner_quality: str
    winner_cost: str
    overall_score: Dict[str, float]
    timestamp: datetime

class ModelComparator:
    """模型比较器"""

    def __init__(self):
        self.evaluation_history: List[ComparisonResult] = []

    async def compare_models(
        self,
        models: List[str],
        test_cases: List[Dict[str, Any]],
        metrics: List[str] = None
    ) -> ComparisonResult:
        """
        比较多个模型

        Args:
            models: 要比较的模型列表
            test_cases: 测试用例列表
            metrics: 要评估的指标列表

        Returns:
            比较结果
        """
        if not metrics:
            metrics = ["speed", "quality", "relevance", "cost"]

        logger.info(f"Comparing models: {models}")
        logger.info(f"Test cases: {len(test_cases)}")

        # 评估每个模型
        model_metrics = {}
        for model in models:
            logger.info(f"Evaluating model: {model}")
            metrics_list = []

            for test_case in test_cases:
                try:
                    metric = await self._evaluate_single_case(
                        model,
                        test_case,
                        metrics
                    )
                    metrics_list.append(metric)
                except Exception as e:
                    logger.error(f"Failed to evaluate {model} on test case: {str(e)}")
                    # 创建失败的指标
                    metric = ModelEvaluationMetrics(
                        model_name=model,
                        response_time=0,
                        token_count=0,
                        response_quality=0,
                        relevance_score=0,
                        error_count=1,
                        success_count=0,
                        total_cost=0
                    )
                    metrics_list.append(metric)

            # 聚合指标
            model_metrics[model] = self._aggregate_metrics(metrics_list)

        # 确定优胜者
        results = list(model_metrics.values())
        winner_speed = min(results, key=lambda x: x.response_time).model_name
        winner_quality = max(results, key=lambda x: x.response_quality).model_name
        winner_cost = min(results, key=lambda x: x.total_cost).model_name

        # 计算综合评分
        overall_score = self._calculate_overall_score(model_metrics)

        comparison = ComparisonResult(
            models=results,
            winner_speed=winner_speed,
            winner_quality=winner_quality,
            winner_cost=winner_cost,
            overall_score=overall_score,
            timestamp=datetime.now()
        )

        self.evaluation_history.append(comparison)
        return comparison

    async def _evaluate_single_case(
        self,
        model: str,
        test_case: Dict[str, Any],
        metrics: List[str]
    ) -> ModelEvaluationMetrics:
        """评估单个测试用例"""
        start_time = time.time()

        # 执行模型
        response = await chat_with_ai(
            message=test_case["prompt"],
            model=model,
            context=test_case.get("context", []),
            stream=False
        )

        duration = time.time() - start_time

        # 提取响应内容
        response_text = response.get("content", "") if isinstance(response, dict) else str(response)

        # 计算各种指标
        response_time = duration
        token_count = self._estimate_tokens(response_text)
        response_quality = await self._evaluate_quality(response_text, test_case) if "quality" in metrics else 0
        relevance_score = self._calculate_relevance(response_text, test_case) if "relevance" in metrics else 0
        total_cost = self._estimate_cost(model, token_count) if "cost" in metrics else 0

        return ModelEvaluationMetrics(
            model_name=model,
            response_time=response_time,
            token_count=token_count,
            response_quality=response_quality,
            relevance_score=relevance_score,
            error_count=0,
            success_count=1,
            total_cost=total_cost
        )

    def _aggregate_metrics(self, metrics_list: List[ModelEvaluationMetrics]) -> ModelEvaluationMetrics:
        """聚合多个测试用例的指标"""
        if not metrics_list:
            return ModelEvaluationMetrics("", 0, 0, 0, 0, 0, 0, 0)

        # 计算平均值
        response_times = [m.response_time for m in metrics_list if m.success_count > 0]
        token_counts = [m.token_count for m in metrics_list if m.success_count > 0]
        qualities = [m.response_quality for m in metrics_list if m.success_count > 0]
        relevances = [m.relevance_score for m in metrics_list if m.success_count > 0]
        costs = [m.total_cost for m in metrics_list if m.success_count > 0]

        return ModelEvaluationMetrics(
            model_name=metrics_list[0].model_name,
            response_time=statistics.mean(response_times) if response_times else 0,
            token_count=statistics.mean(token_counts) if token_counts else 0,
            response_quality=statistics.mean(qualities) if qualities else 0,
            relevance_score=statistics.mean(relevances) if relevances else 0,
            error_count=sum(m.error_count for m in metrics_list),
            success_count=sum(m.success_count for m in metrics_list),
            total_cost=statistics.mean(costs) if costs else 0
        )

    async def _evaluate_quality(self, response: str, test_case: Dict[str, Any]) -> float:
        """评估响应质量"""
        # 这里可以使用更复杂的评估方法
        # 例如使用另一个AI模型来评分

        quality_score = 5.0  # 基础分数

        # 检查响应长度
        if len(response) < 10:
            quality_score -= 2
        elif len(response) > 500:
            quality_score -= 1

        # 检查是否包含期望的关键词
        if "expected_keywords" in test_case:
            keywords = test_case["expected_keywords"]
            found_keywords = sum(1 for kw in keywords if kw.lower() in response.lower())
            if keywords:
                quality_score += (found_keywords / len(keywords)) * 3

        # 检查格式
        if test_case.get("expected_format") == "json":
            try:
                json.loads(response)
                quality_score += 1
            except:
                quality_score -= 2

        # 确保分数在0-10范围内
        return max(0, min(10, quality_score))

    def _calculate_relevance(self, response: str, test_case: Dict[str, Any]) -> float:
        """计算相关性分数"""
        if "expected_answer" not in test_case:
            return 7.0  # 默认分数

        expected = test_case["expected_answer"].lower()
        response_lower = response.lower()

        # 简单的词汇重叠计算
        expected_words = set(expected.split())
        response_words = set(response_lower.split())

        if not expected_words:
            return 7.0

        overlap = len(expected_words & response_words)
        relevance = (overlap / len(expected_words)) * 10

        return min(10, relevance)

    def _estimate_tokens(self, text: str) -> int:
        """估算token数量"""
        # 粗略估算：1 token ≈ 4 characters
        return len(text) // 4

    def _estimate_cost(self, model: str, token_count: int) -> float:
        """估算成本"""
        # 简化的成本计算
        costs = {
            "openai:gpt-4-turbo-preview": 0.03 / 1000,  # $0.03 per 1K tokens
            "openai:gpt-3.5-turbo": 0.002 / 1000,  # $0.002 per 1K tokens
            "anthropic:claude-3-opus-20240229": 0.075 / 1000,  # $0.075 per 1K tokens
            "anthropic:claude-3-sonnet-20240229": 0.015 / 1000,  # $0.015 per 1K tokens
            "google:gemini-pro": 0.0005 / 1000,  # $0.0005 per 1K tokens
        }

        cost_per_token = costs.get(model, 0.01 / 1000)
        return token_count * cost_per_token

    def _calculate_overall_score(self, model_metrics: Dict[str, ModelEvaluationMetrics]) -> Dict[str, float]:
        """计算综合评分"""
        scores = {}

        for model, metrics in model_metrics.items():
            # 加权评分
            speed_score = max(0, 10 - metrics.response_time * 2)  # 响应时间越短分数越高
            quality_score = metrics.response_quality
            cost_score = max(0, 10 - metrics.total_cost * 100)  # 成本越低分数越高
            relevance_score = metrics.relevance_score

            # 综合评分（权重可调整）
            overall = (
                speed_score * 0.2 +
                quality_score * 0.4 +
                cost_score * 0.2 +
                relevance_score * 0.2
            )

            scores[model] = round(overall, 2)

        return scores

    def generate_report(self, comparison: ComparisonResult) -> str:
        """生成比较报告"""
        report = []
        report.append("# AI模型比较报告")
        report.append(f"\n生成时间: {comparison.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"\n比较模型数量: {len(comparison.models)}")

        # 优胜者摘要
        report.append("\n## 优胜者摘要")
        report.append(f"- 最快响应: {comparison.winner_speed}")
        report.append(f"- 最高质量: {comparison.winner_quality}")
        report.append(f"- 最低成本: {comparison.winner_cost}")

        # 详细指标
        report.append("\n## 详细指标")
        report.append("| 模型 | 响应时间(s) | Token数 | 质量评分 | 相关性 | 成本($) | 错误数 | 成功率 |")
        report.append("|------|------------|--------|---------|--------|--------|-------|--------|")

        for metrics in comparison.models:
            success_rate = (metrics.success_count / (metrics.success_count + metrics.error_count) * 100) if (metrics.success_count + metrics.error_count) > 0 else 0
            report.append(
                f"| {metrics.model_name} | {metrics.response_time:.2f} | {metrics.token_count} | "
                f"{metrics.response_quality:.1f} | {metrics.relevance_score:.1f} | "
                f"${metrics.total_cost:.4f} | {metrics.error_count} | {success_rate:.1f}% |"
            )

        # 综合评分
        report.append("\n## 综合评分")
        for model, score in comparison.overall_score.items():
            report.append(f"- {model}: {score}/10")

        # 建议
        best_model = max(comparison.overall_score.items(), key=lambda x: x[1])
        report.append(f"\n## 建议")
        report.append(f"根据综合评分，推荐使用 **{best_model[0]}**")

        return "\n".join(report)

# 全局比较器实例
model_comparator = ModelComparator()

# 便捷函数
async def run_model_comparison(models: Optional[List[str]] = None) -> ComparisonResult:
    """运行模型比较"""
    if not models:
        models = ["openai:gpt-4-turbo-preview", "openai:gpt-3.5-turbo"]

    # 创建测试用例
    test_cases = [
        {
            "prompt": "解释什么是机器学习",
            "expected_keywords": ["算法", "数据", "训练", "预测"],
            "context": []
        },
        {
            "prompt": "写一个Python函数计算斐波那契数列",
            "expected_format": "code",
            "context": []
        },
        {
            "prompt": "用JSON格式返回一个用户信息",
            "expected_format": "json",
            "context": []
        },
        {
            "prompt": "总结人工智能的发展历史",
            "expected_keywords": ["图灵", "深度学习", "神经网络"],
            "context": []
        },
        {
            "prompt": "创建一个待办事项列表",
            "context": [
                {"role": "user", "content": "我需要管理我的任务"},
                {"role": "assistant", "content": "我可以帮您创建一个待办事项列表"}
            ]
        }
    ]

    return await model_comparator.compare_models(models, test_cases)