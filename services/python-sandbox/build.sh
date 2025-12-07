#!/bin/bash

# Build script for Rust Python Sandbox

set -e

echo "🔒 Building Rust Python Sandbox..."

# Check if Rust is installed
if ! command -v cargo &> /dev/null; then
    echo "❌ Rust is not installed. Please install Rust from https://rustup.rs/"
    exit 1
fi

# Build release version
echo "🔨 Building optimized library..."
cargo build --release

# Run tests
echo "🧪 Running tests..."
cargo test

# Check if the library was created
if [ ! -f "target/release/libpython_sandbox.so" ]; then
    echo "❌ Build failed! Library not found."
    exit 1
fi

echo "✅ Build successful!"
echo "   Library location: $(pwd)/target/release/libpython_sandbox.so"

# Show library info
echo ""
echo "📊 Library info:"
file target/release/libpython_sandbox.so
ls -lh target/release/libpython_sandbox.so

echo ""
echo "🎯 Build completed successfully!"
echo ""
echo "To use the Python sandbox:"
echo "  Python: python3 python_wrapper.py"
echo "  Rust:   Add python-sandbox to your Cargo.toml"
echo ""
echo "Security Features:"
echo "  - Process isolation with fork()"
echo "  - Memory usage limits (rlimit)"
echo "  - Execution time limits"
echo "  - Module import restrictions"
echo "  - Built-in function filtering"
echo "  - Filesystem isolation"
echo "  - Network isolation"
echo ""
echo "Performance:"
echo "  - Near-native execution speed"
echo "  - Low overhead security layer"
echo "  - Concurrent execution support"