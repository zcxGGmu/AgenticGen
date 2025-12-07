"""
Python wrapper for Rust metrics collector
Provides seamless integration with existing Python code
"""

import ctypes
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import threading
import warnings

# Try to load the compiled Rust library
try:
    # Get the directory of this file
    current_dir = Path(__file__).parent

    # Try different possible library names and locations
    possible_lib_paths = [
        current_dir / "target/release" / "libmetrics_collector.so",
        current_dir / "target/debug" / "libmetrics_collector.so",
        current_dir / "libmetrics_collector.so",
        current_dir.parent.parent / "target" / "x86_64-unknown-linux-gnu" / "release" / "libmetrics_collector.so",
    ]

    lib_path = None
    for path in possible_lib_paths:
        if path.exists():
            lib_path = path
            break

    if lib_path is None:
        raise ImportError(
            "Rust metrics collector library not found. "
            "Please run `cargo build --release` in the metrics-collector directory."
        )

    # Load the Rust library
    rust_lib = ctypes.CDLL(str(lib_path))

    # Define the FFI interface
    rust_lib.collector_new.restype = ctypes.c_void_p
    rust_lib.collector_drop.restype = None
    rust_lib.collector_increment_counter.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    rust_lib.add_counter.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint64]
    rust_lib.get_counter.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    rust_lib.get_counter.restype = ctypes.c_uint64

    rust_lib.set_gauge.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint64]
    rust_lib.get_gauge.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    rust_lib.get_gauge.restype = ctypes.c_uint64

    rust_lib.record_histogram.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint64]
    rust_lib.record_timing.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint64]

    rust_lib.get_all_counters.restype = ctypes.POINTER(ctypes.c_char_p)
    rust_lib.get_all_gauges.restype = ctypes.POINTER(ctypes.c_char_p)

    rust_lib.reset_all.argtypes = [ctypes.c_void_p]

    # Success flag
    _RUST_LOADED = True
    print(f"✅ Rust metrics collector loaded from: {lib_path}")

except ImportError as e:
    _RUST_LOADED = False
    print(f"⚠️ Rust metrics collector not available: {e}")
    print("   Falling back to Python implementation")
    rust_lib = None


class RustMetricsCollector:
    """Python wrapper for the Rust metrics collector"""

    def __init__(self):
        self._collector = None
        self._python_fallback = RustPythonFallback()
        self._rust_lib = globals().get('rust_lib')

        if self._rust_lib:
            try:
                # Create Rust collector instance
                self._collector = self._rust_lib.collector_new()
                if not self._collector:
                    raise RuntimeError("Failed to create Rust collector instance")
            except Exception as e:
                print(f"⚠️ Failed to initialize Rust collector: {e}")
                print("   Falling back to Python implementation")
                self._rust_lib = None
                self._python_fallback = RustPythonFallback()

    def __del__(self):
        """Cleanup Rust collector instance"""
        if self._collector and self._rust_lib:
            self._rust_lib.collector_drop(self._collector)

    def increment_counter(self, name: str) -> None:
        """Increment a counter by 1"""
        self.add_counter(name, 1)

    def add_counter(self, name: str, value: int) -> None:
        """Add value to a counter"""
        if self._collector and self._rust_lib:
            try:
                name_bytes = name.encode('utf-8')
                self._rust_lib.add_counter(self._collector, name_bytes, value)
            except Exception as e:
                warnings.warn(f"Rust counter operation failed: {e}")
                self._python_fallback.add_counter(name, value)
        else:
            self._python_fallback.add_counter(name, value)

    def set_gauge(self, name: str, value: int) -> None:
        """Set a gauge value"""
        if self._collector and self._rust_lib:
            try:
                name_bytes = name.encode('utf-8')
                self._rust_lib.set_gauge(self._collector, name_bytes, value)
            except Exception as e:
                warnings.warn(f"Rust gauge operation failed: {e}")
                self._python_fallback.set_gauge(name, value)
        else:
            self._python_fallback.set_gauge(name, value)

    def get_counter(self, name: str) -> Optional[int]:
        """Get current counter value"""
        if self._collector and self._rust_lib:
            try:
                name_bytes = name.encode('utf-8')
                value = self._rust_lib.get_counter(self._collector, name_bytes)
                return value if value < 2**63 else None  # Check for error value
            except Exception as e:
                warnings.warn(f"Rust get counter failed: {e}")
                return self._python_fallback.get_counter(name)
        else:
            return self._python_fallback.get_counter(name)

    def get_gauge(self, name: str) -> Optional[int]:
        """Get current gauge value"""
        if self._collector and self._rust_lib:
            try:
                name_bytes = name.encode('utf-8')
                value = self._rust_lib.get_gauge(self._collector, name_bytes)
                return value if value < 2**63 else None  # Check for error value
            except Exception as e:
                warnings.warn(f"Rust get gauge failed: {e}")
                return self._python_fallback.get_gauge(name)
        else:
            return self._python_fallback.get_gauge(name)

    def record_histogram(self, name: str, value: int) -> None:
        """Record a value in a histogram"""
        if self._collector and self._rust_lib:
            try:
                name_bytes = name.encode('utf-8')
                self._rust_lib.record_histogram(self._collector, name_bytes, value)
            except Exception as e:
                warnings.warn(f"Rust histogram operation failed: {e}")
                self._python_fallback.record_histogram(name, value)
        else:
            self._python_fallback.record_histogram(name, value)

    def record_timing(self, name: str, duration: timedelta) -> None:
        """Record a timing in milliseconds"""
        millis = int(duration.total_seconds() * 1000)
        histogram_name = f"{name}_ms"
        self.record_histogram(histogram_name, millis)

    def get_all_counters(self) -> Dict[str, int]:
        """Get all counter values"""
        if self._collector and self._rust_lib:
            try:
                result_ptr = self._rust_lib.get_all_counters(self._collector)
                if result_ptr:
                    # Convert C string to Python dict
                    c_str = ctypes.c_char_p(result_ptr)
                    json_str = ctypes.string_at(result_ptr)

                    # Parse JSON (Rust should return JSON string)
                    import json
                    return json.loads(json_str)
                return {}
            except Exception as e:
                warnings.warn(f"Rust get all counters failed: {e}")
                return self._python_fallback.get_all_counters()
        else:
            return self._python_fallback.get_all_counters()

    def get_all_gauges(self) -> Dict[str, int]:
        """Get all gauge values"""
        if self._collector and self._rust_lib:
            try:
                result_ptr = self._rust_lib.get_all_gauges(self._collector)
                if result_ptr:
                    # Convert C string to Python dict
                    c_str = ctypes.c_char_p(result_ptr)
                    json_str = ctypes.string_at(result_ptr)

                    # Parse JSON
                    import json
                    return json.loads(json_str)
                return {}
            except Exception as e:
                warnings.warn(f"Rust get all gauges failed: {e}")
                return self._python_fallback.get_all_gauges()
        else:
            return self._python_fallback.get_all_gauges()

    def reset_all(self) -> None:
        """Reset all metrics"""
        if self._collector and self._rust_lib:
            try:
                self._rust_lib.reset_all(self._collector)
            except Exception as e:
                warnings.warn(f"Rust reset failed: {e}")
                self._python_fallback.reset_all()
        else:
            self._python_fallback.reset_all()

    def is_rust_active(self) -> bool:
        """Check if Rust implementation is active"""
        return self._collector is not None and self._rust_lib is not None


class RustPythonFallback:
    """Fallback Python implementation when Rust is not available"""

    def __init__(self):
        self._counters = {}
        self._gauges = {}
        self._histograms = {}
        self._lock = threading.RLock()

    def increment_counter(self, name: str) -> None:
        """Increment a counter by 1"""
        self.add_counter(name, 1)

    def add_counter(self, name: str, value: int) -> None:
        """Add value to a counter"""
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + value

    def set_gauge(self, name: str, value: int) -> None:
        """Set a gauge value"""
        with self._lock:
            self._gauges[name] = value

    def get_counter(self, name: str) -> Optional[int]:
        """Get current counter value"""
        with self._lock:
            return self._counters.get(name)

    def get_gauge(self, name: str) -> Optional[int]:
        """Get current gauge value"""
        with self._lock:
            return self._gauges.get(name)

    def record_histogram(self, name: str, value: int) -> None:
        """Record a value in a histogram (simplified version)"""
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = {
                    'count': 0,
                    'sum': 0,
                    'min': float('inf'),
                    'max': float('-inf'),
                    'values': []
                }

            hist = self._histograms[name]
            hist['count'] += 1
            hist['sum'] += value
            hist['min'] = min(hist['min'], value)
            hist['max'] = max(hist['max'], value)

            # Keep only last 1000 values to avoid memory issues
            if len(hist['values']) < 1000:
                hist['values'].append(value)

    def record_timing(self, name: str, duration: timedelta) -> None:
        """Record a timing in milliseconds"""
        millis = int(duration.total_seconds() * 1000)
        self.record_histogram(f"{name}_ms", millis)

    def get_all_counters(self) -> Dict[str, int]:
        """Get all counter values"""
        with self._lock:
            return self._counters.copy()

    def get_all_gauges(self) -> Dict[str, int]:
        """Get all gauge values"""
        with self._lock:
            return self._gauges.copy()

    def reset_all(self) -> None:
        """Reset all metrics"""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()


# Global metrics collector instance
_metrics_collector = None

def get_metrics_collector() -> RustMetricsCollector:
    """Get the global metrics collector instance"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = RustMetricsCollector()
    return _metrics_collector


# Convenience functions that work with the global instance
def increment_counter(name: str) -> None:
    """Increment a global counter"""
    get_metrics_collector().increment_counter(name)

def add_counter(name: str, value: int) -> None:
    """Add value to a global counter"""
    get_metrics_collector().add_counter(name, value)

def set_gauge(name: str, value: int) -> None:
    """Set a global gauge value"""
    get_metrics_collector().set_gauge(name, value)

def record_histogram(name: str, value: int) -> None:
    """Record a value in a global histogram"""
    get_metrics_collector().record_histogram(name, value)

def record_timing(name: str, duration: timedelta) -> None:
    """Record a timing in a global histogram"""
    get_metrics_collector().record_timing(name, duration)

def get_counter(name: str) -> Optional[int]:
    """Get global counter value"""
    return get_metrics_collector().get_counter(name)

def get_gauge(name: str) -> Optional[int]:
    """Get global gauge value"""
    return get_metrics_collector().get_gauge(name)

def get_all_counters() -> Dict[str, int]:
    """Get all global counters"""
    return get_metrics_collector().get_all_counters()

def get_all_gauges() -> Dict[str, int]:
    """Get all global gauges"""
    return get_metrics_collector().get_all_gauges()


# Performance comparison utilities
def benchmark_rust_vs_python(iterations: int = 100000):
    """Benchmark Rust vs Python implementation"""
    import time

    collector = get_metrics_collector()

    print(f"Benchmarking metrics collector with {iterations} operations...")

    # Test counter operations
    print("\n=== Counter Operations ===")

    # Test increment_counter
    start = time.perf_counter()
    for i in range(iterations):
        collector.increment_counter("benchmark_counter")
    rust_increment_time = time.perf_counter() - start
    print(f"Increment Counter: {rust_increment_time:.4f}s ({iterations/rust_increment_time:.0f} ops/sec)")

    # Test add_counter
    start = time.perf_counter()
    for i in range(iterations):
        collector.add_counter("benchmark_add", i)
    rust_add_time = time.perf_counter() - start
    print(f"Add Counter: {rust_add_time:.4f}s ({iterations/rust_add_time:.0f} ops/sec)")

    # Test set_gauge
    start = time.perf_counter()
    for i in range(iterations):
        collector.set_gauge("benchmark_gauge", i)
    rust_gauge_time = time.perf_counter() - start
    print(f"Set Gauge: {rust_gauge_time:.4f}s ({iterations/rust_gauge_time:.0f} ops/sec)")

    # Test get operations
    start = time.perf_counter()
    for i in range(iterations):
        _ = collector.get_counter("benchmark_counter")
        _ = collector.get_gauge("benchmark_gauge")
    rust_get_time = time.perf_counter() - start
    print(f"Get Operations: {rust_get_time:.4f}s ({(iterations*2)/rust_get_time:.0f} ops/sec)")

    print(f"\nRust Implementation Status: {'✅ Active' if collector.is_rust_active() else '❌ Python Fallback'}")


if __name__ == "__main__":
    # Run benchmark when executed directly
    benchmark_rust_vs_python(100000)