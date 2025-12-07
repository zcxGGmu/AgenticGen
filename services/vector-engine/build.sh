#!/bin/bash

# Build script for Rust Vector Engine

set -e

echo "🚀 Building Rust Vector Engine..."

# Check if Rust is installed
if ! command -v cargo &> /dev/null; then
    echo "❌ Rust is not installed. Please install Rust from https://rustup.rs/"
    exit 1
fi

# Build release version with optimizations
echo "🔨 Building optimized library..."
cargo build --release

# Run tests
echo "🧪 Running tests..."
cargo test

# Run benchmarks if nightly toolchain is available
if cargo +nightly --version &> /dev/null; then
    echo "📊 Running benchmarks..."
    cargo +nightly bench --bench vector_ops
else
    echo "⚠️ Nightly toolchain not found. Skipping benchmarks."
    echo "   Install with: rustup toolchain install nightly"
fi

# Check if the library was created
if [ ! -f "target/release/libvector_engine.so" ]; then
    echo "❌ Build failed! Library not found."
    exit 1
fi

echo "✅ Build successful!"
echo "   Library location: $(pwd)/target/release/libvector_engine.so"

# Show library info
echo ""
echo "📊 Library info:"
file target/release/libvector_engine.so
ls -lh target/release/libvector_engine.so

echo ""
echo "🎯 Build completed successfully!"
echo ""
echo "To use the vector engine:"
echo "  Python: python python_wrapper.py"
echo "  Rust:   Add vector_engine to your Cargo.toml"
echo ""
echo "Features:"
echo "  - SIMD-optimized cosine similarity (up to 30x faster)"
echo "  - Parallel batch operations"
echo "  - In-memory vector storage"
echo "  - Multiple distance metrics"
echo "  - C FFI for Python integration"