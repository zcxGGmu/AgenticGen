-- AgenticGen数据库初始化脚本

-- 设置字符集
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS agenticgen DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE agenticgen;

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE COMMENT '用户名',
    email VARCHAR(100) NOT NULL UNIQUE COMMENT '邮箱',
    password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希',
    full_name VARCHAR(100) COMMENT '全名',
    avatar_url VARCHAR(500) COMMENT '头像URL',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    is_superuser BOOLEAN DEFAULT FALSE COMMENT '是否超级用户',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    last_login TIMESTAMP NULL COMMENT '最后登录时间',
    login_count INT DEFAULT 0 COMMENT '登录次数',
    settings JSON COMMENT '用户设置',
    INDEX idx_username (username),
    INDEX idx_email (email),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';

-- API密钥表
CREATE TABLE IF NOT EXISTS api_keys (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL COMMENT '用户ID',
    key_name VARCHAR(100) NOT NULL COMMENT '密钥名称',
    api_key VARCHAR(255) NOT NULL UNIQUE COMMENT 'API密钥',
    prefix VARCHAR(20) NOT NULL COMMENT '密钥前缀',
    permissions JSON COMMENT '权限列表',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    expires_at TIMESTAMP NULL COMMENT '过期时间',
    last_used TIMESTAMP NULL COMMENT '最后使用时间',
    usage_count INT DEFAULT 0 COMMENT '使用次数',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_api_key (api_key),
    INDEX idx_prefix (prefix),
    INDEX idx_expires_at (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='API密钥表';

-- 知识库表
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL COMMENT '用户ID',
    name VARCHAR(200) NOT NULL COMMENT '知识库名称',
    description TEXT COMMENT '描述',
    embedding_model VARCHAR(100) DEFAULT 'text-embedding-ada-002' COMMENT '嵌入模型',
    dimension INT DEFAULT 1536 COMMENT '向量维度',
    total_documents INT DEFAULT 0 COMMENT '文档总数',
    total_chunks INT DEFAULT 0 COMMENT '总块数',
    metadata JSON COMMENT '元数据',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_name (name),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知识库表';

-- 文档信息表
CREATE TABLE IF NOT EXISTS file_info (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL COMMENT '用户ID',
    kb_id INT COMMENT '知识库ID',
    filename VARCHAR(255) NOT NULL COMMENT '文件名',
    original_filename VARCHAR(255) NOT NULL COMMENT '原始文件名',
    file_path VARCHAR(500) NOT NULL COMMENT '文件路径',
    file_size INT NOT NULL COMMENT '文件大小（字节）',
    file_type VARCHAR(50) NOT NULL COMMENT '文件类型',
    mime_type VARCHAR(100) COMMENT 'MIME类型',
    md5_hash VARCHAR(32) COMMENT 'MD5哈希',
    sha256_hash VARCHAR(64) COMMENT 'SHA256哈希',
    status ENUM('uploading', 'processing', 'completed', 'failed') DEFAULT 'uploading' COMMENT '状态',
    error_message TEXT COMMENT '错误信息',
    processing_progress INT DEFAULT 0 COMMENT '处理进度',
    metadata JSON COMMENT '元数据',
    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '上传时间',
    processed_time TIMESTAMP NULL COMMENT '处理完成时间',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id) ON DELETE SET NULL,
    INDEX idx_user_id (user_id),
    INDEX idx_kb_id (kb_id),
    INDEX idx_filename (filename),
    INDEX idx_md5_hash (md5_hash),
    INDEX idx_status (status),
    INDEX idx_upload_time (upload_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文件信息表';

-- 聊天线程表
CREATE TABLE IF NOT EXISTS threads (
    id INT AUTO_INCREMENT PRIMARY KEY,
    thread_id VARCHAR(100) NOT NULL UNIQUE COMMENT '线程ID',
    user_id INT NOT NULL COMMENT '用户ID',
    agent_type ENUM('general', 'coding', 'data_analysis', 'sql', 'knowledge') DEFAULT 'general' COMMENT '代理类型',
    kb_id INT COMMENT '关联知识库ID',
    title VARCHAR(200) COMMENT '标题',
    metadata JSON COMMENT '元数据',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id) ON DELETE SET NULL,
    INDEX idx_thread_id (thread_id),
    INDEX idx_user_id (user_id),
    INDEX idx_agent_type (agent_type),
    INDEX idx_kb_id (kb_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='聊天线程表';

-- 消息表
CREATE TABLE IF NOT EXISTS messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    thread_id VARCHAR(100) NOT NULL COMMENT '线程ID',
    user_id INT NOT NULL COMMENT '用户ID',
    role ENUM('user', 'assistant', 'system') NOT NULL COMMENT '角色',
    content LONGTEXT COMMENT '消息内容',
    metadata JSON COMMENT '元数据',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_thread_id (thread_id),
    INDEX idx_user_id (user_id),
    INDEX idx_role (role),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='消息表';

-- 会话缓存表
CREATE TABLE IF NOT EXISTS session_cache (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL UNIQUE COMMENT '会话ID',
    user_id INT NOT NULL COMMENT '用户ID',
    data JSON NOT NULL COMMENT '会话数据',
    expires_at TIMESTAMP NOT NULL COMMENT '过期时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_session_id (session_id),
    INDEX idx_user_id (user_id),
    INDEX idx_expires_at (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='会话缓存表';

-- 创建默认超级用户（密码：admin123）
INSERT IGNORE INTO users (
    id, username, email, password_hash, full_name, is_superuser
) VALUES (
    1,
    'admin',
    'admin@agenticgen.com',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj3bp.Gm.F5e',
    'System Administrator',
    TRUE
);

-- 创建默认API密钥
INSERT IGNORE INTO api_keys (
    user_id, key_name, api_key, prefix, permissions
) VALUES (
    1,
    'Default API Key',
    'sk-AGenticGen-1234567890abcdef',
    'AGenticGen',
    JSON_ARRAY('*')
);

SET FOREIGN_KEY_CHECKS = 1;