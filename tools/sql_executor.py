"""
SQL执行器

提供安全的SQL查询执行功能。
"""

import re
import time
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text, create_engine, inspect
from sqlalchemy.exc import SQLAlchemyError, OperationalError, ProgrammingError
from sqlalchemy.engine import ResultProxy

from config.database import db_settings
from config.logging import get_logger

logger = get_logger(__name__)


class SQLValidator:
    """SQL验证器"""

    # 危险的SQL关键字
    DANGEROUS_KEYWORDS = [
        "DROP", "DELETE", "TRUNCATE", "ALTER", "CREATE", "INSERT",
        "UPDATE", "GRANT", "REVOKE", "COMMIT", "ROLLBACK", "SAVEPOINT",
        "EXEC", "EXECUTE", "CALL", "MERGE", "REPLACE", "LOAD DATA",
        "LOAD XML", "SELECT INTO", "BULK INSERT", "UNION", "UNION ALL",
    ]

    # 允许的SQL操作
    ALLOWED_OPERATIONS = ["SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN"]

    @staticmethod
    def validate(sql: str) -> Dict[str, Any]:
        """
        验证SQL语句

        Args:
            sql: SQL语句

        Returns:
            验证结果
        """
        try:
            # 去除注释
            sql_no_comments = SQLValidator._remove_comments(sql)

            # 检查是否只包含SELECT语句
            sql_upper = sql_no_comments.upper().strip()

            # 检查是否以允许的操作开始
            has_allowed = any(sql_upper.startswith(op) for op in SQLValidator.ALLOWED_OPERATIONS)

            if not has_allowed:
                return {
                    "valid": False,
                    "error": f"只允许使用以下操作: {', '.join(SQLValidator.ALLOWED_OPERATIONS)}",
                    "detected_operation": SQLValidator._extract_operation(sql_upper),
                }

            # 检查危险关键字
            found_dangerous = []
            for keyword in SQLValidator.DANGEROUS_KEYWORDS:
                # 使用正则表达式检查完整的单词
                pattern = r'\b' + re.escape(keyword) + r'\b'
                if re.search(pattern, sql_upper, re.IGNORECASE):
                    found_dangerous.append(keyword)

            if found_dangerous:
                return {
                    "valid": False,
                    "error": f"SQL语句包含危险操作: {', '.join(found_dangerous)}",
                    "dangerous_keywords": found_dangerous,
                }

            # 检查语法（基本检查）
            try:
                # 使用SQLAlchemy解析
                text(sql)
            except Exception as e:
                return {
                    "valid": False,
                    "error": f"SQL语法错误: {str(e)}",
                }

            return {
                "valid": True,
                "error": None,
                "operation": SQLValidator._extract_operation(sql_upper),
            }

        except Exception as e:
            return {
                "valid": False,
                "error": f"验证失败: {str(e)}",
            }

    @staticmethod
    def _remove_comments(sql: str) -> str:
        """移除SQL注释"""
        # 移除单行注释
        sql = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)
        # 移除多行注释
        sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
        return sql.strip()

    @staticmethod
    def _extract_operation(sql: str) -> str:
        """提取SQL操作类型"""
        for op in SQLValidator.ALLOWED_OPERATIONS:
            if sql.startswith(op):
                return op
        return "UNKNOWN"


class SQLFormatter:
    """SQL格式化器"""

    @staticmethod
    def format(sql: str) -> str:
        """
        格式化SQL语句

        Args:
            sql: SQL语句

        Returns:
            格式化后的SQL
        """
        try:
            import sqlparse
            # 格式化SQL
            formatted = sqlparse.format(sql, reindent=True, keyword_case='upper')
            return formatted
        except ImportError:
            logger.warning("sqlparse未安装，返回原始SQL")
            return sql
        except Exception as e:
            logger.error(f"SQL格式化失败: {str(e)}")
            return sql

    @staticmethod
    def prettify_query_plan(plan: str) -> str:
        """
        美化查询计划

        Args:
            plan: 查询计划

        Returns:
            美化后的查询计划
        """
        # 简单的美化处理
        lines = plan.split('\n')
        pretty_lines = []
        indent = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            if stripped.startswith('->'):
                pretty_lines.append('  ' * indent + stripped)
                indent += 1
            elif stripped.endswith((')', ']')):
                indent -= 1
                pretty_lines.append('  ' * indent + stripped)
            else:
                pretty_lines.append('  ' * indent + stripped)

        return '\n'.join(pretty_lines)


class SQLExecutor:
    """SQL执行器"""

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or db_settings.database_url
        self.engine = create_engine(
            self.db_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        self.validator = SQLValidator()
        self.formatter = SQLFormatter()

    async def execute(
        self,
        sql: str,
        parameters: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        limit: Optional[int] = 1000,
    ) -> Dict[str, Any]:
        """
        执行SQL查询

        Args:
            sql: SQL语句
            parameters: 参数
            timeout: 超时时间
            limit: 结果数量限制

        Returns:
            执行结果
        """
        # 验证SQL
        validation = self.validator.validate(sql)
        if not validation["valid"]:
            return {
                "success": False,
                "error": validation["error"],
                "data": None,
                "execution_time": 0,
                "row_count": 0,
            }

        # 添加LIMIT子句（如果需要）
        if limit and "LIMIT" not in sql.upper():
            if sql.strip().upper().startswith("SELECT"):
                sql = f"{sql.rstrip(';')} LIMIT {limit}"

        try:
            start_time = time.time()

            # 执行查询
            with self.engine.connect() as conn:
                # 设置查询超时
                if timeout:
                    conn.execute(text(f"SET SESSION max_execution_time = {int(timeout * 1000)}"))

                result = conn.execute(text(sql), parameters or {})

                # 获取结果
                if result.returns_rows:
                    # 查询语句
                    rows = result.fetchmany(limit or 1000)
                    data = [dict(row._mapping) for row in rows]
                    row_count = len(data)
                else:
                    # 非查询语句
                    data = None
                    row_count = result.rowcount

                execution_time = time.time() - start_time

                return {
                    "success": True,
                    "error": None,
                    "data": data,
                    "execution_time": execution_time,
                    "row_count": row_count,
                    "columns": list(data[0].keys()) if data else [],
                }

        except OperationalError as e:
            logger.error(f"SQL操作错误: {str(e)}")
            return {
                "success": False,
                "error": f"操作失败: {str(e)}",
                "data": None,
                "execution_time": time.time() - start_time if 'start_time' in locals() else 0,
                "row_count": 0,
            }

        except ProgrammingError as e:
            logger.error(f"SQL编程错误: {str(e)}")
            return {
                "success": False,
                "error": f"SQL错误: {str(e)}",
                "data": None,
                "execution_time": time.time() - start_time if 'start_time' in locals() else 0,
                "row_count": 0,
            }

        except SQLAlchemyError as e:
            logger.error(f"SQL执行错误: {str(e)}")
            return {
                "success": False,
                "error": f"数据库错误: {str(e)}",
                "data": None,
                "execution_time": time.time() - start_time if 'start_time' in locals() else 0,
                "row_count": 0,
            }

        except Exception as e:
            logger.error(f"未知错误: {str(e)}")
            return {
                "success": False,
                "error": f"未知错误: {str(e)}",
                "data": None,
                "execution_time": time.time() - start_time if 'start_time' in locals() else 0,
                "row_count": 0,
            }

    async def explain(
        self,
        sql: str,
        parameters: Optional[Dict[str, Any]] = None,
        analyze: bool = False,
    ) -> Dict[str, Any]:
        """
        执行查询计划

        Args:
            sql: SQL语句
            parameters: 参数
            analyze: 是否执行并分析

        Returns:
            查询计划
        """
        try:
            # 构建EXPLAIN语句
            if analyze:
                explain_sql = f"EXPLAIN ANALYZE {sql}"
            else:
                explain_sql = f"EXPLAIN {sql}"

            result = await self.execute(explain_sql, parameters)

            if result["success"]:
                # 美化查询计划
                plan_text = "\n".join([str(row) for row in result["data"]])
                pretty_plan = self.formatter.prettify_query_plan(plan_text)

                return {
                    "success": True,
                    "error": None,
                    "plan": pretty_plan,
                    "raw_plan": result["data"],
                }
            else:
                return {
                    "success": False,
                    "error": result["error"],
                    "plan": None,
                    "raw_plan": None,
                }

        except Exception as e:
            logger.error(f"查询计划失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "plan": None,
                "raw_plan": None,
            }

    async def get_schema_info(
        self,
        table_name: Optional[str] = None,
        include_sample: bool = False,
        sample_size: int = 5,
    ) -> Dict[str, Any]:
        """
        获取数据库模式信息

        Args:
            table_name: 表名（可选）
            include_sample: 是否包含示例数据
            sample_size: 示例数据大小

        Returns:
            模式信息
        """
        try:
            inspector = inspect(self.engine)

            # 获取所有表
            tables = inspector.get_table_names() if not table_name else [table_name]

            schema_info = {
                "database": self.engine.url.database,
                "tables": {},
            }

            for table in tables:
                # 获取列信息
                columns = inspector.get_columns(table)

                # 获取主键
                primary_keys = inspector.get_pk_constraint(table)

                # 获取外键
                foreign_keys = inspector.get_foreign_keys(table)

                # 获取索引
                indexes = inspector.get_indexes(table)

                # 构建表信息
                table_info = {
                    "name": table,
                    "columns": columns,
                    "primary_keys": primary_keys,
                    "foreign_keys": foreign_keys,
                    "indexes": indexes,
                }

                # 获取示例数据
                if include_sample:
                    sample_result = await self.execute(
                        f"SELECT * FROM {table} LIMIT {sample_size}"
                    )
                    table_info["sample_data"] = sample_result.get("data", [])

                schema_info["tables"][table] = table_info

            return {
                "success": True,
                "error": None,
                "schema": schema_info,
            }

        except Exception as e:
            logger.error(f"获取模式信息失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "schema": None,
            }

    async def validate_and_format(self, sql: str) -> Dict[str, Any]:
        """
        验证并格式化SQL

        Args:
            sql: SQL语句

        Returns:
            验证和格式化结果
        """
        # 验证SQL
        validation = self.validator.validate(sql)

        # 格式化SQL
        formatted_sql = self.formatter.format(sql)

        return {
            "validation": validation,
            "formatted_sql": formatted_sql,
        }

    async def get_suggestions(
        self,
        partial_query: str,
        limit: int = 10,
    ) -> List[str]:
        """
        获取SQL建议

        Args:
            partial_query: 部分查询
            limit: 建议数量限制

        Returns:
            建议列表
        """
        suggestions = []

        # 基于关键字的简单建议
        query_upper = partial_query.upper()

        # 表名建议
        try:
            inspector = inspect(self.engine)
            tables = inspector.get_table_names()

            if "FROM" in query_upper and not query_upper.endswith("FROM"):
                suggestions.extend([f" {table}" for table in tables])

            # 列名建议（如果有表名）
            last_table = None
            # 简单解析最后一个表名
            from_match = re.search(r'FROM\s+(\w+)', query_upper)
            if from_match:
                last_table = from_match.group(1)

            if last_table and "WHERE" not in query_upper:
                try:
                    columns = inspector.get_columns(last_table)
                    suggestions.extend([f" {col['name']}" for col in columns])
                except:
                    pass

        except Exception:
            pass

        # 关键字建议
        keywords = ["WHERE", "GROUP BY", "ORDER BY", "HAVING", "LIMIT", "JOIN"]
        for keyword in keywords:
            if keyword not in query_upper:
                suggestions.append(f" {keyword}")

        # 去重并限制数量
        suggestions = list(set(suggestions))[:limit]

        return suggestions

    def close(self):
        """关闭数据库连接"""
        if self.engine:
            self.engine.dispose()