#!/bin/bash

# Build script for Rust metrics collector

set -e

echo "🔨 Building Rust Metrics Collector..."

# Check if Rust is installed
if ! command -v cargo &> /dev/null; then
    echo "❌ Rust is not installed. Please install Rust from https://rustup.rs/"
    exit 1
fi

# Set environment variables for optimization
export RUSTFLAGS="-C target-cpu=native -C opt-level=3"
export CARGO_TARGET_DIR="target"

# Clean previous builds
echo "🧹 Cleaning previous builds..."
cargo clean

# Build release version with optimizations
echo "📦 Building optimized release version..."
cargo build --release

# Check if the library was created
LIBRARY_PATH="target/release/libmetrics_collector.so"

if [ -f "$LIBRARY_PATH" ]; then
    echo "✅ Build successful!"
    echo "   Library location: $(pwd)/$LIBRARY_PATH"

    # Copy library to a more accessible location
    cp "$LIBRARY_PATH" "./libmetrics_collector.so"
    echo "   Copied to: $(pwd)/libmetrics_collector.so"

    # Show library info
    echo "📊 Library info:"
    file "$LIBRARY_PATH"
    ls -lh "$LIBRARY_PATH"

    # Test Python integration
    echo ""
    echo "🧪 Testing Python integration..."
    python3 python_wrapper.py

else
    echo "❌ Build failed! Please check the output above for errors."
    exit 1
fi

echo ""
echo "🎯 Build completed successfully!"
echo ""
echo "The Rust metrics collector is ready to use."
echo "Python wrapper will automatically detect and use the Rust implementation."
echo ""
echo "To run benchmarks:"
echo "  python python_wrapper.py"