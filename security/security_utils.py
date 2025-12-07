"""
安全工具模块
提供加密、解密、令牌生成等安全功能
"""

import hashlib
import hmac
import secrets
import time
import jwt
from typing import Optional, Dict, Any, Tuple
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import logging

from config.config import settings

logger = logging.getLogger(__name__)

class EncryptionManager:
    """加密管理器"""

    def __init__(self, key: Optional[bytes] = None):
        if key:
            self.key = key
        else:
            self.key = self._generate_key()

        self.cipher_suite = Fernet(self.key)

    @staticmethod
    def _generate_key(password: str = None) -> bytes:
        """生成加密密钥"""
        if password is None:
            password = settings.JWT_SECRET_KEY.encode()

        # 使用PBKDF2从密码生成密钥
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'agenticgen_salt',  # 在生产环境中应该使用随机盐
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        return key

    def encrypt(self, data: str) -> str:
        """加密数据"""
        try:
            encrypted_data = self.cipher_suite.encrypt(data.encode())
            return base64.urlsafe_b64encode(encrypted_data).decode()
        except Exception as e:
            logger.error(f"Encryption failed: {str(e)}")
            raise

    def decrypt(self, encrypted_data: str) -> str:
        """解密数据"""
        try:
            decoded_data = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted_data = self.cipher_suite.decrypt(decoded_data)
            return decrypted_data.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {str(e)}")
            raise

class TokenManager:
    """令牌管理器"""

    def __init__(self):
        self.secret_key = settings.JWT_SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.access_token_expire_minutes = settings.JWT_EXPIRE_MINUTES

    def generate_access_token(self, data: Dict[str, Any]) -> str:
        """生成访问令牌"""
        to_encode = data.copy()
        expire = time.time() + self.access_token_expire_minutes * 60
        to_encode.update({"exp": expire, "type": "access"})

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def generate_refresh_token(self, data: Dict[str, Any]) -> str:
        """生成刷新令牌"""
        to_encode = data.copy()
        expire = time.time() + self.access_token_expire_minutes * 60 * 24 * 7  # 7天
        to_encode.update({"exp": expire, "type": "refresh"})

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """验证令牌"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.JWTError as e:
            logger.warning(f"Token validation failed: {str(e)}")
            return None

    def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """使用刷新令牌生成新的访问令牌"""
        payload = self.verify_token(refresh_token)

        if not payload or payload.get("type") != "refresh":
            return None

        # 移除过期时间，创建新的访问令牌
        payload.pop("exp", None)
        payload.pop("type", None)

        return self.generate_access_token(payload)

class PasswordManager:
    """密码管理器"""

    def __init__(self):
        self.pbkdf2_iterations = 100000

    def hash_password(self, password: str, salt: Optional[str] = None) -> Tuple[str, str]:
        """
        对密码进行哈希

        Returns:
            (hashed_password, salt)
        """
        if salt is None:
            salt = secrets.token_hex(32)

        # 使用PBKDF2哈希密码
        pwdhash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            self.pbkdf2_iterations
        )

        return pwdhash.hex(), salt

    def verify_password(self, password: str, hashed: str, salt: str) -> bool:
        """验证密码"""
        test_hash, _ = self.hash_password(password, salt)
        return hmac.compare_digest(test_hash, hashed)

    def generate_password(self, length: int = 16) -> str:
        """生成随机密码"""
        alphabet = (
            "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789"
            "!@#$%^&*()_+-=[]{}|"
        )
        return ''.join(secrets.choice(alphabet) for _ in range(length))

class APIKeyManager:
    """API密钥管理器"""

    def __init__(self):
        self.encryption_manager = EncryptionManager()

    def generate_api_key(self, user_id: int, key_name: str) -> Tuple[str, str]:
        """
        生成API密钥

        Returns:
            (api_key, key_prefix)
        """
        # 生成唯一的密钥ID
        key_id = secrets.token_urlsafe(16)

        # 生成密钥
        key_secret = secrets.token_urlsafe(32)
        api_key = f"ag_{key_id}_{key_secret}"

        # 生成前缀（用于快速查找）
        key_prefix = f"ag_{key_id[:8]}"

        # 加密存储
        encrypted_data = self.encryption_manager.encrypt(
            f"{user_id}:{key_name}:{time.time()}"
        )

        # 在实际应用中，应该将加密数据存储到数据库
        logger.info(f"Generated API key {key_prefix} for user {user_id}")

        return api_key, key_prefix

    def verify_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """验证API密钥"""
        try:
            # 解析API密钥
            parts = api_key.split('_')
            if len(parts) != 3 or parts[0] != "ag":
                return None

            key_id = parts[1]
            key_secret = parts[2]

            # 在实际应用中，应该从数据库查询并验证
            # 这里返回模拟数据
            return {
                "key_id": key_id,
                "valid": True,
                "user_id": 1,  # 应该从数据库获取
                "key_name": "test_key"
            }

        except Exception as e:
            logger.error(f"API key verification failed: {str(e)}")
            return None

class SecurityValidator:
    """安全验证器"""

    @staticmethod
    def validate_password_strength(password: str) -> Dict[str, Any]:
        """验证密码强度"""
        result = {
            "valid": True,
            "score": 0,
            "issues": []
        }

        # 长度检查
        if len(password) < 8:
            result["valid"] = False
            result["issues"].append("密码长度至少8位")
        else:
            result["score"] += 1

        # 包含大写字母
        if not any(c.isupper() for c in password):
            result["issues"].append("建议包含大写字母")
        else:
            result["score"] += 1

        # 包含小写字母
        if not any(c.islower() for c in password):
            result["issues"].append("建议包含小写字母")
        else:
            result["score"] += 1

        # 包含数字
        if not any(c.isdigit() for c in password):
            result["issues"].append("建议包含数字")
        else:
            result["score"] += 1

        # 包含特殊字符
        if not any(c in "!@#$%^&*()_+-=[]{}|;:'\",.<>?/" for c in password):
            result["issues"].append("建议包含特殊字符")
        else:
            result["score"] += 1

        # 计算强度等级
        if result["score"] >= 4:
            result["strength"] = "强"
        elif result["score"] >= 3:
            result["strength"] = "中等"
        else:
            result["strength"] = "弱"
            result["valid"] = False

        return result

    @staticmethod
    def validate_email(email: str) -> bool:
        """验证邮箱格式"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None

    @staticmethod
    def sanitize_input(input_string: str, max_length: int = 1000) -> str:
        """清理输入字符串"""
        if not input_string:
            return ""

        # 限制长度
        if len(input_string) > max_length:
            input_string = input_string[:max_length]

        # 移除潜在的恶意字符
        dangerous_chars = ['<', '>', '"', "'", '&', '\x00']
        for char in dangerous_chars:
            input_string = input_string.replace(char, '')

        return input_string.strip()

    @staticmethod
    def generate_csrf_token() -> str:
        """生成CSRF令牌"""
        return secrets.token_urlsafe(32)

    @staticmethod
    def verify_csrf_token(token: str, expected_token: str) -> bool:
        """验证CSRF令牌"""
        return hmac.compare_digest(token, expected_token)

class SecurityAuditor:
    """安全审计器"""

    def __init__(self):
        self.encryption_manager = EncryptionManager()

    def audit_sensitive_data(self, data: Any, field_name: str) -> bool:
        """审计敏感数据是否正确处理"""
        sensitive_patterns = [
            r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',  # 信用卡号
            r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # 邮箱
        ]

        data_str = str(data)

        import re
        for pattern in sensitive_patterns:
            if re.search(pattern, data_str):
                logger.warning(f"Potential sensitive data detected in field: {field_name}")
                return False

        return True

    def encrypt_sensitive_field(self, value: str) -> str:
        """加密敏感字段"""
        if not value:
            return ""
        return self.encryption_manager.encrypt(value)

    def decrypt_sensitive_field(self, encrypted_value: str) -> str:
        """解密敏感字段"""
        if not encrypted_value:
            return ""
        return self.encryption_manager.decrypt(encrypted_value)

# 全局实例
encryption_manager = EncryptionManager()
token_manager = TokenManager()
password_manager = PasswordManager()
api_key_manager = APIKeyManager()
security_validator = SecurityValidator()
security_auditor = SecurityAuditor()

# 便捷函数
def hash_password(password: str) -> Tuple[str, str]:
    """哈希密码（便捷函数）"""
    return password_manager.hash_password(password)

def verify_password(password: str, hashed: str, salt: str) -> bool:
    """验证密码（便捷函数）"""
    return password_manager.verify_password(password, hashed, salt)

def generate_token(data: Dict[str, Any]) -> str:
    """生成令牌（便捷函数）"""
    return token_manager.generate_access_token(data)

def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """验证令牌（便捷函数）"""
    return token_manager.verify_token(token)