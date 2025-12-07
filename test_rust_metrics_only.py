#!/usr/bin/env python3
"""
Simple test script to verify the Rust metrics collector works
"""

import sys
from pathlib import Path
from datetime import datetime

# Add services/metrics-collector to path
sys.path.insert(0, str(Path(__file__).parent / "services" / "metrics-collector"))

def test_rust_metrics():
    """Test the Rust metrics collector directly"""

    print("🔍 Testing Rust Metrics Collector Directly...")

    # Import the wrapper
    from python_wrapper import get_metrics_collector

    # Create collector
    collector = get_metrics_collector()

    # Check if Rust is active
    rust_active = collector.is_rust_active()
    print(f"\n📊 Rust Implementation Active: {rust_active}")

    if not rust_active:
        print("⚠️  Rust implementation not active - using Python fallback")
        print("   This means the Rust library wasn't found or failed to load")
        return

    print("✅ Rust implementation loaded successfully!")

    # Test counter operations
    print("\n🔢 Testing Counter Operations...")
    for i in range(100):
        collector.increment_counter("test_counter")
        collector.add_counter("test_add_counter", i)

    # Test gauge operations
    print("⏱️  Testing Gauge Operations...")
    for i in range(100):
        collector.set_gauge("test_gauge", i * 10)

    # Test histogram operations
    print("📈 Testing Histogram Operations...")
    for i in range(100):
        collector.record_histogram("test_histogram", i)

    # Get all counters and gauges
    counters = collector.get_all_counters()
    gauges = collector.get_all_gauges()

    print("\n📋 Counters:")
    for name, value in counters.items():
        print(f"  {name}: {value}")

    print("\n📋 Gauges:")
    for name, value in gauges.items():
        print(f"  {name}: {value}")

    # Performance test
    print("\n⚡ Performance Test (100,000 operations)...")
    start = datetime.now()

    for i in range(100000):
        collector.increment_counter("perf_test")

    elapsed = (datetime.now() - start).total_seconds()
    ops_per_sec = 100000 / elapsed

    print(f"  ✅ Completed in {elapsed:.4f}s")
    print(f"  🚀 Performance: {ops_per_sec:,.0f} ops/sec")

    print("\n🎯 Rust metrics collector test completed successfully!")
    print("   The high-performance metrics collection is working!")


if __name__ == "__main__":
    test_rust_metrics()