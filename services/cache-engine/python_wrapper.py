"""
Python wrapper for Rust cache engine
Provides seamless integration with existing Python code
"""

import ctypes
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import json
import warnings

# Try to load the compiled Rust library
try:
    # Get the directory of this file
    current_dir = Path(__file__).parent

    # Try different possible library names and locations
    possible_lib_paths = [
        current_dir / "target/release" / "libcache_engine.so",
        current_dir / "target/debug" / "libcache_engine.so",
        current_dir / "libcache_engine.so",
        current_dir.parent.parent / "target" / "x86_64-unknown-linux-gnu" / "release" / "libcache_engine.so",
    ]

    lib_path = None
    for path in possible_lib_paths:
        if path.exists():
            lib_path = path
            break

    if lib_path is None:
        raise ImportError(
            "Rust cache engine library not found. "
            "Please run `cargo build --release` in the cache-engine directory."
        )

    # Load the Rust library
    rust_lib = ctypes.CDLL(str(lib_path))

    # Define the FFI interface
    rust_lib.cache_engine_new.restype = ctypes.c_void_p
    rust_lib.cache_engine_drop.restype = None
    rust_lib.cache_get.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)), ctypes.POINTER(ctypes.c_size_t)]
    rust_lib.cache_get.restype = ctypes.c_bool
    rust_lib.cache_set.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_ubyte), ctypes.c_size_t, ctypes.c_uint64]
    rust_lib.cache_set.restype = ctypes.c_bool
    rust_lib.cache_delete.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    rust_lib.cache_delete.restype = ctypes.c_bool
    rust_lib.cache_clear.argtypes = [ctypes.c_void_p]
    rust_lib.cache_clear.restype = ctypes.c_bool
    rust_lib.cache_get_stats.argtypes = [ctypes.c_void_p]
    rust_lib.cache_get_stats.restype = ctypes.POINTER(ctypes.c_char)

    # Success flag
    _RUST_LOADED = True
    print(f"✅ Rust cache engine loaded from: {lib_path}")

except ImportError as e:
    _RUST_LOADED = False
    print(f"⚠️ Rust cache engine not available: {e}")
    print("   Falling back to Python implementation")
    rust_lib = None


class RustCacheEngine:
    """Python wrapper for the Rust cache engine"""

    def __init__(self):
        self._engine = None
        self._python_fallback = RustPythonFallback()
        self._rust_lib = globals().get('rust_lib')

        if self._rust_lib:
            try:
                # Create Rust engine instance
                self._engine = self._rust_lib.cache_engine_new()
                if not self._engine:
                    raise RuntimeError("Failed to create Rust engine instance")
            except Exception as e:
                print(f"⚠️ Failed to initialize Rust engine: {e}")
                print("   Falling back to Python implementation")
                rust_lib = None
                self._python_fallback = RustPythonFallback()

    def __del__(self):
        """Cleanup Rust engine instance"""
        if self._engine and self._rust_lib:
            self._rust_lib.cache_engine_drop(self._engine)

    def get(self, key: str) -> Optional[bytes]:
        """Get a value from cache"""
        if self._engine and self._rust_lib:
            try:
                key_bytes = key.encode('utf-8')
                value_out = ctypes.POINTER(ctypes.c_ubyte)()
                value_len = ctypes.c_size_t()

                success = self._rust_lib.cache_get(self._engine, key_bytes, ctypes.byref(value_out), ctypes.byref(value_len))

                if success and value_len.value > 0:
                    # Convert C array to Python bytes
                    buffer = (ctypes.c_ubyte * value_len.value).from_address(value_out)
                    result = bytes(buffer)
                    # Note: In production, we should free the C memory
                    return result
            except Exception as e:
                warnings.warn(f"Rust get operation failed: {e}")
                return self._python_fallback.get(key)
        else:
            return self._python_fallback.get(key)

        return None

    def set(self, key: str, value: bytes, ttl_seconds: int = 0) -> bool:
        """Set a value in cache"""
        if self._engine and self._rust_lib:
            try:
                key_bytes = key.encode('utf-8')
                value_ptr = ctypes.cast(value, ctypes.POINTER(ctypes.c_ubyte))
                value_len = len(value)

                return bool(self._rust_lib.cache_set(self._engine, key_bytes, value_ptr, value_len, ttl_seconds))
            except Exception as e:
                warnings.warn(f"Rust set operation failed: {e}")
                return self._python_fallback.set(key, value, ttl_seconds)
        else:
            return self._python_fallback.set(key, value, ttl_seconds)

    def delete(self, key: str) -> bool:
        """Delete a value from cache"""
        if self._engine and self._rust_lib:
            try:
                key_bytes = key.encode('utf-8')
                return bool(self._rust_lib.cache_delete(self._engine, key_bytes))
            except Exception as e:
                warnings.warn(f"Rust delete operation failed: {e}")
                return self._python_fallback.delete(key)
        else:
            return self._python_fallback.delete(key)

    def clear(self) -> bool:
        """Clear all cache entries"""
        if self._engine and self._rust_lib:
            try:
                return bool(self._rust_lib.cache_clear(self._engine))
            except Exception as e:
                warnings.warn(f"Rust clear operation failed: {e}")
                return self._python_fallback.clear()
        else:
            return self._python_fallback.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        if self._engine and self._rust_lib:
            try:
                stats_ptr = self._rust_lib.cache_get_stats(self._engine)
                if stats_ptr:
                    # Convert C string to Python dict
                    c_str = ctypes.c_char_p(stats_ptr)
                    json_str = ctypes.string_at(stats_ptr)

                    # Parse JSON
                    return json.loads(json_str)
                return {}
            except Exception as e:
                warnings.warn(f"Rust get stats failed: {e}")
                return self._python_fallback.get_stats()
        else:
            return self._python_fallback.get_stats()

    def is_rust_active(self) -> bool:
        """Check if Rust implementation is active"""
        return self._engine is not None and self._rust_lib is not None


class RustPythonFallback:
    """Fallback Python implementation when Rust is not available"""

    def __init__(self):
        self._cache = {}
        self._stats = {
            "l1_hits": 0,
            "l1_misses": 0,
            "evictions": 0,
            "total_operations": 0,
            "l1_size": 0
        }

    def get(self, key: str) -> Optional[bytes]:
        """Get a value from cache"""
        self._stats["total_operations"] += 1
        if key in self._cache:
            self._stats["l1_hits"] += 1
            return self._cache[key]
        else:
            self._stats["l1_misses"] += 1
            return None

    def set(self, key: str, value: bytes, ttl_seconds: int = 0) -> bool:
        """Set a value in cache"""
        self._cache[key] = value
        self._stats["l1_size"] = len(self._cache)
        return True

    def delete(self, key: str) -> bool:
        """Delete a value from cache"""
        if key in self._cache:
            del self._cache[key]
            self._stats["l1_size"] = len(self._cache)
            return True
        return False

    def clear(self) -> bool:
        """Clear all cache entries"""
        self._cache.clear()
        self._stats["l1_size"] = 0
        return True

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return self._stats.copy()


# Global cache engine instance
_cache_engine = None

def get_cache_engine() -> RustCacheEngine:
    """Get the global cache engine instance"""
    global _cache_engine
    if _cache_engine is None:
        _cache_engine = RustCacheEngine()
    return _cache_engine


# Convenience functions that work with the global instance
def get(key: str) -> Optional[bytes]:
    """Get a value from global cache"""
    return get_cache_engine().get(key)

def set(key: str, value: bytes, ttl_seconds: int = 0) -> bool:
    """Set a value in global cache"""
    return get_cache_engine().set(key, value, ttl_seconds)

def delete(key: str) -> bool:
    """Delete a value from global cache"""
    return get_cache_engine().delete(key)

def clear() -> bool:
    """Clear all global cache entries"""
    return get_cache_engine().clear()

def get_stats() -> Dict[str, Any]:
    """Get global cache statistics"""
    return get_cache_engine().get_stats()


# Performance comparison utilities
def benchmark_rust_vs_python(iterations: int = 100000):
    """Benchmark Rust vs Python cache implementation"""
    import time

    cache = get_cache_engine()

    print(f"Benchmarking cache engine with {iterations} operations...")

    # Test set operations
    print("\n=== Set Operations ===")
    start = time.perf_counter()
    for i in range(iterations):
        cache.set(f"key_{i}", f"value_{i}".encode(), 60)
    rust_set_time = time.perf_counter() - start
    print(f"Set Operations: {rust_set_time:.4f}s ({iterations/rust_set_time:.0f} ops/sec)")

    # Test get operations
    print("\n=== Get Operations ===")
    start = time.perf_counter()
    for i in range(iterations):
        _ = cache.get(f"key_{i % 1000}")  # Mix of hits and misses
    rust_get_time = time.perf_counter() - start
    print(f"Get Operations: {rust_get_time:.4f}s ({iterations/rust_get_time:.0f} ops/sec)")

    # Test get stats
    stats = cache.get_stats()
    print(f"\n📊 Cache Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print(f"\nRust Implementation Status: {'✅ Active' if cache.is_rust_active() else '❌ Python Fallback'}")


if __name__ == "__main__":
    # Run benchmark when executed directly
    benchmark_rust_vs_python(100000)