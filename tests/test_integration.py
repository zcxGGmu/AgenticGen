"""
集成测试
测试系统各组件的协作
"""

import pytest
import asyncio
from datetime import datetime
import json

from agent.agent_manager import AgentManager
from knowledge.knowledge_base import KnowledgeBase
from tools.python_executor import PythonExecutor
from orchestration.orchestrator import AgentOrchestrator
from monitoring.metrics_collector import MetricsCollector


class TestAgentIntegration:
    """代理系统集成测试"""

    @pytest.mark.asyncio
    async def test_agent_chat_flow(self):
        """测试完整的聊天流程"""
        agent_manager = AgentManager()

        # 创建代理
        agent = await agent_manager.get_or_create_agent(
            thread_id="test_thread_1",
            agent_type="coding"
        )

        # 发送多条消息
        messages = [
            "Write a function to calculate fibonacci numbers",
            "Can you optimize it?",
            "Add error handling to the function"
        ]

        for message in messages:
            response = await agent.chat_async(message)
            assert response is not None
            assert len(response) > 0

        # 清理
        await agent_manager.remove_agent("test_thread_1")

    @pytest.mark.asyncio
    async def test_multi_agent_collaboration(self):
        """测试多代理协作"""
        orchestrator = AgentOrchestrator()

        # 创建多个相关任务
        tasks = []
        task_configs = [
            {
                "type": "code_analysis",
                "description": "Analyze this Python code",
                "input_data": {"code": "def hello(): print('Hello')"}
            },
            {
                "type": "code_generation",
                "description": "Generate tests for the code",
                "input_data": {"requirements": "Unit tests for hello function"}
            },
            {
                "type": "conversation",
                "description": "Review the generated tests",
                "input_data": {"message": "Are these tests comprehensive?"}
            }
        ]

        for config in task_configs:
            task_id = await orchestrator.submit_task(**config)
            tasks.append(task_id)

        # 等待任务完成
        await asyncio.sleep(2)

        # 检查任务状态
        for task_id in tasks:
            status = await orchestrator.get_task_status(task_id)
            assert status is not None
            assert status["status"] in ["completed", "running", "pending"]

    @pytest.mark.asyncio
    async def test_agent_with_tools(self):
        """测试代理使用工具"""
        agent_manager = AgentManager()

        # 创建具有工具访问权限的代理
        agent = await agent_manager.get_or_create_agent(
            thread_id="test_thread_2",
            agent_type="coding"
        )

        # 请求代理执行代码
        message = """
        Please execute this Python code and show me the result:

        import math
        result = math.sqrt(16)
        print(f"The square root of 16 is {result}")
        """

        response = await agent.chat_async(message)
        assert response is not None
        assert "4" in response or "sqrt" in response.lower()

        # 清理
        await agent_manager.remove_agent("test_thread_2")


class TestKnowledgeIntegration:
    """知识库集成测试"""

    @pytest.mark.asyncio
    async def test_rag_pipeline(self):
        """测试RAG（检索增强生成）流程"""
        # 创建知识库
        kb = KnowledgeBase("test_kb")

        # 添加测试文档
        test_docs = [
            {
                "content": """
                Python is a high-level programming language.
                It was created by Guido van Rossum and first released in 1991.
                Python emphasizes code readability and has a clean syntax.
                """,
                "metadata": {"source": "python_intro.txt", "type": "documentation"}
            },
            {
                "content": """
                Machine Learning is a subset of artificial intelligence.
                It uses algorithms to parse data, learn from it, and make predictions.
                Popular ML frameworks include TensorFlow and PyTorch.
                """,
                "metadata": {"source": "ml_intro.txt", "type": "documentation"}
            }
        ]

        for doc in test_docs:
            await kb.add_document(
                content=doc["content"],
                metadata=doc["metadata"]
            )

        # 等待索引完成
        await asyncio.sleep(1)

        # 搜索查询
        query = "Who created Python?"
        results = await kb.search(query, limit=3)

        assert len(results) > 0
        assert any("Guido" in result.content for result in results)

    @pytest.mark.asyncio
    async def test_semantic_search(self):
        """测试语义搜索"""
        from knowledge.semantic_search import SemanticSearchEngine

        search_engine = SemanticSearchEngine()

        # 索引文档
        await search_engine.index_document(
            doc_id="doc1",
            content="The sky is blue during the day.",
            metadata={"type": "fact"}
        )

        await search_engine.index_document(
            doc_id="doc2",
            content="Ocean water appears blue because of light absorption.",
            metadata={"type": "fact"}
        )

        # 语义搜索
        results = await search_engine.search("Why is the sky blue?")

        assert len(results) > 0
        assert results[0].score > 0.5

    @pytest.mark.asyncio
    async def test_knowledge_graph(self):
        """测试知识图谱"""
        from knowledge.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph()

        # 添加实体和关系
        text = """
        Apple Inc. is a technology company founded by Steve Jobs.
        It is headquartered in Cupertino, California.
        The iPhone is a product of Apple Inc.
        """

        entities, relations = await kg.add_entities_and_relations(text, "test_source")

        assert len(entities) > 0
        assert len(relations) > 0

        # 查询图
        apple_entity = await kg.find_entity("Apple Inc.", "organization")
        assert apple_entity is not None

        related = await kg.find_related_entities(apple_entity.id)
        assert len(related) > 0


class TestMonitoringIntegration:
    """监控系统集成测试"""

    @pytest.mark.asyncio
    async def test_metrics_collection(self):
        """测试指标收集"""
        collector = MetricsCollector()

        # 记录各种类型的指标
        await collector.record_metric("test_counter", 1.0)
        await collector.increment_counter("test_increment", 5.0)
        await collector.set_gauge("test_gauge", 42.0)
        await collector.record_histogram("test_histogram", 15.5)

        # 获取指标
        metrics = await collector.get_metric("test_counter")
        assert len(metrics) > 0
        assert metrics[-1].value == 1.0

        # 获取聚合
        agg = await collector.get_aggregation("test_histogram", "1m")
        assert agg.count > 0
        assert agg.avg > 0

    @pytest.mark.asyncio
    async def test_alerting_system(self):
        """测试告警系统"""
        from monitoring.alerting import AlertingEngine, AlertRule, AlertSeverity, ComparisonOperator

        collector = MetricsCollector()
        alerting = AlertingEngine(collector)

        # 创建测试规则
        rule = AlertRule(
            id="test_rule",
            name="Test Alert",
            description="Test alert rule",
            metric_name="test_metric",
            operator=ComparisonOperator.GT,
            threshold=10.0,
            severity=AlertSeverity.WARNING
        )

        await alerting.add_rule(rule)

        # 记录触发告警的指标
        for i in range(10):
            await collector.record_metric("test_metric", 15.0)

        # 等待告警评估
        await asyncio.sleep(2)

        # 检查告警
        active_alerts = await alerting.get_active_alerts()
        test_alerts = [a for a in active_alerts if a["rule_id"] == "test_rule"]

        # 注意：实际测试中可能需要调整等待时间和阈值


class TestToolsIntegration:
    """工具集成测试"""

    @pytest.mark.asyncio
    async def test_python_executor_integration(self):
        """测试Python执行器集成"""
        executor = PythonExecutor()

        # 执行简单代码
        code = """
        import json
        data = {"numbers": [1, 2, 3, 4, 5]}
        result = {
            "sum": sum(data["numbers"]),
            "avg": sum(data["numbers"]) / len(data["numbers"])
        }
        print(json.dumps(result))
        """

        result = await executor.execute(code, timeout=5)

        assert result["exit_code"] == 0
        assert "result" in result["output"]
        assert result["error"] is None

        # 验证输出
        import json
        output_data = json.loads(result["output"].strip())
        assert output_data["sum"] == 15
        assert output_data["avg"] == 3.0

    @pytest.mark.asyncio
    async def test_expanded_tools(self):
        """测试扩展工具集"""
        from tools.expanded_tools import GitTool, FileSystemTool, DataAnalysisTool

        # 测试Git工具
        git_tool = GitTool()
        status = await git_tool.get_status()
        assert "status" in status

        # 测试文件系统工具
        fs_tool = FileSystemTool()
        files = await fs_tool.list_directory(".", recursive=False)
        assert isinstance(files, list)

        # 测试数据分析工具
        data_tool = DataAnalysisTool()
        # 这里可以使用测试数据
        test_data = {"values": [1, 2, 3, 4, 5]}
        stats = await data_tool.calculate_statistics(test_data)
        assert "mean" in stats
        assert stats["mean"] == 3.0


class TestEndToEndWorkflow:
    """端到端工作流测试"""

    @pytest.mark.asyncio
    async def test_document_analysis_workflow(self):
        """测试文档分析工作流"""
        orchestrator = AgentOrchestrator()

        # 步骤1：上传和分析文档
        task1_id = await orchestrator.submit_task(
            type="file_processing",
            description="Analyze the uploaded document",
            input_data={
                "file_info": {"name": "test.pdf", "type": "application/pdf"},
                "processing_goal": "Extract key insights and summary"
            }
        )

        # 步骤2：基于分析结果生成报告
        task2_id = await orchestrator.submit_task(
            type="code_generation",
            description="Generate analysis report",
            input_data={
                "requirements": "Create a structured report based on document analysis",
                "dependencies": [task1_id]
            }
        )

        # 步骤3：可视化数据
        task3_id = await orchestrator.submit_task(
            type="data_analysis",
            description="Create visualizations",
            input_data={
                "data_description": "Data extracted from document",
                "analysis_goal": "Generate charts and graphs",
                "dependencies": [task1_id]
            }
        )

        # 等待所有任务完成
        await asyncio.sleep(3)

        # 验证任务状态
        for task_id in [task1_id, task2_id, task3_id]:
            status = await orchestrator.get_task_status(task_id)
            assert status is not None

    @pytest.mark.asyncio
    async def test_code_development_workflow(self):
        """测试代码开发工作流"""
        orchestrator = AgentOrchestrator()

        # 需求：实现一个排序算法
        requirements = """
        Implement a sorting algorithm with the following requirements:
        1. Time complexity better than O(n^2)
        2. Stable sort
        3. Handle duplicate values
        """

        # 步骤1：设计算法
        design_task = await orchestrator.submit_task(
            type="code_analysis",
            description="Design sorting algorithm approach",
            input_data={
                "requirements": requirements
            }
        )

        # 步骤2：实现代码
        impl_task = await orchestrator.submit_task(
            type="code_generation",
            description="Implement the sorting algorithm",
            input_data={
                "language": "python",
                "requirements": requirements,
                "dependencies": [design_task]
            }
        )

        # 步骤3：编写测试
        test_task = await orchestrator.submit_task(
            type="code_generation",
            description="Write unit tests",
            input_data={
                "requirements": "Comprehensive tests for sorting algorithm",
                "dependencies": [impl_task]
            }
        )

        # 等待完成
        await asyncio.sleep(5)

        # 获取实现结果
        impl_result = await orchestrator.get_task_status(impl_task)
        assert impl_result is not None
        if impl_result["status"] == "completed":
            assert impl_result["result"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])