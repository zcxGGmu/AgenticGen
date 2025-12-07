#!/bin/bash

# Build script for Go Orchestration Engine

set -e

echo "🚀 Building Go Orchestration Engine..."

# Check if Go is installed
if ! command -v go &> /dev/null; then
    echo "❌ Go is not installed. Please install Go from https://golang.org/"
    exit 1
fi

# Set environment variables for optimization
export CGO_ENABLED=0
export GOOS=linux
export GOARCH=amd64

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -f main

# Download dependencies
echo "📦 Downloading dependencies..."
go mod download
go mod tidy

# Run tests
echo "🧪 Running tests..."
go test ./...

# Build the application
echo "🔨 Building optimized binary..."
go build -ldflags="-w -s" -o main .

# Check if the binary was created
if [ ! -f "main" ]; then
    echo "❌ Build failed! Please check the output above for errors."
    exit 1
fi

echo "✅ Build successful!"
echo "   Binary location: $(pwd)/main"

# Show binary info
echo "📊 Binary info:"
file main
ls -lh main

echo ""
echo "🎯 Build completed successfully!"
echo ""
echo "To run the orchestration engine:"
echo "  ./main"
echo ""
echo "Environment variables:"
echo "  HTTP_PORT=8080      # HTTP API port"
echo "  GRPC_PORT=9090     # gRPC port"
echo "  LOG_LEVEL=info     # Log level (debug, info, warn, error)"