"""
测试运行脚本
提供便捷的测试执行和报告生成
"""

import os
import sys
import subprocess
import argparse
from datetime import datetime
from pathlib import Path
import json


def run_command(cmd, capture_output=True):
    """运行命令并返回结果"""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=capture_output,
        text=True
    )
    return result


def run_unit_tests(coverage=True, html_report=False):
    """运行单元测试"""
    print("\n=== Running Unit Tests ===")

    cmd = ["python", "-m", "pytest", "tests/test_api.py", "-v"]

    if coverage:
        cmd.extend([
            "--cov=.",
            "--cov-report=term-missing"
        ])

        if html_report:
            cmd.extend(["--cov-report=html"])
            print("Coverage HTML report will be generated in htmlcov/")

    result = run_command(cmd)

    if result.returncode == 0:
        print("✅ Unit tests passed")
    else:
        print("❌ Unit tests failed")
        print(result.stdout)
        print(result.stderr)

    return result.returncode == 0


def run_integration_tests():
    """运行集成测试"""
    print("\n=== Running Integration Tests ===")

    cmd = [
        "python", "-m", "pytest",
        "tests/test_integration.py",
        "-v",
        "-m", "asyncio"
    ]

    result = run_command(cmd)

    if result.returncode == 0:
        print("✅ Integration tests passed")
    else:
        print("❌ Integration tests failed")
        print(result.stdout)
        print(result.stderr)

    return result.returncode == 0


def run_performance_tests():
    """运行性能测试"""
    print("\n=== Running Performance Tests ===")

    # 检查k6是否安装
    k6_check = run_command(["which", "k6"])
    if k6_check.returncode != 0:
        print("❌ k6 is not installed. Skipping performance tests")
        print("Install k6: https://k6.io/docs/get-started/installation/")
        return True  # 不将k6缺失视为失败

    # 运行性能测试
    cmd = [
        "k6", "run",
        "--out", "json=performance_results.json",
        "tests/performance/smoke_test.js"
    ]

    result = run_command(cmd, capture_output=False)

    if result.returncode == 0:
        print("✅ Performance tests passed")

        # 生成简单的报告
        generate_performance_report()
    else:
        print("❌ Performance tests failed")

    return result.returncode == 0


def generate_performance_report():
    """生成性能测试报告"""
    try:
        with open("performance_results.json", "r") as f:
            data = json.load(f)

        # 计算统计信息
        response_times = []
        errors = 0

        for metric in data.get("metrics", {}).values():
            if metric.get("type") == "Point" and "data" in metric:
                for point in metric["data"]["samples"]:
                    if "value" in point:
                        if metric.get("name") == "http_req_duration":
                            response_times.append(point["value"])
                        elif metric.get("name") == "http_req_failed":
                            errors += point["value"]

        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
            max_response_time = max(response_times)
            p95_response_time = sorted(response_times)[int(len(response_times) * 0.95)]

            print("\n=== Performance Test Summary ===")
            print(f"Total Requests: {len(response_times)}")
            print(f"Average Response Time: {avg_response_time:.2f}ms")
            print(f"95th Percentile: {p95_response_time:.2f}ms")
            print(f"Max Response Time: {max_response_time:.2f}ms")
            print(f"Error Rate: {(errors / len(response_times) * 100):.2f}%")

    except Exception as e:
        print(f"Failed to generate performance report: {e}"


def run_linting():
    """运行代码检查"""
    print("\n=== Running Code Quality Checks ===")

    tools = [
        ("black", ["black", "--check", "."], "Code formatting"),
        ("isort", ["isort", "--check-only", "."], "Import sorting"),
        ("flake8", ["flake8", "."], "Linting"),
        ("mypy", ["mypy", "."], "Type checking"),
    ]

    all_passed = True

    for tool_name, cmd, description in tools:
        print(f"\nChecking {description} with {tool_name}...")

        # 检查工具是否安装
        check_cmd = run_command(["which", tool_name])
        if check_cmd.returncode != 0:
            print(f"⚠️ {tool_name} not installed. Skipping.")
            continue

        result = run_command(cmd)

        if result.returncode == 0:
            print(f"✅ {description} passed")
        else:
            print(f"❌ {description} failed")
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr)
            all_passed = False

    return all_passed


def run_security_scan():
    """运行安全扫描"""
    print("\n=== Running Security Scan ===")

    # 检查bandit
    bandit_check = run_command(["which", "bandit"])
    if bandit_check.returncode != 0:
        print("⚠️ bandit not installed. Install with: pip install bandit")
        return True

    cmd = ["bandit", "-r", ".", "-x", "tests/"]
    result = run_command(cmd)

    if result.returncode == 0:
        print("✅ Security scan passed")
    else:
        print("❌ Security scan found issues")
        print(result.stdout)

    return result.returncode == 0


def generate_test_report(unit_ok, integration_ok, performance_ok, linting_ok, security_ok):
    """生成测试报告"""
    report = {
        "timestamp": datetime.now().isoformat(),
        "results": {
            "unit_tests": unit_ok,
            "integration_tests": integration_ok,
            "performance_tests": performance_ok,
            "code_quality": linting_ok,
            "security_scan": security_ok
        },
        "summary": {
            "total_checks": 5,
            "passed": sum([unit_ok, integration_ok, performance_ok, linting_ok, security_ok]),
            "failed": 5 - sum([unit_ok, integration_ok, performance_ok, linting_ok, security_ok])
        }
    }

    # 保存报告
    report_file = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)

    # 打印摘要
    print("\n" + "="*50)
    print("TEST SUMMARY")
    print("="*50)
    print(f"Unit Tests: {'✅ PASS' if unit_ok else '❌ FAIL'}")
    print(f"Integration Tests: {'✅ PASS' if integration_ok else '❌ FAIL'}")
    print(f"Performance Tests: {'✅ PASS' if performance_ok else '❌ FAIL'}")
    print(f"Code Quality: {'✅ PASS' if linting_ok else '❌ FAIL'}")
    print(f"Security Scan: {'✅ PASS' if security_ok else '❌ FAIL'}")
    print("-"*50)
    print(f"Overall: {'✅ ALL TESTS PASSED' if report['summary']['failed'] == 0 else '❌ SOME TESTS FAILED'}")
    print(f"Report saved to: {report_file}")

    return report['summary']['failed'] == 0


def main():
    parser = argparse.ArgumentParser(description="Test runner for AgenticGen")
    parser.add_argument(
        "--unit",
        action="store_true",
        help="Run unit tests only"
    )
    parser.add_argument(
        "--integration",
        action="store_true",
        help="Run integration tests only"
    )
    parser.add_argument(
        "--performance",
        action="store_true",
        help="Run performance tests only"
    )
    parser.add_argument(
        "--lint",
        action="store_true",
        help="Run linting only"
    )
    parser.add_argument(
        "--security",
        action="store_true",
        help="Run security scan only"
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        default=True,
        help="Generate coverage report"
    )
    parser.add_argument(
        "--no-coverage",
        action="store_true",
        help="Skip coverage report"
    )
    parser.add_argument(
        "--html-coverage",
        action="store_true",
        help="Generate HTML coverage report"
    )

    args = parser.parse_args()

    # 确保在项目根目录
    os.chdir(Path(__file__).parent.parent)

    # 运行测试
    results = {
        "unit": True,
        "integration": True,
        "performance": True,
        "linting": True,
        "security": True
    }

    if args.unit or not any([args.unit, args.integration, args.performance, args.lint, args.security]):
        coverage = args.coverage and not args.no_coverage
        results["unit"] = run_unit_tests(
            coverage=coverage,
            html_report=args.html_coverage
        )

    if args.integration or not any([args.unit, args.integration, args.performance, args.lint, args.security]):
        results["integration"] = run_integration_tests()

    if args.performance or not any([args.unit, args.integration, args.performance, args.lint, args.security]):
        results["performance"] = run_performance_tests()

    if args.lint or not any([args.unit, args.integration, args.performance, args.lint, args.security]):
        results["linting"] = run_linting()

    if args.security or not any([args.unit, args.integration, args.performance, args.lint, args.security]):
        results["security"] = run_security_scan()

    # 生成报告
    success = generate_test_report(
        results["unit"],
        results["integration"],
        results["performance"],
        results["linting"],
        results["security"]
    )

    # 设置退出码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()