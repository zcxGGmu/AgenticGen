"""
身份验证核心

提供API密钥验证、用户身份识别等功能。
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session

from auth.crypto import get_crypto_manager
from db.models import SecretModel, UserSession
from db.database import get_db
from config import settings
from config.logging import get_logger

logger = get_logger(__name__)


class IdentityVerifier:
    """身份验证器"""

    def __init__(self):
        self.crypto_manager = get_crypto_manager()
        self.default_rate_limit = settings.rate_limit_requests
        self.rate_limit_window = settings.rate_limit_window

    def create_secret(
        self,
        user_id: str,
        secret_value: str,
        secret_type: str = "api_key",
        name: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        db: Optional[Session] = None,
    ) -> SecretModel:
        """
        创建密钥

        Args:
            user_id: 用户ID
            secret_value: 密钥值
            secret_type: 密钥类型
            name: 密钥名称
            expires_at: 过期时间
            db: 数据库会话

        Returns:
            密钥模型
        """
        if db is None:
            db = next(get_db())

        try:
            # 加密密钥值
            encrypted_value = self.crypto_manager.encrypt(secret_value)

            # 创建密钥记录
            secret = SecretModel(
                user_id=user_id,
                name=name or f"{secret_type}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                secret_value=encrypted_value,
                secret_type=secret_type,
                expires_at=expires_at,
                is_active=True,
            )

            db.add(secret)
            db.commit()
            db.refresh(secret)

            logger.info(f"创建密钥成功: {secret.id} for user {user_id}")
            return secret

        except Exception as e:
            db.rollback()
            logger.error(f"创建密钥失败: {str(e)}")
            raise

    def verify_secret(
        self,
        secret_value: str,
        secret_type: str = "api_key",
        db: Optional[Session] = None,
    ) -> Optional[SecretModel]:
        """
        验证密钥

        Args:
            secret_value: 密钥值
            secret_type: 密钥类型
            db: 数据库会话

        Returns:
            密钥模型（验证成功）或None（验证失败）
        """
        if db is None:
            db = next(get_db())

        try:
            # 查找所有激活的密钥
            secrets = db.query(SecretModel).filter(
                SecretModel.secret_type == secret_type,
                SecretModel.is_active == True,
            ).all()

            # 逐个验证密钥
            for secret in secrets:
                try:
                    # 解密并比较密钥值
                    decrypted_value = self.crypto_manager.decrypt(secret.secret_value)
                    if decrypted_value == secret_value:
                        # 检查是否过期
                        if secret.is_expired():
                            logger.warning(f"密钥已过期: {secret.id}")
                            continue

                        # 更新使用记录
                        secret.last_used_at = datetime.utcnow()
                        secret.usage_count += 1
                        db.commit()

                        logger.info(f"密钥验证成功: {secret.id}")
                        return secret

                except ValueError:
                    # 解密失败，继续下一个密钥
                    continue

            logger.warning(f"密钥验证失败: {secret_value[:10]}...")
            return None

        except Exception as e:
            logger.error(f"验证密钥时出错: {str(e)}")
            return None

    def create_user_session(
        self,
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session_data: Optional[Dict[str, Any]] = None,
        expires_hours: int = 24,
        db: Optional[Session] = None,
    ) -> UserSession:
        """
        创建用户会话

        Args:
            user_id: 用户ID
            ip_address: IP地址
            user_agent: 用户代理
            session_data: 会话数据
            expires_hours: 过期小时数
            db: 数据库会话

        Returns:
            会话模型
        """
        if db is None:
            db = next(get_db())

        try:
            session_id = self.crypto_manager.generate_session_id()
            expires_at = datetime.utcnow() + timedelta(hours=expires_hours)

            session = UserSession(
                session_id=session_id,
                user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent,
                session_data=session_data or {},
                is_active=True,
                expires_at=expires_at,
            )

            db.add(session)
            db.commit()
            db.refresh(session)

            logger.info(f"创建用户会话成功: {session_id} for user {user_id}")
            return session

        except Exception as e:
            db.rollback()
            logger.error(f"创建用户会话失败: {str(e)}")
            raise

    def verify_session(
        self,
        session_id: str,
        db: Optional[Session] = None,
    ) -> Optional[UserSession]:
        """
        验证用户会话

        Args:
            session_id: 会话ID
            db: 数据库会话

        Returns:
            会话模型（验证成功）或None（验证失败）
        """
        if db is None:
            db = next(get_db())

        try:
            session = db.query(UserSession).filter(
                UserSession.session_id == session_id,
                UserSession.is_active == True,
            ).first()

            if session is None:
                logger.warning(f"会话不存在: {session_id}")
                return None

            # 检查是否过期
            if session.is_expired():
                session.is_active = False
                db.commit()
                logger.warning(f"会话已过期: {session_id}")
                return None

            # 更新最后活动时间
            session.update_activity()
            db.commit()

            logger.info(f"会话验证成功: {session_id}")
            return session

        except Exception as e:
            logger.error(f"验证会话时出错: {str(e)}")
            return None

    def invalidate_session(
        self,
        session_id: str,
        db: Optional[Session] = None,
    ) -> bool:
        """
        使会话失效

        Args:
            session_id: 会话ID
            db: 数据库会话

        Returns:
            是否成功
        """
        if db is None:
            db = next(get_db())

        try:
            session = db.query(UserSession).filter(
                UserSession.session_id == session_id
            ).first()

            if session:
                session.is_active = False
                db.commit()
                logger.info(f"会话已失效: {session_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"使会话失效时出错: {str(e)}")
            return False

    def revoke_secret(
        self,
        secret_id: int,
        user_id: str,
        db: Optional[Session] = None,
    ) -> bool:
        """
        撤销密钥

        Args:
            secret_id: 密钥ID
            user_id: 用户ID
            db: 数据库会话

        Returns:
            是否成功
        """
        if db is None:
            db = next(get_db())

        try:
            secret = db.query(SecretModel).filter(
                SecretModel.id == secret_id,
                SecretModel.user_id == user_id,
            ).first()

            if secret:
                secret.is_active = False
                db.commit()
                logger.info(f"密钥已撤销: {secret_id}")
                return True

            return False

        except Exception as e:
            db.rollback()
            logger.error(f"撤销密钥时出错: {str(e)}")
            return False

    def cleanup_expired_sessions(self, db: Optional[Session] = None) -> int:
        """
        清理过期会话

        Args:
            db: 数据库会话

        Returns:
            清理的会话数量
        """
        if db is None:
            db = next(get_db())

        try:
            # 查找所有过期或非激活的会话
            expired_sessions = db.query(UserSession).filter(
                (UserSession.expires_at < datetime.utcnow()) |
                (UserSession.is_active == False)
            ).all()

            count = len(expired_sessions)

            # 删除过期会话
            for session in expired_sessions:
                db.delete(session)

            db.commit()

            logger.info(f"清理了 {count} 个过期会话")
            return count

        except Exception as e:
            db.rollback()
            logger.error(f"清理过期会话时出错: {str(e)}")
            return 0


# 创建全局身份验证器实例
_identity_verifier = None


def get_identity_verifier() -> IdentityVerifier:
    """获取身份验证器实例（单例模式）"""
    global _identity_verifier
    if _identity_verifier is None:
        _identity_verifier = IdentityVerifier()
    return _identity_verifier