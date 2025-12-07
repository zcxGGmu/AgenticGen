"""
数据库索引优化脚本
根据优化方案添加必要的索引以提升查询性能
"""

from sqlalchemy import text
from db.connection import get_db_session

# 索引定义
INDEXES = [
    # 用户相关索引
    {
        "name": "idx_users_email_active",
        "table": "users",
        "columns": ["email", "is_active"],
        "description": "用户邮箱和状态联合索引"
    },
    {
        "name": "idx_users_created_at",
        "table": "users",
        "columns": ["created_at"],
        "description": "用户创建时间索引"
    },

    # API密钥索引
    {
        "name": "idx_api_keys_user_active",
        "table": "api_keys",
        "columns": ["user_id", "is_active"],
        "description": "API密钥用户和状态联合索引"
    },
    {
        "name": "idx_api_keys_prefix",
        "table": "api_keys",
        "columns": ["prefix"],
        "description": "API密钥前缀索引"
    },
    {
        "name": "idx_api_keys_expires",
        "table": "api_keys",
        "columns": ["expires_at"],
        "description": "API密钥过期时间索引"
    },

    # 知识库索引
    {
        "name": "idx_kb_user_active",
        "table": "knowledge_bases",
        "columns": ["user_id", "is_active"],
        "description": "知识库用户和状态联合索引"
    },
    {
        "name": "idx_kb_name",
        "table": "knowledge_bases",
        "columns": ["name"],
        "description": "知识库名称索引"
    },

    # 文件信息索引
    {
        "name": "idx_files_user_status_time",
        "table": "file_info",
        "columns": ["user_id", "status", "upload_time"],
        "description": "文件用户、状态和上传时间联合索引"
    },
    {
        "name": "idx_files_kb_status",
        "table": "file_info",
        "columns": ["kb_id", "status"],
        "description": "文件知识库和状态联合索引"
    },
    {
        "name": "idx_files_md5",
        "table": "file_info",
        "columns": ["md5_hash"],
        "description": "文件MD5哈希索引"
    },
    {
        "name": "idx_files_upload_time",
        "table": "file_info",
        "columns": ["upload_time"],
        "description": "文件上传时间索引"
    },

    # 聊天线程索引
    {
        "name": "idx_threads_user_time",
        "table": "threads",
        "columns": ["user_id", "created_at"],
        "description": "线程用户和创建时间联合索引"
    },
    {
        "name": "idx_threads_agent_type",
        "table": "threads",
        "columns": ["agent_type"],
        "description": "线程代理类型索引"
    },
    {
        "name": "idx_threads_updated_at",
        "table": "threads",
        "columns": ["updated_at"],
        "description": "线程更新时间索引"
    },

    # 消息索引
    {
        "name": "idx_messages_thread_time",
        "table": "messages",
        "columns": ["thread_id", "created_at"],
        "description": "消息线程和时间联合索引"
    },
    {
        "name": "idx_messages_user_thread",
        "table": "messages",
        "columns": ["user_id", "thread_id"],
        "description": "消息用户和线程联合索引"
    },
    {
        "name": "idx_messages_role",
        "table": "messages",
        "columns": ["role"],
        "description": "消息角色索引"
    },

    # 会话缓存索引
    {
        "name": "idx_session_expires",
        "table": "session_cache",
        "columns": ["expires_at"],
        "description": "会话过期时间索引"
    },
    {
        "name": "idx_session_user",
        "table": "session_cache",
        "columns": ["user_id"],
        "description": "会话用户索引"
    }
]

def create_index(index_def):
    """创建单个索引"""
    columns_str = ", ".join(index_def["columns"])
    sql = f"""
    CREATE INDEX IF NOT EXISTS {index_def['name']}
    ON {index_def['table']} ({columns_str})
    """
    return sql

def check_index_exists(session, index_name):
    """检查索引是否存在"""
    sql = """
    SELECT COUNT(*) as count
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
    AND index_name = :index_name
    """
    result = session.execute(text(sql), {"index_name": index_name}).fetchone()
    return result.count > 0

def run_index_optimization():
    """执行索引优化"""
    with get_db_session() as session:
        print("开始数据库索引优化...")

        created_count = 0
        skipped_count = 0

        for index_def in INDEXES:
            if check_index_exists(session, index_def["name"]):
                print(f"✓ 索引 {index_def['name']} 已存在，跳过")
                skipped_count += 1
                continue

            try:
                sql = create_index(index_def)
                session.execute(text(sql))
                session.commit()
                print(f"✓ 创建索引: {index_def['name']} - {index_def['description']}")
                created_count += 1
            except Exception as e:
                print(f"✗ 创建索引失败 {index_def['name']}: {str(e)}")
                session.rollback()

        print(f"\n索引优化完成!")
        print(f"创建新索引: {created_count} 个")
        print(f"跳过已存在: {skipped_count} 个")

        # 分析表以更新统计信息
        print("\n正在更新表统计信息...")
        tables = ["users", "api_keys", "knowledge_bases", "file_info", "threads", "messages", "session_cache"]
        for table in tables:
            try:
                session.execute(text(f"ANALYZE TABLE {table}"))
                session.commit()
                print(f"✓ 更新统计信息: {table}")
            except Exception as e:
                print(f"✗ 更新统计信息失败 {table}: {str(e)}")

if __name__ == "__main__":
    run_index_optimization()