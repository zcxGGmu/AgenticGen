#!/usr/bin/env python3
"""
Simple demo for the Vector Engine without external dependencies
"""

import time
import random
import math

# Simple vector operations without numpy
def cosine_similarity(vec_a, vec_b):
    """Calculate cosine similarity between two vectors"""
    if len(vec_a) != len(vec_b):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)

def euclidean_distance(vec_a, vec_b):
    """Calculate Euclidean distance between two vectors"""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(vec_a, vec_b)))

def add_vectors(vec_a, vec_b):
    """Add two vectors"""
    return [a + b for a, b in zip(vec_a, vec_b)]

def normalize(vector):
    """Normalize vector to unit length"""
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        return vector
    return [v / norm for v in vector]

def demo():
    """Run vector engine demo"""
    print("🚀 Vector Engine Demo")
    print("=" * 50)

    # Generate test vectors
    random.seed(42)

    # Test with different dimensions
    dimensions = [128, 256, 512, 768, 1024]

    for dim in dimensions:
        print(f"\n📏 Testing with {dim}D vectors:")

        # Create random vectors
        vec_a = [random.random() for _ in range(dim)]
        vec_b = [random.random() for _ in range(dim)]

        # Normalize vectors
        vec_a_norm = normalize(vec_a)
        vec_b_norm = normalize(vec_b)

        # Calculate similarity
        similarity = cosine_similarity(vec_a_norm, vec_b_norm)
        distance = euclidean_distance(vec_a_norm, vec_b_norm)

        print(f"  Cosine similarity: {similarity:.4f}")
        print(f"  Euclidean distance: {distance:.4f}")

        # Performance test
        num_ops = 1000
        start = time.time()

        for _ in range(num_ops):
            cosine_similarity(vec_a_norm, vec_b_norm)

        elapsed = time.time() - start
        ops_per_sec = num_ops / elapsed
        avg_latency = (elapsed / num_ops) * 1000000  # microseconds

        print(f"  Performance: {ops_per_sec:,.0f} ops/sec")
        print(f"  Latency: {avg_latency:.2f} μs")

    # Vector search demo
    print("\n🔍 Vector Search Demo:")
    print("-" * 30)

    # Create a database of vectors
    db_size = 1000
    vector_dim = 128
    vector_db = []

    for i in range(db_size):
        vector = [random.random() for _ in range(vector_dim)]
        vector_db.append((f"vec_{i}", normalize(vector)))

    # Query vector
    query = normalize([random.random() for _ in range(vector_dim)])

    # Find similar vectors
    start = time.time()
    results = []

    for vid, vec in vector_db:
        similarity = cosine_similarity(query, vec)
        if similarity > 0.5:  # Threshold
            results.append((vid, similarity, vec))

    # Sort by similarity
    results.sort(key=lambda x: x[1], reverse=True)
    results = results[:10]  # Top 10

    search_time = time.time() - start

    print(f"Database size: {db_size} vectors")
    print(f"Query dimension: {vector_dim}")
    print(f"Search time: {search_time:.4f} seconds")
    print(f"Results found: {len(results)}")

    print("\nTop 5 results:")
    for i, (vid, similarity, _) in enumerate(results[:5]):
        print(f"  {i+1}. {vid}: {similarity:.4f}")

    # Vector arithmetic demo
    print("\n➕ Vector Arithmetic Demo:")
    print("-" * 30)

    v1 = [1.0, 2.0, 3.0, 4.0, 5.0]
    v2 = [5.0, 4.0, 3.0, 2.0, 1.0]

    v3 = add_vectors(v1, v2)
    print(f"v1: {v1}")
    print(f"v2: {v2}")
    print(f"v1 + v2: {v3}")

    print("\n✨ Demo complete!")

if __name__ == "__main__":
    demo()