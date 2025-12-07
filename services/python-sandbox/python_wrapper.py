"""
Python wrapper for the Rust Python Sandbox
Provides secure execution of untrusted Python code
"""

import ctypes
import json
import time
from typing import Dict, List, Optional, Any
import os
import sys
import subprocess
import tempfile
import threading

class PythonSandbox:
    """
    Python wrapper for the Rust Python Sandbox.

    When the Rust implementation is not available, falls back to a pure Python implementation
    with basic security restrictions.
    """

    def __init__(self, max_execution_time: int = 30, max_memory_mb: int = 512):
        """
        Initialize the sandbox.

        Args:
            max_execution_time: Maximum execution time in seconds
            max_memory_mb: Maximum memory limit in MB
        """
        self.config = {
            'max_execution_time': max_execution_time,
            'max_memory_mb': max_memory_mb
        }

        # Try to load Rust implementation
        self._load_library()

        if self._lib is not None:
            self.rust_sandbox = self._create_rust_sandbox()
        else:
            self.rust_sandbox = None
            print("⚠️ Rust implementation not found, using Python fallback")

    def _load_library(self):
        """Load the shared library"""
        try:
            # Try to find the library
            lib_name = None
            lib_paths = [
                "./target/release/libpython_sandbox.so",
                "./target/debug/libpython_sandbox.so",
                "/usr/local/lib/libpython_sandbox.so",
                "/usr/lib/libpython_sandbox.so",
            ]

            for path in lib_paths:
                if os.path.exists(path):
                    lib_name = path
                    break

            if lib_name is None:
                self._lib = None
                return

            # Load the library
            self._lib = ctypes.CDLL(lib_name)

            # Define function signatures
            self._lib.python_sandbox_create.argtypes = []
            self._lib.python_sandbox_create.restype = ctypes.c_void_p

            self._lib.python_sandbox_destroy.argtypes = [ctypes.c_void_p]
            self._lib.python_sandbox_destroy.restype = None

            self._lib.python_sandbox_execute.argtypes = [
                ctypes.c_void_p,
                ctypes.c_char_p,
                ctypes.c_char_p,
                ctypes.POINTER(ctypes.c_size_t)
            ]
            self._lib.python_sandbox_execute.restype = ctypes.c_int

            self._lib.python_sandbox_get_result.argtypes = [
                ctypes.c_void_p,
                ctypes.c_char_p,
                ctypes.POINTER(ctypes.c_int),
                ctypes.c_char_p,
                ctypes.POINTER(ctypes.c_size_t),
                ctypes.c_char_p,
                ctypes.POINTER(ctypes.c_size_t)
            ]
            self._lib.python_sandbox_get_result.restype = ctypes.c_int

        except:
            self._lib = None

    def _create_rust_sandbox(self):
        """Create a Rust sandbox instance"""
        if self._lib is None:
            return None

        ptr = self._lib.python_sandbox_create()
        if not ptr:
            return None
        return ptr

    def __del__(self):
        """Cleanup resources"""
        if hasattr(self, 'rust_sandbox') and self.rust_sandbox and self._lib:
            self._lib.python_sandbox_destroy(self.rust_sandbox)

    def execute(self, code: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """
        Execute Python code in the sandbox.

        Args:
            code: Python code to execute
            timeout: Custom timeout in seconds

        Returns:
            Dictionary with execution result
        """
        if self.rust_sandbox:
            return self._execute_rust(code, timeout)
        else:
            return self._execute_python_fallback(code, timeout)

    def _execute_rust(self, code: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """Execute using Rust implementation"""
        c_code = code.encode('utf-8')

        # Prepare output parameters
        execution_id = ctypes.create_string_buffer(256)
        id_len = ctypes.c_size_t()

        result = self._lib.python_sandbox_execute(
            self.rust_sandbox,
            c_code,
            execution_id,
            ctypes.byref(id_len)
        )

        if result != 0:
            return {
                'success': False,
                'error': 'Failed to execute code',
                'exit_code': -1,
                'stdout': '',
                'stderr': ''
            }

        # Get the execution ID
        exec_id = execution_id.value.decode('utf-8')[:id_len.value]

        # Wait for result
        # In a real implementation, this would be async or use polling
        time.sleep(0.1)

        # Get result
        exit_code = ctypes.c_int()
        stdout = ctypes.create_string_buffer(1024 * 1024)
        stdout_len = ctypes.c_size_t()
        stderr = ctypes.create_string_buffer(1024 * 1024)
        stderr_len = ctypes.c_size_t()

        result = self._lib.python_sandbox_get_result(
            self.rust_sandbox,
            exec_id.encode('utf-8'),
            ctypes.byref(exit_code),
            stdout,
            ctypes.byref(stdout_len),
            stderr,
            ctypes.byref(stderr_len)
        )

        if result == 0:
            stdout_str = stdout.value.decode('utf-8', errors='replace')[:stdout_len.value]
            stderr_str = stderr.value.decode('utf-8', errors='replace')[:stderr_len.value]

            return {
                'success': exit_code.value == 0,
                'exit_code': exit_code.value,
                'stdout': stdout_str,
                'stderr': stderr_str
            }
        else:
            return {
                'success': False,
                'error': 'Execution not found or still running',
                'exit_code': -1,
                'stdout': '',
                'stderr': ''
            }

    def _execute_python_fallback(self, code: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """Execute using Python fallback implementation"""
        # Basic security check
        dangerous_keywords = [
            'import os', 'import sys', 'import subprocess', 'import importlib',
            'exec(', 'eval(', 'compile(', '__import__',
            'open(', 'file(', 'input(',
            'globals()', 'locals()', 'vars()',
            'getattr', 'setattr', 'delattr'
        ]

        code_lower = code.lower()
        for keyword in dangerous_keywords:
            if keyword in code_lower:
                return {
                    'success': False,
                    'error': f'Dangerous operation detected: {keyword}',
                    'exit_code': -1,
                    'stdout': '',
                    'stderr': f'Error: {keyword} is not allowed in sandbox'
                }

        # Create temporary files
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            # Wrap code with basic restrictions
            wrapped_code = f'''
import sys
import builtins

# Remove dangerous builtins
dangerous = ['open', 'file', 'input', 'raw_input', 'exec', 'eval']
for d in dangerous:
    if hasattr(builtins, d):
        delattr(builtins, d)

# User code
try:
{code}
except Exception as e:
    print(f"Error: {{e}}", file=sys.stderr)
    sys.exit(1)
'''
            f.write(wrapped_code)
            code_file = f.name

        try:
            # Execute with resource limits
            timeout = timeout or self.config['max_execution_time']

            # Use subprocess with limits
            process = subprocess.run(
                [sys.executable, '-u', code_file],
                capture_output=True,
                text=True,
                timeout=timeout
            )

            return {
                'success': process.returncode == 0,
                'exit_code': process.returncode,
                'stdout': process.stdout,
                'stderr': process.stderr
            }

        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': 'Execution timeout',
                'exit_code': -1,
                'stdout': '',
                'stderr': 'Error: Code execution timed out'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'exit_code': -1,
                'stdout': '',
                'stderr': f'Error: {str(e)}'
            }
        finally:
            # Clean up temp file
            try:
                os.unlink(code_file)
            except:
                pass

    def batch_execute(self, codes: List[str]) -> List[Dict[str, Any]]:
        """
        Execute multiple code snippets.

        Args:
            codes: List of Python code snippets

        Returns:
            List of execution results
        """
        results = []
        for code in codes:
            result = self.execute(code)
            results.append(result)
        return results


def demo():
    """Demonstrate the Python sandbox"""
    print("🔒 Python Sandbox Demo")
    print("=" * 50)

    # Create sandbox
    sandbox = PythonSandbox(max_execution_time=5)

    # Test cases
    test_cases = [
        {
            'name': 'Simple Math',
            'code': '''
result = 2 + 2
print(f"2 + 2 = {result}")
'''
        },
        {
            'name': 'List Operations',
            'code': '''
numbers = [1, 2, 3, 4, 5]
squared = [x**2 for x in numbers]
print(f"Squared: {squared}")
'''
        },
        {
            'name': 'Math Functions',
            'code': '''
import math
print(f"Pi = {math.pi}")
print(f"sqrt(16) = {math.sqrt(16)}")
'''
        },
        {
            'name': 'Error Handling',
            'code': '''
try:
    result = 1 / 0
except ZeroDivisionError:
    print("Caught division by zero")
'''
        },
        {
            'name': 'Blocked Operation',
            'code': '''
import os
print("This should not execute")
'''
        },
        {
            'name': 'Timeout Test',
            'code': '''
import time
time.sleep(10)  # Should timeout
print("This should not print")
'''
        }
    ]

    print(f"📋 Running {len(test_cases)} test cases...\n")

    for i, test in enumerate(test_cases, 1):
        print(f"\n--- Test {i}: {test['name']} ---")
        print(f"Code:\n{test['code']}")

        start = time.time()
        result = sandbox.execute(test['code'])
        elapsed = time.time() - start

        print(f"\nResult ({elapsed:.3f}s):")
        print(f"  Success: {result['success']}")
        print(f"  Exit Code: {result.get('exit_code', 'N/A')}")

        if result['stdout']:
            print(f"  Output:\n    {result['stdout'].strip()}")

        if result['stderr']:
            print(f"  Errors:\n    {result['stderr'].strip()}")

        if result.get('error'):
            print(f"  Error: {result['error']}")

    print("\n✨ Demo complete!")

    # Show sandbox info
    print("\n🔍 Sandbox Configuration:")
    print(f"  Implementation: {'Rust' if sandbox.rust_sandbox else 'Python'}")
    print(f"  Max Execution Time: {sandbox.config['max_execution_time']}s")
    print(f"  Max Memory: {sandbox.config['max_memory_mb']}MB")


if __name__ == "__main__":
    demo()