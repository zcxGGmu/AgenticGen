"""
沙箱环境

提供安全的执行环境隔离。
"""

import asyncio
import os
import resource
import signal
import subprocess
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Dict, Any, List

from config import settings
from config.logging import get_logger

logger = get_logger(__name__)


class ResourceLimits:
    """资源限制配置"""

    def __init__(
        self,
        max_cpu_time: float = 30.0,
        max_memory: int = 512 * 1024 * 1024,  # 512MB
        max_processes: int = 10,
        max_file_size: int = 10 * 1024 * 1024,  # 10MB
    ):
        self.max_cpu_time = max_cpu_time
        self.max_memory = max_memory
        self.max_processes = max_processes
        self.max_file_size = max_file_size


class Sandbox:
    """沙箱执行环境"""

    def __init__(
        self,
        working_dir: Optional[str] = None,
        resource_limits: Optional[ResourceLimits] = None,
        allowed_paths: Optional[List[str]] = None,
    ):
        self.working_dir = working_dir or tempfile.mkdtemp(prefix="agenticgen_sandbox_")
        self.resource_limits = resource_limits or ResourceLimits()
        self.allowed_paths = allowed_paths or [self.working_dir]

        # 确保工作目录存在
        Path(self.working_dir).mkdir(parents=True, exist_ok=True)

        logger.debug(f"创建沙箱: {self.working_dir}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    async def execute(
        self,
        command: str,
        input_data: Optional[str] = None,
        timeout: Optional[float] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        在沙箱中执行命令

        Args:
            command: 要执行的命令
            input_data: 输入数据
            timeout: 超时时间
            env: 环境变量

        Returns:
            执行结果
        """
        # 设置超时
        timeout = timeout or self.resource_limits.max_cpu_time

        # 准备环境变量
        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)

        # 限制环境变量，避免泄露系统信息
        restricted_env = {
            "PATH": exec_env.get("PATH", "/usr/bin:/bin"),
            "HOME": self.working_dir,
            "TMPDIR": self.working_dir,
            "PYTHONPATH": "",
            "PYTHONSTARTUP": "",
        }

        # 添加用户指定的环境变量（排除危险变量）
        safe_env_vars = [
            "LANG", "LC_ALL", "TZ", "TERM", "SHELL", "USER", "USERNAME",
            "PYTHONUNBUFFERED", "PYTHONDONTWRITEBYTECODE",
        ]
        for var in safe_env_vars:
            if var in exec_env:
                restricted_env[var] = exec_env[var]

        try:
            # 创建子进程
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=self.working_dir,
                env=restricted_env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=self._setup_resource_limits,
            )

            logger.debug(f"执行命令: {command}")

            # 设置超时
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=input_data.encode() if input_data else None),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                # 超时，强制终止进程
                process.kill()
                await process.wait()

                return {
                    "success": False,
                    "error": f"执行超时（{timeout}秒）",
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": "Timeout",
                    "execution_time": timeout,
                }

            # 解析输出
            stdout_text = stdout.decode('utf-8', errors='replace')
            stderr_text = stderr.decode('utf-8', errors='replace')

            # 检查是否超出资源限制
            if self._check_resource_violation(process):
                return {
                    "success": False,
                    "error": "超出资源限制",
                    "exit_code": process.returncode,
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                }

            return {
                "success": process.returncode == 0,
                "error": None if process.returncode == 0 else f"命令失败，退出码: {process.returncode}",
                "exit_code": process.returncode,
                "stdout": stdout_text,
                "stderr": stderr_text,
            }

        except Exception as e:
            logger.error(f"沙箱执行失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
            }

    def _setup_resource_limits(self):
        """设置进程资源限制"""
        # CPU时间限制
        resource.setrlimit(
            resource.RLIMIT_CPU,
            (int(self.resource_limits.max_cpu_time), int(self.resource_limits.max_cpu_time))
        )

        # 内存限制
        resource.setrlimit(
            resource.RLIMIT_AS,
            (self.resource_limits.max_memory, self.resource_limits.max_memory)
        )

        # 进程数限制
        resource.setrlimit(
            resource.RLIMIT_NPROC,
            (self.resource_limits.max_processes, self.resource_limits.max_processes)
        )

        # 文件大小限制
        resource.setrlimit(
            resource.RLIMIT_FSIZE,
            (self.resource_limits.max_file_size, self.resource_limits.max_file_size)
        )

        # 禁用核心转储
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

        # 清理权限
        os.umask(0o077)

    def _check_resource_violation(self, process) -> bool:
        """检查是否违反资源限制"""
        # 在Linux上可以通过/proc/<pid>/status检查
        if hasattr(process, 'pid'):
            try:
                status_file = f"/proc/{process.pid}/status"
                if os.path.exists(status_file):
                    with open(status_file, 'r') as f:
                        for line in f:
                            if line.startswith('VmRSS:'):  # 物理内存使用
                                kb = int(line.split()[1])
                                bytes_used = kb * 1024
                                if bytes_used > self.resource_limits.max_memory:
                                    return True
            except:
                pass
        return False

    def create_file(self, filename: str, content: str) -> str:
        """
        在沙箱中创建文件

        Args:
            filename: 文件名
            content: 文件内容

        Returns:
            文件路径
        """
        file_path = Path(self.working_dir) / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return str(file_path)

    def read_file(self, filename: str) -> str:
        """
        读取沙箱中的文件

        Args:
            filename: 文件名

        Returns:
            文件内容
        """
        file_path = Path(self.working_dir) / filename

        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {filename}")

        if not self._is_path_allowed(str(file_path)):
            raise PermissionError(f"访问被拒绝: {filename}")

        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    def list_files(self, path: str = ".") -> List[Dict[str, Any]]:
        """
        列出沙箱中的文件

        Args:
            path: 路径

        Returns:
            文件列表
        """
        dir_path = Path(self.working_dir) / path

        if not self._is_path_allowed(str(dir_path)):
            raise PermissionError(f"访问被拒绝: {path}")

        files = []
        for item in dir_path.iterdir():
            if item.is_file():
                file_type = "file"
                size = item.stat().st_size
            elif item.is_dir():
                file_type = "directory"
                size = 0
            else:
                file_type = "other"
                size = 0

            files.append({
                "name": item.name,
                "path": str(item.relative_to(self.working_dir)),
                "type": file_type,
                "size": size,
            })

        return files

    def delete_file(self, filename: str) -> bool:
        """
        删除沙箱中的文件

        Args:
            filename: 文件名

        Returns:
            是否成功
        """
        file_path = Path(self.working_dir) / filename

        if not self._is_path_allowed(str(file_path)):
            raise PermissionError(f"访问被拒绝: {filename}")

        try:
            if file_path.is_file():
                file_path.unlink()
            elif file_path.is_dir():
                import shutil
                shutil.rmtree(file_path)
            return True
        except Exception:
            return False

    def _is_path_allowed(self, path: str) -> bool:
        """检查路径是否被允许访问"""
        abs_path = os.path.abspath(path)

        for allowed_path in self.allowed_paths:
            abs_allowed = os.path.abspath(allowed_path)
            if abs_path.startswith(abs_allowed + os.sep) or abs_path == abs_allowed:
                return True

        return False

    def cleanup(self):
        """清理沙箱"""
        import shutil
        try:
            if os.path.exists(self.working_dir):
                shutil.rmtree(self.working_dir)
                logger.debug(f"清理沙箱: {self.working_dir}")
        except Exception as e:
            logger.error(f"清理沙箱失败: {str(e)}")


@asynccontextmanager
async def create_sandbox(
    working_dir: Optional[str] = None,
    resource_limits: Optional[ResourceLimits] = None,
    allowed_paths: Optional[List[str]] = None,
):
    """
    创建沙箱的上下文管理器

    Args:
        working_dir: 工作目录
        resource_limits: 资源限制
        allowed_paths: 允许访问的路径

    Yields:
        Sandbox实例
    """
    sandbox = Sandbox(working_dir, resource_limits, allowed_paths)
    try:
        yield sandbox
    finally:
        sandbox.cleanup()


# 全局沙箱配置
DEFAULT_SANDBOX_LIMITS = ResourceLimits(
    max_cpu_time=30.0,
    max_memory=512 * 1024 * 1024,  # 512MB
    max_processes=10,
    max_file_size=10 * 1024 * 1024,  # 10MB
)