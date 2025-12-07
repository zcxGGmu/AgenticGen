"""
加密解密功能

提供AES加密解密、哈希计算等加密相关功能。
"""

import base64
import hashlib
import secrets
from typing import Optional, Tuple

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from jose import JWTError, jwt

from config import settings
from config.logging import get_logger

logger = get_logger(__name__)


class CryptoManager:
    """加密管理器"""

    def __init__(self):
        self.encryption_key = self._derive_encryption_key(settings.jwt_secret_key)
        self.jwt_algorithm = settings.jwt_algorithm
        self.jwt_expire_minutes = settings.jwt_access_token_expire_minutes

    def _derive_encryption_key(self, secret: str) -> bytes:
        """
        从密钥派生加密密钥

        Args:
            secret: 原始密钥

        Returns:
            派生的加密密钥
        """
        return hashlib.sha256(secret.encode()).digest()

    def encrypt(self, plaintext: str) -> str:
        """
        加密文本

        Args:
            plaintext: 明文

        Returns:
            Base64编码的密文
        """
        try:
            # 生成随机IV
            iv = secrets.token_bytes(AES.block_size)

            # 创建加密器
            cipher = AES.new(self.encryption_key, AES.MODE_CBC, iv)

            # 加密数据
            padded_data = pad(plaintext.encode(), AES.block_size)
            ciphertext = cipher.encrypt(padded_data)

            # 组合IV和密文
            encrypted_data = iv + ciphertext

            # Base64编码
            return base64.b64encode(encrypted_data).decode()
        except Exception as e:
            logger.error(f"加密失败: {str(e)}")
            raise ValueError("加密失败")

    def decrypt(self, ciphertext: str) -> str:
        """
        解密文本

        Args:
            ciphertext: Base64编码的密文

        Returns:
            明文
        """
        try:
            # Base64解码
            encrypted_data = base64.b64decode(ciphertext)

            # 提取IV
            iv = encrypted_data[:AES.block_size]
            ciphertext_bytes = encrypted_data[AES.block_size:]

            # 创建解密器
            cipher = AES.new(self.encryption_key, AES.MODE_CBC, iv)

            # 解密数据
            padded_data = cipher.decrypt(ciphertext_bytes)
            plaintext = unpad(padded_data, AES.block_size)

            return plaintext.decode()
        except Exception as e:
            logger.error(f"解密失败: {str(e)}")
            raise ValueError("解密失败")

    def generate_jwt_token(self, payload: dict) -> str:
        """
        生成JWT令牌

        Args:
            payload: 令牌载荷

        Returns:
            JWT令牌
        """
        try:
            # 添加过期时间
            from datetime import datetime, timedelta
            expire = datetime.utcnow() + timedelta(minutes=self.jwt_expire_minutes)
            payload.update({"exp": expire})

            # 生成令牌
            token = jwt.encode(payload, settings.jwt_secret_key, algorithm=self.jwt_algorithm)
            return token
        except Exception as e:
            logger.error(f"生成JWT令牌失败: {str(e)}")
            raise ValueError("生成令牌失败")

    def verify_jwt_token(self, token: str) -> dict:
        """
        验证JWT令牌

        Args:
            token: JWT令牌

        Returns:
            令牌载荷
        """
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[self.jwt_algorithm]
            )
            return payload
        except JWTError as e:
            logger.error(f"JWT令牌验证失败: {str(e)}")
            raise ValueError("无效的令牌")

    def hash_password(self, password: str, salt: Optional[str] = None) -> Tuple[str, str]:
        """
        哈希密码

        Args:
            password: 密码
            salt: 盐值（可选）

        Returns:
            (哈希值, 盐值)
        """
        if salt is None:
            salt = secrets.token_hex(16)

        # 使用PBKDF2进行密码哈希
        hash_value = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode(),
            salt.encode(),
            100000  # 迭代次数
        )

        return hash_value.hex(), salt

    def verify_password(self, password: str, hash_value: str, salt: str) -> bool:
        """
        验证密码

        Args:
            password: 密码
            hash_value: 哈希值
            salt: 盐值

        Returns:
            验证结果
        """
        computed_hash, _ = self.hash_password(password, salt)
        return secrets.compare_digest(computed_hash, hash_value)

    def generate_api_key(self) -> str:
        """
        生成API密钥

        Returns:
            API密钥
        """
        return secrets.token_urlsafe(32)

    def generate_session_id(self) -> str:
        """
        生成会话ID

        Returns:
            会话ID
        """
        return secrets.token_urlsafe(32)

    def generate_random_string(self, length: int = 32) -> str:
        """
        生成随机字符串

        Args:
            length: 字符串长度

        Returns:
            随机字符串
        """
        return secrets.token_urlsafe(length)


# 创建全局加密管理器实例
_crypto_manager = None


def get_crypto_manager() -> CryptoManager:
    """获取加密管理器实例（单例模式）"""
    global _crypto_manager
    if _crypto_manager is None:
        _crypto_manager = CryptoManager()
    return _crypto_manager