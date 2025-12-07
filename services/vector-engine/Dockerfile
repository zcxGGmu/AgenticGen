# Build stage for Rust
FROM rust:1.75-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy source code
COPY Cargo.toml Cargo.lock ./
COPY src ./src

# Build the library
RUN cargo build --release

# Runtime stage
FROM python:3.10-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app

# Copy the compiled library from builder
COPY --from=builder /app/target/release/libvector_engine.so .
COPY python_wrapper.py .
COPY demo.py .

# Set LD_LIBRARY_PATH
ENV LD_LIBRARY_PATH=/app:$LD_LIBRARY_PATH

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python3 -c "import ctypes; lib = ctypes.CDLL('./libvector_engine.so'); exit(0 if lib else 1)"

# Default command
CMD ["python3", "demo.py"]