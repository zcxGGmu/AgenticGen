"""
Python代码执行器

提供安全的Python代码执行环境。
"""

import ast
import json
import sys
import traceback
from io import StringIO, BytesIO
from typing import Any, Dict, List, Optional

from tools.sandbox import Sandbox, DEFAULT_SANDBOX_LIMITS
from config import settings
from config.logging import get_logger

logger = get_logger(__name__)


class PythonOutputCapture:
    """捕获Python输出"""

    def __init__(self):
        self.stdout_buffer = StringIO()
        self.stderr_buffer = StringIO()
        self.original_stdout = None
        self.original_stderr = None

    def __enter__(self):
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        sys.stdout = self.stdout_buffer
        sys.stderr = self.stderr_buffer
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr

    def get_output(self) -> Dict[str, str]:
        """获取捕获的输出"""
        return {
            "stdout": self.stdout_buffer.getvalue(),
            "stderr": self.stderr_buffer.getvalue(),
        }


class PythonCodeValidator:
    """Python代码验证器"""

    @staticmethod
    def validate(code: str) -> Dict[str, Any]:
        """
        验证Python代码

        Args:
            code: Python代码

        Returns:
            验证结果
        """
        try:
            # 解析代码
            ast.parse(code)

            # 检查危险操作
            dangerous_patterns = [
                "os.system",
                "subprocess.call",
                "subprocess.run",
                "subprocess.Popen",
                "eval(",
                "exec(",
                "compile(",
                "globals()",
                "locals()",
                "vars()",
                "dir()",
                "hasattr(",
                "getattr(",
                "setattr(",
                "delattr(",
                "open(",
                "file(",
                "input(",
                "raw_input(",
                "__import__",
                "reload(",
            ]

            code_lower = code.lower()
            found_dangerous = []

            for pattern in dangerous_patterns:
                if pattern in code_lower:
                    found_dangerous.append(pattern)

            # 允许一些安全的函数调用
            allowed_patterns = [
                "print(",
                "len(",
                "range(",
                "enumerate(",
                "zip(",
                "map(",
                "filter(",
                "sum(",
                "max(",
                "min(",
                "sorted(",
                "list(",
                "dict(",
                "set(",
                "tuple(",
            ]

            # 移除允许的模式
            for pattern in allowed_patterns:
                if pattern in found_dangerous:
                    found_dangerous.remove(pattern)

            # 检查导入的模块
            tree = ast.parse(code)
            imported_modules = []
            dangerous_modules = [
                "os", "sys", "subprocess", "socket", "threading",
                "multiprocessing", "ctypes", "pickle", "marshal",
                "shutil", "tempfile", "glob", "fnmatch",
            ]

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported_modules.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported_modules.append(node.module)

            found_dangerous_modules = [
                mod for mod in imported_modules if mod in dangerous_modules
            ]

            if found_dangerous or found_dangerous_modules:
                return {
                    "valid": False,
                    "error": "代码包含不安全的操作",
                    "dangerous_operations": found_dangerous,
                    "dangerous_modules": found_dangerous_modules,
                }

            return {
                "valid": True,
                "error": None,
                "imported_modules": imported_modules,
            }

        except SyntaxError as e:
            return {
                "valid": False,
                "error": f"语法错误: {str(e)}",
                "line": e.lineno,
                "offset": e.offset,
            }
        except Exception as e:
            return {
                "valid": False,
                "error": f"验证错误: {str(e)}",
            }


class PythonExecutor:
    """Python代码执行器"""

    def __init__(self, sandbox_limits=None):
        self.sandbox_limits = sandbox_limits or DEFAULT_SANDBOX_LIMITS
        self.allowed_modules = [
            "math", "random", "datetime", "json", "csv",
            "collections", "itertools", "functools", "operator",
            "string", "re", "statistics", "decimal", "fractions",
            "numbers", "typing", "dataclasses", "enum",
        ]

        # 允许的第三方模块
        if settings.environment == "production":
            self.allowed_third_party = [
                "numpy", "pandas", "matplotlib", "seaborn",
                "plotly", "scipy", "sklearn", "tensorflow",
                "torch", "pillow", "opencv-python",
            ]
        else:
            self.allowed_third_party = []

    async def execute(
        self,
        code: str,
        timeout: Optional[float] = None,
        capture_output: bool = True,
    ) -> Dict[str, Any]:
        """
        执行Python代码

        Args:
            code: Python代码
            timeout: 超时时间
            capture_output: 是否捕获输出

        Returns:
            执行结果
        """
        # 验证代码
        validation = PythonCodeValidator.validate(code)
        if not validation["valid"]:
            return {
                "success": False,
                "error": validation["error"],
                "output": "",
                "error_output": "",
                "execution_time": 0,
            }

        # 准备执行脚本
        exec_script = self._prepare_exec_script(code, capture_output)

        # 在沙箱中执行
        async with Sandbox(resource_limits=self.sandbox_limits) as sandbox:
            # 保存执行脚本
            script_file = sandbox.create_file("execute.py", exec_script)

            # 准备执行命令
            command = f"python3 {script_file}"

            # 执行代码
            result = await sandbox.execute(command, timeout=timeout)

            # 解析输出
            if result["success"]:
                try:
                    # 读取执行结果
                    output_file = Path(sandbox.working_dir) / "output.json"
                    if output_file.exists():
                        with open(output_file, 'r', encoding='utf-8') as f:
                            output_data = json.load(f)
                    else:
                        output_data = {}

                    return {
                        "success": True,
                        "error": None,
                        "output": output_data.get("stdout", ""),
                        "error_output": output_data.get("stderr", ""),
                        "result": output_data.get("result"),
                        "execution_time": output_data.get("execution_time", 0),
                        "memory_usage": output_data.get("memory_usage", 0),
                    }
                except Exception as e:
                    logger.error(f"解析Python执行结果失败: {str(e)}")
                    return {
                        "success": True,
                        "error": None,
                        "output": result["stdout"],
                        "error_output": result["stderr"],
                        "result": None,
                        "execution_time": 0,
                    }
            else:
                return {
                    "success": False,
                    "error": result["error"],
                    "output": result["stdout"],
                    "error_output": result["stderr"],
                    "execution_time": 0,
                }

    def _prepare_exec_script(self, code: str, capture_output: bool) -> str:
        """
        准备执行脚本

        Args:
            code: 用户代码
            capture_output: 是否捕获输出

        Returns:
            执行脚本
        """
        # 导入必要的模块
        imports = [
            "import sys",
            "import traceback",
            "import json",
            "import time",
            "import tracemalloc",
        ]

        # 允许的模块导入
        for module in self.allowed_modules:
            imports.append(f"try:\n    import {module}\nexcept ImportError:\n    pass")

        for module in self.allowed_third_party:
            imports.append(f"try:\n    import {module}\nexcept ImportError:\n    pass")

        # 构建执行脚本
        script_parts = imports + [
            "\n# 执行用户代码",
            "start_time = time.time()",
            "tracemalloc.start()",
        ]

        if capture_output:
            script_parts += [
                "try:",
                "    exec('''",
                code.replace("'''", r"\'\'\'"),
                "''')",
                "except Exception as e:",
                "    error_output = traceback.format_exc()",
            ]
        else:
            script_parts += [
                "exec('''",
                code.replace("'''", r"\'\'\'"),
                "''')",
            ]

        script_parts += [
            "\n# 记录执行结果",
            "current, peak = tracemalloc.get_traced_memory()",
            "tracemalloc.stop()",
            "execution_time = time.time() - start_time",
            "",
            "result = {",
            "    'stdout': globals().get('_stdout', ''),",
            "    'stderr': globals().get('_stderr', ''),",
            "    'execution_time': execution_time,",
            "    'memory_usage': current,",
            "}",
            "",
            "if 'error_output' in locals():",
            "    result['error'] = error_output",
            "",
            "# 保存结果到文件",
            "with open('output.json', 'w', encoding='utf-8') as f:",
            "    json.dump(result, f, ensure_ascii=False, indent=2)",
        ]

        return "\n".join(script_parts)

    async def execute_with_matplotlib(
        self,
        code: str,
        timeout: Optional[float] = None,
        save_plots: bool = True,
        plot_format: str = "png",
    ) -> Dict[str, Any]:
        """
        执行包含matplotlib的代码

        Args:
            code: Python代码
            timeout: 超时时间
            save_plots: 是否保存图表
            plot_format: 图表格式

        Returns:
            执行结果
        """
        # 添加matplotlib配置
        matplotlib_code = f"""
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端
import matplotlib.pyplot as plt

# 保存图表的函数
def save_current_plot(filename):
    if plt.get_fignums():
        plt.savefig(filename, format='{plot_format}', bbox_inches='tight')
        plt.close()
        return filename
    return None

{code}
"""

        result = await self.execute(matplotlib_code, timeout=timeout)

        # 查找生成的图片文件
        if result["success"]:
            # 这里可以添加查找并返回图片文件路径的逻辑
            pass

        return result

    async def check_syntax(self, code: str) -> Dict[str, Any]:
        """
        检查代码语法

        Args:
            code: Python代码

        Returns:
            检查结果
        """
        return PythonCodeValidator.validate(code)

    async def format_code(self, code: str) -> Dict[str, Any]:
        """
        格式化代码

        Args:
            code: Python代码

        Returns:
            格式化结果
        """
        try:
            import black
            import autopep8

            # 使用black格式化
            formatted = black.format_str(code, mode=black.FileMode())

            # 使用autopep8进一步优化
            formatted = autopep8.fix_code(formatted)

            return {
                "success": True,
                "formatted_code": formatted,
                "error": None,
            }
        except ImportError:
            return {
                "success": False,
                "error": "格式化工具未安装（需要black和autopep8）",
                "formatted_code": code,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "formatted_code": code,
            }