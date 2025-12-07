"""
API端点测试
"""

import pytest
from fastapi.testclient import TestClient
import json
from datetime import datetime, timedelta

from api.main import app
from auth.auth import create_access_token
from db.models import User

client = TestClient(app)


class TestAuthAPI:
    """认证API测试"""

    def test_register_user(self):
        """测试用户注册"""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "Test123456!"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "user_id" in data
        assert data["message"] == "User registered successfully"

    def test_login(self):
        """测试用户登录"""
        response = client.post(
            "/api/auth/login",
            json={
                "username": "testuser",
                "password": "Test123456!"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "token_type" in data
        assert data["token_type"] == "bearer"

    def test_invalid_login(self):
        """测试无效登录"""
        response = client.post(
            "/api/auth/login",
            json={
                "username": "testuser",
                "password": "wrongpassword"
            }
        )
        assert response.status_code == 401
        assert "detail" in response.json()

    def test_protected_endpoint_without_token(self):
        """测试无token访问受保护端点"""
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_protected_endpoint_with_token(self):
        """测试有token访问受保护端点"""
        # 先登录获取token
        login_response = client.post(
            "/api/auth/login",
            json={
                "username": "testuser",
                "password": "Test123456!"
            }
        )
        token = login_response.json()["access_token"]

        # 使用token访问受保护端点
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["username"] == "testuser"


class TestChatAPI:
    """聊天API测试"""

    @pytest.fixture
    def auth_token(self):
        """获取认证token"""
        # 创建测试用户并获取token
        user_id = "test_user_123"
        token = create_access_token(data={"sub": user_id})
        return token

    def test_create_chat_thread(self, auth_token):
        """测试创建聊天线程"""
        response = client.post(
            "/api/chat/threads",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "thread_id" in data
        assert data["message"] == "Thread created successfully"

    def test_send_message(self, auth_token):
        """测试发送消息"""
        # 先创建线程
        thread_response = client.post(
            "/api/chat/threads",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        thread_id = thread_response.json()["thread_id"]

        # 发送消息
        response = client.post(
            f"/api/chat/threads/{thread_id}/messages",
            json={
                "message": "Hello, how are you?"
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "message_id" in data

    def test_get_chat_history(self, auth_token):
        """测试获取聊天历史"""
        # 先创建线程
        thread_response = client.post(
            "/api/chat/threads",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        thread_id = thread_response.json()["thread_id"]

        # 获取历史记录
        response = client.get(
            f"/api/chat/threads/{thread_id}/history",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert isinstance(data["messages"], list)

    def test_stream_chat(self, auth_token):
        """测试流式聊天"""
        # 先创建线程
        thread_response = client.post(
            "/api/chat/threads",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        thread_id = thread_response.json()["thread_id"]

        # 测试流式响应
        response = client.post(
            f"/api/chat/threads/{thread_id}/stream",
            json={
                "message": "Tell me a joke"
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream"


class TestKnowledgeAPI:
    """知识库API测试"""

    @pytest.fixture
    def auth_token(self):
        """获取认证token"""
        token = create_access_token(data={"sub": "test_user_123"})
        return token

    def test_create_knowledge_base(self, auth_token):
        """测试创建知识库"""
        response = client.post(
            "/api/knowledge/bases",
            json={
                "name": "Test Knowledge Base",
                "description": "A test knowledge base"
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "kb_id" in data
        assert data["name"] == "Test Knowledge Base"

    def test_upload_document(self, auth_token):
        """测试上传文档"""
        # 先创建知识库
        kb_response = client.post(
            "/api/knowledge/bases",
            json={
                "name": "Test KB",
                "description": "Test"
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        kb_id = kb_response.json()["kb_id"]

        # 上传文档
        with open("tests/fixtures/test_document.txt", "rb") as f:
            response = client.post(
                f"/api/knowledge/bases/{kb_id}/documents",
                files={"file": ("test.txt", f, "text/plain")},
                headers={"Authorization": f"Bearer {auth_token}"}
            )
        assert response.status_code == 200
        data = response.json()
        assert "document_id" in data

    def test_search_knowledge(self, auth_token):
        """测试知识库搜索"""
        # 先创建知识库
        kb_response = client.post(
            "/api/knowledge/bases",
            json={
                "name": "Test KB",
                "description": "Test"
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        kb_id = kb_response.json()["kb_id"]

        # 搜索
        response = client.get(
            f"/api/knowledge/bases/{kb_id}/search",
            params={"query": "test", "limit": 5},
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert isinstance(data["results"], list)


class TestToolsAPI:
    """工具API测试"""

    @pytest.fixture
    def auth_token(self):
        """获取认证token"""
        token = create_access_token(data={"sub": "test_user_123"})
        return token

    def test_execute_python_code(self, auth_token):
        """测试执行Python代码"""
        response = client.post(
            "/api/tools/python/execute",
            json={
                "code": "print('Hello, World!')\nresult = 2 + 2",
                "timeout": 5
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "output" in data
        assert "Hello, World!" in data["output"]
        assert "result = 4" in data["output"]

    def test_execute_sql_query(self, auth_token):
        """测试执行SQL查询"""
        response = client.post(
            "/api/tools/sql/execute",
            json={
                "query": "SELECT 1 as test_value",
                "database": "test"
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 1
        assert data["results"][0]["test_value"] == 1

    def test_invalid_python_code(self, auth_token):
        """测试无效Python代码"""
        response = client.post(
            "/api/tools/python/execute",
            json={
                "code": "invalid syntax !!!",
                "timeout": 5
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 400
        data = response.json()
        assert "error" in data


class TestRBACAPI:
    """RBAC权限API测试"""

    @pytest.fixture
    def admin_token(self):
        """获取管理员token"""
        token = create_access_token(data={"sub": "admin_user", "roles": ["admin"]})
        return token

    def test_list_roles(self, admin_token):
        """测试列出角色"""
        response = client.get(
            "/api/roles",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # 应该包含预定义角色
        role_names = [role["name"] for role in data]
        assert "super_admin" in role_names
        assert "admin" in role_names

    def test_create_custom_role(self, admin_token):
        """测试创建自定义角色"""
        response = client.post(
            "/api/roles",
            json={
                "name": "test_role",
                "description": "A test role",
                "permissions": ["user:read", "chat:write"]
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "test_role" in data["message"]

    def test_assign_role_to_user(self, admin_token):
        """测试分配角色给用户"""
        response = client.post(
            "/api/users/test_user/roles",
            json={
                "user_id": "test_user",
                "role_name": "viewer"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_check_permission(self, admin_token):
        """测试检查权限"""
        response = client.get(
            "/api/check?user_id=admin_user&permission=user:admin",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "has_permission" in data
        assert data["has_permission"] is True


class TestOrchestrationAPI:
    """编排系统API测试"""

    @pytest.fixture
    def auth_token(self):
        """获取认证token"""
        token = create_access_token(data={"sub": "test_user_123"})
        return token

    def test_submit_task(self, auth_token):
        """测试提交任务"""
        response = client.post(
            "/api/orchestration/tasks",
            json={
                "type": "conversation",
                "description": "Test conversation task",
                "input_data": {"message": "Hello"},
                "priority": "normal"
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    def test_get_task_status(self, auth_token):
        """测试获取任务状态"""
        # 先提交任务
        submit_response = client.post(
            "/api/orchestration/tasks",
            json={
                "type": "conversation",
                "description": "Test task",
                "input_data": {"message": "Hello"}
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        task_id = submit_response.json()["task_id"]

        # 获取任务状态
        response = client.get(
            f"/api/orchestration/tasks/{task_id}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == task_id
        assert "status" in data

    def test_list_agents(self, auth_token):
        """测试列出代理"""
        response = client.get(
            "/api/orchestration/agents",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 403  # 需要系统监控权限

    def test_get_system_metrics(self, auth_token):
        """测试获取系统指标"""
        response = client.get(
            "/api/orchestration/metrics",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_tasks" in data
        assert "active_agents" in data


class TestMonitoringAPI:
    """监控API测试"""

    @pytest.fixture
    def auth_token(self):
        """获取认证token"""
        token = create_access_token(
            data={
                "sub": "test_user_123",
                "permissions": ["system:monitor"]
            }
        )
        return token

    def test_get_metrics_summary(self, auth_token):
        """测试获取指标摘要"""
        response = client.get(
            "/api/monitoring/metrics/summary",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        # 应该包含系统指标
        assert "system_cpu_usage" in data or "system_memory_usage" in data

    def test_get_active_alerts(self, auth_token):
        """测试获取活跃告警"""
        response = client.get(
            "/api/monitoring/alerts",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_chart_data(self, auth_token):
        """测试获取图表数据"""
        response = client.get(
            "/api/monitoring/charts/data",
            params={
                "metric_name": "system_cpu_usage",
                "window": "1h"
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "metric" in data
        assert "data_points" in data
        assert isinstance(data["data_points"], list)


class TestHealthCheck:
    """健康检查测试"""

    def test_health_endpoint(self):
        """测试健康检查端点"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "version" in data

    def test_root_endpoint(self):
        """测试根端点"""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])