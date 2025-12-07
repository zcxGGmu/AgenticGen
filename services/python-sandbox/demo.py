#!/usr/bin/env python3
"""
Demo for the Python Sandbox without external dependencies
"""

import subprocess
import time
import tempfile
import os
import sys

class SimpleSandbox:
    """Simple Python sandbox implementation for demo"""

    def __init__(self, timeout=5, memory_limit=512):
        self.timeout = timeout
        self.memory_limit = memory_limit

    def execute(self, code, stdin=None):
        """Execute Python code with basic restrictions"""
        # Wrap code for safety
        code_lines = code.split('\n')
        indented_code = '\n'.join(f'    {line}' for line in code_lines if line.strip())

        wrapped = f'''import builtins
import sys

# Remove dangerous builtins
dangerous = ['open', 'file', 'input', 'exec', 'eval', 'compile']
for d in dangerous:
    if hasattr(builtins, d):
        delattr(builtins, d)

# User code
try:
{indented_code}
except Exception as e:
    print(f"Error: {{e}}", file=sys.stderr)
    sys.exit(1)
'''

        # Write to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(wrapped)
            temp_file = f.name

        try:
            # Run the code
            result = subprocess.run(
                [sys.executable, '-u', temp_file],
                input=stdin,
                text=True,
                capture_output=True,
                timeout=self.timeout
            )

            return {
                'success': result.returncode == 0,
                'exit_code': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'timeout': False
            }

        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'exit_code': -1,
                'stdout': '',
                'stderr': 'Execution timeout',
                'timeout': True
            }
        finally:
            # Clean up
            try:
                os.unlink(temp_file)
            except:
                pass

def demo():
    """Demonstrate the Python sandbox"""
    print("🔒 Python Sandbox Demo")
    print("=" * 50)

    # Create sandbox
    sandbox = SimpleSandbox(timeout=3)

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
print(f"Numbers: {numbers}")
print(f"Squared: {squared}")
'''
        },
        {
            'name': 'Math Functions',
            'code': '''
import math
print(f"Pi = {math.pi:.4f}")
print(f"sqrt(16) = {math.sqrt(16)}")
print(f"sin(pi/2) = {math.sin(math.pi/2)}")
'''
        },
        {
            'name': 'String Operations',
            'code': '''
text = "Hello, World!"
print(f"Original: {text}")
print(f"Upper: {text.upper()}")
print(f"Lower: {text.lower()}")
print(f"Length: {len(text)}")
'''
        },
        {
            'name': 'Error Handling',
            'code': '''
try:
    result = 1 / 0
except ZeroDivisionError as e:
    print(f"Caught error: {e}")
finally:
    print("Done with try block")
'''
        },
        {
            'name': 'Loop Example',
            'code': '''
# Calculate factorial
def factorial(n):
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result

print("Factorials:")
for n in range(1, 6):
    print(f"  {n}! = {factorial(n)}")
'''
        },
        {
            'name': 'Dictionary Operations',
            'code': '''
student = {
    "name": "Alice",
    "age": 20,
    "grades": [85, 92, 78]
}

print(f"Student: {student['name']}")
print(f"Age: {student['age']}")
print(f"Average grade: {sum(student['grades']) / len(student['grades']):.1f}")
'''
        },
        {
            'name': 'File Access (Blocked)',
            'code': '''
# This should fail
try:
    with open("/etc/passwd", "r") as f:
        content = f.read()
        print("File content:", content)
except NameError:
    print("open function not available (as expected)")
except Exception as e:
    print(f"Error: {e}")
'''
        },
        {
            'name': 'Timeout Test',
            'code': '''
import time
print("Starting long operation...")
time.sleep(5)  # Should timeout
print("This should not print")
'''
        }
    ]

    print(f"📋 Running {len(test_cases)} test cases...\n")

    total_time = 0
    passed = 0

    for i, test in enumerate(test_cases, 1):
        print(f"\n--- Test {i}: {test['name']} ---")
        print(f"Code preview: {test['code'][:100]}...")

        start = time.time()
        result = sandbox.execute(test['code'])
        elapsed = time.time() - start
        total_time += elapsed

        print(f"\nResult ({elapsed:.3f}s):")
        print(f"  Success: {result['success']}")
        print(f"  Exit Code: {result['exit_code']}")

        if result.get('timeout'):
            print("  Status: ⏰ TIMEOUT")
        elif result['success']:
            print("  Status: ✅ PASSED")
            passed += 1
        else:
            print("  Status: ❌ FAILED")

        if result['stdout']:
            print(f"  Output:\n    {result['stdout'].strip()}")

        if result['stderr']:
            print(f"  Errors:\n    {result['stderr'].strip()}")

    # Summary
    print(f"\n{'='*50}")
    print("📊 Summary:")
    print(f"  Total tests: {len(test_cases)}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {len(test_cases) - passed}")
    print(f"  Success rate: {passed/len(test_cases)*100:.1f}%")
    print(f"  Total time: {total_time:.3f}s")
    print(f"  Average per test: {total_time/len(test_cases):.3f}s")

    print("\n🔍 Sandbox Configuration:")
    print(f"  Timeout: {sandbox.timeout}s")
    print(f"  Memory limit: {sandbox.memory_limit}MB")

    print("\n✨ Demo complete!")

if __name__ == "__main__":
    demo()