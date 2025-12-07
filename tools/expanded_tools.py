"""
扩展工具集
包含Git操作、文件系统、数据分析等工具
"""

import os
import subprocess
import asyncio
import logging
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
import tempfile
import shutil
from datetime import datetime
import git

from config.config import settings
from security.security_utils import security_validator

logger = logging.getLogger(__name__)

class GitTool:
    """Git操作工具"""

    def __init__(self, work_dir: str = None):
        self.work_dir = work_dir or os.getcwd()
        self.repo = None
        self._init_repo()

    def _init_repo(self):
        """初始化Git仓库"""
        try:
            self.repo = git.Repo(self.work_dir)
        except git.exc.InvalidGitRepositoryError:
            # 不是Git仓库，尝试初始化
            self.repo = git.Repo.init(self.work_dir)
            logger.info(f"Initialized new Git repository in {self.work_dir}")

    async def execute_command(self, command: List[str]) -> Dict[str, Any]:
        """执行Git命令"""
        try:
            # 安全验证
            cmd_str = ' '.join(command)
            if not self._is_safe_git_command(command):
                raise ValueError("Unsafe Git command detected")

            # 执行命令
            result = subprocess.run(
                ['git'] + command,
                cwd=self.work_dir,
                capture_output=True,
                text=True,
                timeout=30
            )

            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "command": 'git ' + cmd_str
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Command timed out after 30 seconds",
                "command": 'git ' + ' '.join(command)
            }
        except Exception as e:
            logger.error(f"Git command failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "command": 'git ' + ' '.join(command)
            }

    def _is_safe_git_command(self, command: List[str]) -> bool:
        """检查Git命令是否安全"""
        # 禁止的命令
        forbidden_commands = [
            'rm', 'clean', 'reset', 'rebase', 'merge', 'push', 'pull'
        ]

        for cmd in command:
            if cmd in forbidden_commands:
                logger.warning(f"Forbidden Git command: {cmd}")
                return False

        # 允许的命令
        allowed_commands = [
            'status', 'log', 'diff', 'show', 'branch', 'tag',
            'add', 'commit', 'checkout', 'stash', 'reflog'
        ]

        if command[0] not in allowed_commands:
            logger.warning(f"Unknown Git command: {command[0]}")
            return False

        return True

    async def get_status(self) -> Dict[str, Any]:
        """获取Git状态"""
        return await self.execute_command(['status', '--porcelain'])

    async def get_log(self, limit: int = 10) -> Dict[str, Any]:
        """获取提交日志"""
        return await self.execute_command(['log', '--oneline', f'-n{limit}'])

    async def get_diff(self, file: str = None) -> Dict[str, Any]:
        """获取差异"""
        cmd = ['diff']
        if file:
            cmd.append(file)
        return await self.execute_command(cmd)

    async def create_branch(self, branch_name: str) -> Dict[str, Any]:
        """创建分支"""
        return await self.execute_command(['branch', branch_name])

    async def switch_branch(self, branch_name: str) -> Dict[str, Any]:
        """切换分支"""
        return await self.execute_command(['checkout', branch_name])

    async def add_file(self, file_path: str) -> Dict[str, Any]:
        """添加文件到暂存区"""
        # 验证文件路径
        full_path = os.path.join(self.work_dir, file_path)
        if not os.path.exists(full_path):
            return {
                "success": False,
                "error": f"File not found: {file_path}"
            }

        return await self.execute_command(['add', file_path])

    async def commit(self, message: str) -> Dict[str, Any]:
        """提交更改"""
        # 验证提交信息
        if not message or len(message.strip()) == 0:
            return {
                "success": False,
                "error": "Commit message cannot be empty"
            }

        # 清理提交信息
        message = security_validator.sanitize_input(message, 200)

        # 配置用户信息（如果未配置）
        await self.execute_command(['config', 'user.name', '"AgenticGen"'])
        await self.execute_command(['config', 'user.email', '"agenticgen@example.com"'])

        return await self.execute_command(['commit', '-m', f'"{message}"'])

class FilesystemTool:
    """文件系统操作工具"""

    def __init__(self, base_path: str = None):
        self.base_path = Path(base_path or settings.UPLOAD_DIR)
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def list_directory(self, path: str = ".") -> Dict[str, Any]:
        """列出目录内容"""
        try:
            # 安全检查路径
            target_path = self._safe_path(path)
            if not target_path:
                return {
                    "success": False,
                    "error": "Invalid path"
                }

            target_path = Path(target_path)
            if not target_path.exists():
                return {
                    "success": False,
                    "error": "Path does not exist"
                }

            if not target_path.is_dir():
                return {
                    "success": False,
                    "error": "Not a directory"
                }

            # 列出内容
            items = []
            for item in target_path.iterdir():
                item_info = {
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else 0,
                    "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat()
                }
                items.append(item_info)

            # 排序（目录优先）
            items.sort(key=lambda x: (0 if x["type"] == "directory" else 1, x["name"]))

            return {
                "success": True,
                "path": str(target_path.relative_to(self.base_path)),
                "items": items
            }

        except Exception as e:
            logger.error(f"Failed to list directory: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def read_file(self, path: str, max_size: int = 1024 * 1024) -> Dict[str, Any]:
        """读取文件内容"""
        try:
            target_path = self._safe_path(path)
            if not target_path:
                return {
                    "success": False,
                    "error": "Invalid path"
                }

            target_path = Path(target_path)
            if not target_path.exists() or not target_path.is_file():
                return {
                    "success": False,
                    "error": "File not found"
                }

            # 检查文件大小
            file_size = target_path.stat().st_size
            if file_size > max_size:
                return {
                    "success": False,
                    "error": f"File too large (max {max_size} bytes)"
                }

            # 读取文件
            content = target_path.read_text(encoding='utf-8')

            # 检查文件类型
            if target_path.suffix.lower() in ['.json', '.yaml', '.yml', '.xml']:
                try:
                    # 尝试解析结构化数据
                    if target_path.suffix.lower() == '.json':
                        structured_content = json.loads(content)
                    else:
                        structured_content = content  # YAML/XML需要额外处理
                except:
                    structured_content = None
            else:
                structured_content = None

            return {
                "success": True,
                "path": str(target_path.relative_to(self.base_path)),
                "size": file_size,
                "content": content,
                "structured": structured_content is not None,
                "structured_content": structured_content
            }

        except Exception as e:
            logger.error(f"Failed to read file: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def write_file(self, path: str, content: str, overwrite: bool = False) -> Dict[str, Any]:
        """写入文件"""
        try:
            target_path = self._safe_path(path)
            if not target_path:
                return {
                    "success": False,
                    "error": "Invalid path"
                }

            target_path = Path(target_path)

            # 检查是否覆盖
            if target_path.exists() and not overwrite:
                return {
                    "success": False,
                    "error": "File already exists"
                }

            # 创建目录
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # 安全检查内容
            content = security_validator.sanitize_input(content, 10 * 1024 * 1024)  # 10MB limit

            # 写入文件
            target_path.write_text(content, encoding='utf-8')

            return {
                "success": True,
                "path": str(target_path.relative_to(self.base_path)),
                "size": len(content.encode('utf-8'))
            }

        except Exception as e:
            logger.error(f"Failed to write file: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def delete_file(self, path: str) -> Dict[str, Any]:
        """删除文件或目录"""
        try:
            target_path = self._safe_path(path)
            if not target_path:
                return {
                    "success": False,
                    "error": "Invalid path"
                }

            target_path = Path(target_path)
            if not target_path.exists():
                return {
                    "success": False,
                    "error": "Path does not exist"
                }

            if target_path.is_file():
                target_path.unlink()
            elif target_path.is_dir():
                shutil.rmtree(target_path)

            return {
                "success": True,
                "path": str(target_path.relative_to(self.base_path))
            }

        except Exception as e:
            logger.error(f"Failed to delete: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def _safe_path(self, path: str) -> Optional[Path]:
        """确保路径安全"""
        try:
            # 清理路径
            clean_path = security_validator.sanitize_input(path, 1000)

            # 解析路径
            target_path = Path(clean_path).resolve()
            base_path = Path(self.base_path).resolve()

            # 确保在基础路径内
            try:
                target_path.relative_to(base_path)
                return target_path
            except ValueError:
                logger.warning(f"Path traversal attempt: {path}")
                return None

        except Exception as e:
            logger.error(f"Path validation failed: {str(e)}")
            return None

class DataAnalysisTool:
    """数据分析工具"""

    def __init__(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        logger.info(f"Created temp directory for data analysis: {self.temp_dir}")

    async def analyze_csv(self, file_path: str, sample_size: int = 1000) -> Dict[str, Any]:
        """分析CSV文件"""
        try:
            # 读取CSV
            df = pd.read_csv(file_path, nrows=sample_size)

            analysis = {
                "success": True,
                "shape": df.shape,
                "columns": list(df.columns),
                "dtypes": df.dtypes.to_dict(),
                "null_counts": df.isnull().sum().to_dict(),
                "sample_data": df.head(10).to_dict('records'),
                "numeric_summary": {},
                "categorical_summary": {}
            }

            # 数值列分析
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            for col in numeric_cols:
                analysis["numeric_summary"][col] = {
                    "count": df[col].count(),
                    "mean": float(df[col].mean()),
                    "std": float(df[col].std()),
                    "min": float(df[col].min()),
                    "max": float(df[col].max()),
                    "quartiles": df[col].quantile([0.25, 0.5, 0.75]).to_dict()
                }

            # 分类列分析
            categorical_cols = df.select_dtypes(include=['object']).columns
            for col in categorical_cols:
                value_counts = df[col].value_counts().head(10)
                analysis["categorical_summary"][col] = {
                    "unique_count": df[col].nunique(),
                    "top_values": value_counts.to_dict()
                }

            return analysis

        except Exception as e:
            logger.error(f"Failed to analyze CSV: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def create_visualization(
        self,
        data: Union[List[Dict], pd.DataFrame],
        chart_type: str,
        x_col: str = None,
        y_col: str = None
    ) -> Dict[str, Any]:
        """创建数据可视化"""
        try:
            import matplotlib
            matplotlib.use('Agg')  # 使用非交互式后端
            import matplotlib.pyplot as plt
            import seaborn as sns

            # 转换数据
            if isinstance(data, list):
                df = pd.DataFrame(data)
            else:
                df = data

            # 创建图表
            plt.figure(figsize=(10, 6))

            if chart_type == "line" and x_col and y_col:
                plt.plot(df[x_col], df[y_col])
                plt.xlabel(x_col)
                plt.ylabel(y_col)

            elif chart_type == "bar" and x_col and y_col:
                plt.bar(df[x_col], df[y_col])
                plt.xlabel(x_col)
                plt.ylabel(y_col)
                plt.xticks(rotation=45)

            elif chart_type == "scatter" and x_col and y_col:
                plt.scatter(df[x_col], df[y_col])
                plt.xlabel(x_col)
                plt.ylabel(y_col)

            elif chart_type == "hist" and y_col:
                plt.hist(df[y_col], bins=20)
                plt.xlabel(y_col)
                plt.ylabel("Frequency")

            elif chart_type == "box" and y_col:
                sns.boxplot(data=df, y=y_col)

            else:
                return {
                    "success": False,
                    "error": f"Unsupported chart type or missing columns: {chart_type}"
                }

            plt.title(f"{chart_type.title()} Chart")
            plt.tight_layout()

            # 保存图表
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_path = self.temp_dir / f"chart_{timestamp}.png"
            plt.savefig(image_path)
            plt.close()

            # 转换为base64
            import base64
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode()

            return {
                "success": True,
                "image_data": image_data,
                "image_path": str(image_path)
            }

        except Exception as e:
            logger.error(f"Failed to create visualization: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def correlation_analysis(self, file_path: str) -> Dict[str, Any]:
        """相关性分析"""
        try:
            df = pd.read_csv(file_path)
            numeric_df = df.select_dtypes(include=[np.number])

            if numeric_df.empty:
                return {
                    "success": False,
                    "error": "No numeric columns found for correlation analysis"
                }

            correlation_matrix = numeric_df.corr()

            return {
                "success": True,
                "correlation_matrix": correlation_matrix.to_dict(),
                "high_correlations": self._find_high_correlations(correlation_matrix)
            }

        except Exception as e:
            logger.error(f"Failed correlation analysis: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def _find_high_correlations(self, corr_matrix: pd.DataFrame, threshold: float = 0.8) -> List[Dict]:
        """查找高相关性"""
        high_corr = []
        for i in range(len(corr_matrix.columns)):
            for j in range(i + 1, len(corr_matrix.columns)):
                corr_value = corr_matrix.iloc[i, j]
                if abs(corr_value) > threshold:
                    high_corr.append({
                        "column1": corr_matrix.columns[i],
                        "column2": corr_matrix.columns[j],
                        "correlation": float(corr_value)
                    })
        return high_corr

    async def cleanup(self):
        """清理临时文件"""
        try:
            shutil.rmtree(self.temp_dir)
            logger.info("Cleaned up data analysis temp directory")
        except Exception as e:
            logger.error(f"Failed to cleanup temp directory: {str(e)}")

# 工具管理器
class ExpandedToolManager:
    """扩展工具管理器"""

    def __init__(self):
        self.git_tool = None
        self.fs_tool = FilesystemTool()
        self.data_tool = DataAnalysisTool()

    def get_git_tool(self, work_dir: str = None) -> GitTool:
        """获取Git工具实例"""
        return GitTool(work_dir)

    async def execute_tool(
        self,
        tool_name: str,
        action: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行工具操作"""
        try:
            if tool_name == "git":
                git_tool = self.get_git_tool(parameters.get("work_dir"))
                method = getattr(git_tool, action, None)
                if method:
                    return await method(**parameters)
            elif tool_name == "filesystem":
                method = getattr(self.fs_tool, action, None)
                if method:
                    return await method(**parameters)
            elif tool_name == "data_analysis":
                method = getattr(self.data_tool, action, None)
                if method:
                    return await method(**parameters)

            return {
                "success": False,
                "error": f"Unknown tool or action: {tool_name}.{action}"
            }

        except Exception as e:
            logger.error(f"Tool execution failed: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

# 全局工具管理器
expanded_tool_manager = ExpandedToolManager()