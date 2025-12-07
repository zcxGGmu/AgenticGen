#!/usr/bin/env python3
"""
Test script to verify the Rust metrics collector integration
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

async def test_metrics_integration():
    """Test metrics collection with Rust backend"""

    # Import after path is set
    from monitoring.metrics_collector import MetricsCollector

    print("🔍 Testing Metrics Collector Integration...")

    # Create metrics collector instance
    collector = MetricsCollector()

    # Check Rust status
    rust_status = collector.get_rust_status()
    print("\n📊 Rust Status:")
    for key, value in rust_status.items():
        print(f"  {key}: {value}")

    # Test counter operations
    print("\n🔢 Testing Counter Operations...")
    for i in range(10):
        await collector.increment_counter("test_requests", 1)

    # Test gauge operations
    print("⏱️  Testing Gauge Operations...")
    for i in range(10):
        await collector.set_gauge("active_connections", i * 10)

    # Test histogram operations
    print("📈 Testing Histogram Operations...")
    for i in range(100):
        await collector.record_histogram("response_time_ms", i)

    # Get Rust counters and gauges
    rust_counters = await collector.get_all_rust_counters()
    rust_gauges = await collector.get_all_rust_gauges()

    print("\n📋 Rust Counters:")
    for name, value in rust_counters.items():
        print(f"  {name}: {value}")

    print("\n📋 Rust Gauges:")
    for name, value in rust_gauges.items():
        print(f"  {name}: {value}")

    # Test performance with timing
    print("\n⚡ Performance Test (10,000 operations)...")
    start = datetime.now()

    for i in range(10000):
        await collector.increment_counter("perf_test", 1)

    elapsed = (datetime.now() - start).total_seconds()
    ops_per_sec = 10000 / elapsed

    print(f"  ✅ Completed in {elapsed:.4f}s")
    print(f"  🚀 Performance: {ops_per_sec:,.0f} ops/sec")

    print("\n✅ Metrics integration test completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_metrics_integration())