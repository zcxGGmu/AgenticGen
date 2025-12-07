use parking_lot::RwLock;
use dashmap::DashMap;
use std::sync::Arc;
use std::collections::HashMap;
use std::time::{Duration, Instant};
use std::ffi::{CStr, CString};
use std::os::raw::{c_char, c_double, c_int, c_float};
use std::ptr;
use std::slice;
use anyhow::Result;
use serde::{Serialize, Deserialize};
use uuid::Uuid;

/// Vector storage with SIMD-optimized operations
pub struct VectorEngine {
    /// In-memory vector storage
    vectors: DashMap<String, VectorData>,
    /// Vector dimensions configuration
    config: EngineConfig,
    /// Performance statistics
    stats: Arc<RwLock<VectorStats>>,
}

/// Configuration for the vector engine
#[derive(Debug, Clone)]
pub struct EngineConfig {
    /// Default dimension for vectors
    pub default_dimension: usize,
    /// Maximum cache size
    pub max_cache_size: usize,
    /// Use SIMD operations
    pub use_simd: bool,
}

/// Vector data with metadata
#[derive(Debug, Clone)]
pub struct VectorData {
    /// The actual vector values
    pub vector: Vec<f32>,
    /// Vector dimension
    pub dimension: usize,
    /// Creation timestamp
    pub created_at: Instant,
    /// Last access timestamp
    pub last_accessed: Instant,
    /// Access count
    pub access_count: u64,
}

/// Performance statistics
#[derive(Debug, Default)]
pub struct VectorStats {
    /// Total operations
    pub total_ops: u64,
    /// Cache hits
    pub cache_hits: u64,
    /// Cache misses
    pub cache_misses: u64,
    /// Average operation latency (nanoseconds)
    pub avg_latency_ns: u64,
    /// Operations per second
    pub ops_per_sec: u64,
}

/// Similarity search result
#[derive(Debug, Clone)]
pub struct SearchResult {
    /// Vector ID
    pub id: String,
    /// Similarity score
    pub score: f32,
    /// Vector data
    pub vector: Vec<f32>,
}

/// Error types
#[derive(Debug, thiserror::Error)]
pub enum VectorError {
    #[error("Dimension mismatch: expected {expected}, got {actual}")]
    DimensionMismatch { expected: usize, actual: usize },
    #[error("Vector not found: {id}")]
    VectorNotFound { id: String },
    #[error("Invalid vector size: {size}")]
    InvalidVectorSize { size: usize },
    #[error("Computation error: {message}")]
    ComputationError { message: String },
}

impl Default for EngineConfig {
    fn default() -> Self {
        Self {
            default_dimension: 768, // Common embedding size
            max_cache_size: 100_000,
            use_simd: true,
        }
    }
}

impl VectorEngine {
    /// Create a new vector engine
    pub fn new(config: EngineConfig) -> Self {
        Self {
            vectors: DashMap::new(),
            config,
            stats: Arc::new(RwLock::new(VectorStats::default())),
        }
    }

    /// Insert a vector into the engine
    pub fn insert(&self, id: String, vector: Vec<f32>) -> Result<()> {
        let start = Instant::now();

        // Validate vector
        if vector.is_empty() {
            return Err(VectorError::InvalidVectorSize { size: 0 }.into());
        }

        let vector_data = VectorData {
            dimension: vector.len(),
            created_at: Instant::now(),
            last_accessed: Instant::now(),
            access_count: 0,
            vector,
        };

        self.vectors.insert(id.clone(), vector_data);

        // Update stats
        let mut stats = self.stats.write();
        stats.total_ops += 1;
        stats.update_latency(start.elapsed());

        Ok(())
    }

    /// Get a vector by ID
    pub fn get(&self, id: &str) -> Option<Vec<f32>> {
        let start = Instant::now();

        let result = self.vectors.get(id).map(|entry| {
            let mut data = entry.value().clone();
            data.access_count += 1;
            data.last_accessed = Instant::now();
            data.vector.clone()
        });

        // Update stats
        let mut stats = self.stats.write();
        stats.total_ops += 1;
        if result.is_some() {
            stats.cache_hits += 1;
        } else {
            stats.cache_misses += 1;
        }
        stats.update_latency(start.elapsed());

        result
    }

    /// Calculate cosine similarity between two vectors
    pub fn cosine_similarity(&self, vec_a: &[f32], vec_b: &[f32]) -> Result<f32> {
        if vec_a.len() != vec_b.len() {
            return Err(VectorError::DimensionMismatch {
                expected: vec_a.len(),
                actual: vec_b.len()
            }.into());
        }

        if self.config.use_simd && vec_a.len() % 8 == 0 {
            Ok(self.cosine_similarity_simd(vec_a, vec_b))
        } else {
            Ok(self.cosine_similarity_scalar(vec_a, vec_b))
        }
    }

    /// SIMD-optimized cosine similarity
    #[cfg(target_arch = "x86_64")]
    fn cosine_similarity_simd(&self, vec_a: &[f32], vec_b: &[f32]) -> f32 {
        use wide::*;

        let mut sum_ab = f32x8::ZERO;
        let mut sum_a2 = f32x8::ZERO;
        let mut sum_b2 = f32x8::ZERO;

        let chunks_a = vec_a.chunks_exact(8);
        let chunks_b = vec_b.chunks_exact(8);
        let remainder_a = chunks_a.remainder();
        let remainder_b = chunks_b.remainder();

        for (chunk_a, chunk_b) in chunks_a.zip(chunks_b) {
            let va = f32x8::from(chunk_a);
            let vb = f32x8::from(chunk_b);

            sum_ab += va * vb;
            sum_a2 += va * va;
            sum_b2 += vb * vb;
        }

        let mut dot_product = sum_ab.reduce_add();
        let mut norm_a = sum_a2.reduce_add();
        let mut norm_b = sum_b2.reduce_add();

        // Handle remainder
        for (&a, &b) in remainder_a.iter().zip(remainder_b.iter()) {
            dot_product += a * b;
            norm_a += a * a;
            norm_b += b * b;
        }

        let denominator = (norm_a * norm_b).sqrt();
        if denominator == 0.0 {
            0.0
        } else {
            dot_product / denominator
        }
    }

    /// Scalar cosine similarity (fallback)
    fn cosine_similarity_scalar(&self, vec_a: &[f32], vec_b: &[f32]) -> f32 {
        let mut dot_product = 0.0f32;
        let mut norm_a = 0.0f32;
        let mut norm_b = 0.0f32;

        for (&a, &b) in vec_a.iter().zip(vec_b.iter()) {
            dot_product += a * b;
            norm_a += a * a;
            norm_b += b * b;
        }

        let denominator = (norm_a * norm_b).sqrt();
        if denominator == 0.0 {
            0.0
        } else {
            dot_product / denominator
        }
    }

    /// Find similar vectors
    pub fn find_similar(&self, query: &[f32], limit: usize) -> Result<Vec<SearchResult>> {
        let start = Instant::now();

        let mut results = Vec::new();

        for entry in self.vectors.iter() {
            let vector_data = entry.value();

            if vector_data.dimension != query.len() {
                continue;
            }

            let similarity = self.cosine_similarity(query, &vector_data.vector)?;

            if similarity > 0.0 { // Only include positive similarities
                results.push(SearchResult {
                    id: entry.key().clone(),
                    score: similarity,
                    vector: vector_data.vector.clone(),
                });
            }
        }

        // Sort by similarity score (descending)
        results.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap());

        // Limit results
        results.truncate(limit);

        // Update stats
        let mut stats = self.stats.write();
        stats.total_ops += 1;
        stats.update_latency(start.elapsed());

        Ok(results)
    }

    /// Euclidean distance between vectors
    pub fn euclidean_distance(&self, vec_a: &[f32], vec_b: &[f32]) -> Result<f32> {
        if vec_a.len() != vec_b.len() {
            return Err(VectorError::DimensionMismatch {
                expected: vec_a.len(),
                actual: vec_b.len()
            }.into());
        }

        let mut sum_sq_diff = 0.0f32;

        for (&a, &b) in vec_a.iter().zip(vec_b.iter()) {
            let diff = a - b;
            sum_sq_diff += diff * diff;
        }

        Ok(sum_sq_diff.sqrt())
    }

    /// Manhattan distance between vectors
    pub fn manhattan_distance(&self, vec_a: &[f32], vec_b: &[f32]) -> Result<f32> {
        if vec_a.len() != vec_b.len() {
            return Err(VectorError::DimensionMismatch {
                expected: vec_a.len(),
                actual: vec_b.len()
            }.into());
        }

        let mut sum_abs_diff = 0.0f32;

        for (&a, &b) in vec_a.iter().zip(vec_b.iter()) {
            sum_abs_diff += (a - b).abs();
        }

        Ok(sum_abs_diff)
    }

    /// Dot product of two vectors
    pub fn dot_product(&self, vec_a: &[f32], vec_b: &[f32]) -> Result<f32> {
        if vec_a.len() != vec_b.len() {
            return Err(VectorError::DimensionMismatch {
                expected: vec_a.len(),
                actual: vec_b.len()
            }.into());
        }

        let mut result = 0.0f32;

        for (&a, &b) in vec_a.iter().zip(vec_b.iter()) {
            result += a * b;
        }

        Ok(result)
    }

    /// Vector addition
    pub fn add(&self, vec_a: &[f32], vec_b: &[f32]) -> Result<Vec<f32>> {
        if vec_a.len() != vec_b.len() {
            return Err(VectorError::DimensionMismatch {
                expected: vec_a.len(),
                actual: vec_b.len()
            }.into());
        }

        Ok(vec_a.iter().zip(vec_b.iter())
            .map(|(&a, &b)| a + b)
            .collect())
    }

    /// Vector subtraction
    pub fn subtract(&self, vec_a: &[f32], vec_b: &[f32]) -> Result<Vec<f32>> {
        if vec_a.len() != vec_b.len() {
            return Err(VectorError::DimensionMismatch {
                expected: vec_a.len(),
                actual: vec_b.len()
            }.into());
        }

        Ok(vec_a.iter().zip(vec_b.iter())
            .map(|(&a, &b)| a - b)
            .collect())
    }

    /// Scalar multiplication
    pub fn multiply_scalar(&self, vec: &[f32], scalar: f32) -> Vec<f32> {
        vec.iter().map(|&v| v * scalar).collect()
    }

    /// Normalize a vector to unit length
    pub fn normalize(&self, vec: &[f32]) -> Result<Vec<f32>> {
        if vec.is_empty() {
            return Ok(Vec::new());
        }

        let norm = (vec.iter().map(|&v| v * v).sum::<f32>()).sqrt();

        if norm == 0.0 {
            return Err(VectorError::ComputationError {
                message: "Cannot normalize zero vector".to_string()
            }.into());
        }

        Ok(vec.iter().map(|&v| v / norm).collect())
    }

    /// Batch vector operations
    pub fn batch_cosine_similarity(&self, query: &[f32], vectors: &[Vec<f32>]) -> Result<Vec<f32>> {
        let mut results = Vec::with_capacity(vectors.len());

        for vec in vectors {
            if vec.len() != query.len() {
                results.push(0.0f32);
                continue;
            }

            let similarity = if self.config.use_simd && vec.len() % 8 == 0 {
                self.cosine_similarity_simd(query, vec)
            } else {
                self.cosine_similarity_scalar(query, vec)
            };

            results.push(similarity);
        }

        Ok(results)
    }

    /// Get engine statistics
    pub fn get_stats(&self) -> VectorStats {
        self.stats.read().clone()
    }

    /// Get the number of stored vectors
    pub fn len(&self) -> usize {
        self.vectors.len()
    }

    /// Check if the engine is empty
    pub fn is_empty(&self) -> bool {
        self.vectors.is_empty()
    }

    /// Clear all vectors
    pub fn clear(&self) {
        self.vectors.clear();

        // Reset stats
        let mut stats = self.stats.write();
        *stats = VectorStats::default();
    }

    /// Remove a vector by ID
    pub fn remove(&self, id: &str) -> bool {
        self.vectors.remove(id).is_some()
    }

    /// List all vector IDs
    pub fn list_ids(&self) -> Vec<String> {
        self.vectors.iter().map(|entry| entry.key().clone()).collect()
    }
}

impl VectorStats {
    /// Update average latency
    fn update_latency(&mut self, latency: Duration) {
        let latency_ns = latency.as_nanos() as u64;
        self.avg_latency_ns = (self.avg_latency_ns + latency_ns) / 2;

        // Update ops per second (simplified)
        if self.total_ops > 0 {
            self.ops_per_sec = 1_000_000_000 / latency_ns;
        }
    }
}

impl Clone for VectorStats {
    fn clone(&self) -> Self {
        Self {
            total_ops: self.total_ops,
            cache_hits: self.cache_hits,
            cache_misses: self.cache_misses,
            avg_latency_ns: self.avg_latency_ns,
            ops_per_sec: self.ops_per_sec,
        }
    }
}

// C FFI Interface for Python integration

/// Opaque pointer to VectorEngine
pub struct VectorEnginePtr {
    inner: *mut VectorEngine,
}

/// Create a new vector engine
#[no_mangle]
pub extern "C" fn vector_engine_create(
    default_dimension: usize,
    max_cache_size: usize,
    use_simd: bool,
) -> *mut VectorEnginePtr {
    let config = EngineConfig {
        default_dimension,
        max_cache_size,
        use_simd,
    };

    let engine = Box::new(VectorEngine::new(config));
    let ptr = Box::into_raw(engine);

    let wrapper = Box::new(VectorEnginePtr { inner: ptr });
    Box::into_raw(wrapper)
}

/// Destroy a vector engine
#[no_mangle]
pub unsafe extern "C" fn vector_engine_destroy(ptr: *mut VectorEnginePtr) {
    if !ptr.is_null() {
        let wrapper = Box::from_raw(ptr);
        if !wrapper.inner.is_null() {
            let _ = Box::from_raw(wrapper.inner);
        }
    }
}

/// Insert a vector
#[no_mangle]
pub unsafe extern "C" fn vector_engine_insert(
    ptr: *mut VectorEnginePtr,
    id: *const c_char,
    vector: *const c_float,
    len: usize,
) -> c_int {
    if ptr.is_null() || id.is_null() || vector.is_null() {
        return -1;
    }

    let wrapper = &*ptr;
    let engine = &*wrapper.inner;

    let id_str = match CStr::from_ptr(id).to_str() {
        Ok(s) => s.to_string(),
        Err(_) => return -1,
    };

    let vec_data = slice::from_raw_parts(vector, len).to_vec();

    match engine.insert(id_str, vec_data) {
        Ok(()) => 0,
        Err(_) => -1,
    }
}

/// Get cosine similarity between two vectors
#[no_mangle]
pub unsafe extern "C" fn vector_engine_cosine_similarity(
    ptr: *mut VectorEnginePtr,
    vec_a: *const c_float,
    len_a: usize,
    vec_b: *const c_float,
    len_b: usize,
) -> c_double {
    if ptr.is_null() || vec_a.is_null() || vec_b.is_null() {
        return -1.0;
    }

    let wrapper = &*ptr;
    let engine = &*wrapper.inner;

    let a = slice::from_raw_parts(vec_a, len_a);
    let b = slice::from_raw_parts(vec_b, len_b);

    match engine.cosine_similarity(a, b) {
        Ok(similarity) => similarity as c_double,
        Err(_) => -1.0,
    }
}

/// Find similar vectors
#[no_mangle]
pub unsafe extern "C" fn vector_engine_find_similar(
    ptr: *mut VectorEnginePtr,
    query: *const c_float,
    query_len: usize,
    limit: usize,
    out_ids: *mut *mut *mut c_char,
    out_scores: *mut *mut c_double,
    out_count: *mut usize,
) -> c_int {
    if ptr.is_null() || query.is_null() || out_ids.is_null() || out_scores.is_null() || out_count.is_null() {
        return -1;
    }

    let wrapper = &*ptr;
    let engine = &*wrapper.inner;

    let query_vec = slice::from_raw_parts(query, query_len);

    match engine.find_similar(query_vec, limit) {
        Ok(results) => {
            let ids: Vec<*mut c_char> = results
                .iter()
                .map(|r| CString::new(r.id.as_str()).unwrap().into_raw())
                .collect();

            let scores: Vec<c_double> = results
                .iter()
                .map(|r| r.score as c_double)
                .collect();

            let ids_ptr = Box::into_raw(ids.into_boxed_slice()) as *mut *mut c_char;
            let scores_ptr = Box::into_raw(scores.into_boxed_slice()) as *mut c_double;

            *out_ids = ids_ptr;
            *out_scores = scores_ptr;
            *out_count = results.len();

            0
        }
        Err(_) => -1,
    }
}

/// Free memory allocated for search results
#[no_mangle]
pub unsafe extern "C" fn vector_engine_free_results(
    ids: *mut *mut c_char,
    scores: *mut c_double,
    count: usize,
) {
    if !ids.is_null() {
        let ids_slice = slice::from_raw_parts_mut(ids, count);
        for &mut id_ptr in ids_slice {
            if !id_ptr.is_null() {
                let _ = CString::from_raw(id_ptr);
            }
        }
        let _ = Box::from_raw(slice::from_raw_parts_mut(ids, count));
    }

    if !scores.is_null() {
        let _ = Box::from_raw(slice::from_raw_parts_mut(scores, count));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_vector_operations() {
        let config = EngineConfig::default();
        let engine = VectorEngine::new(config);

        let vec_a = vec![1.0, 2.0, 3.0];
        let vec_b = vec![4.0, 5.0, 6.0];

        // Test cosine similarity
        let similarity = engine.cosine_similarity(&vec_a, &vec_b).unwrap();
        assert!(similarity > 0.0);

        // Test euclidean distance
        let distance = engine.euclidean_distance(&vec_a, &vec_b).unwrap();
        assert!(distance > 0.0);

        // Test dot product
        let dot = engine.dot_product(&vec_a, &vec_b).unwrap();
        assert_eq!(dot, 32.0);

        // Test vector addition
        let sum = engine.add(&vec_a, &vec_b).unwrap();
        assert_eq!(sum, vec![5.0, 7.0, 9.0]);
    }

    #[test]
    fn test_insert_and_get() {
        let config = EngineConfig::default();
        let engine = VectorEngine::new(config);

        let vector = vec![1.0, 2.0, 3.0];
        engine.insert("test".to_string(), vector.clone()).unwrap();

        let retrieved = engine.get("test").unwrap();
        assert_eq!(retrieved, vector);
    }

    #[test]
    fn test_find_similar() {
        let config = EngineConfig::default();
        let engine = VectorEngine::new(config);

        engine.insert("vec1".to_string(), vec![1.0, 0.0, 0.0]).unwrap();
        engine.insert("vec2".to_string(), vec![0.9, 0.1, 0.0]).unwrap();
        engine.insert("vec3".to_string(), vec![0.0, 1.0, 0.0]).unwrap();

        let query = vec![1.0, 0.0, 0.0];
        let results = engine.find_similar(&query, 2).unwrap();

        assert_eq!(results.len(), 2);
        assert_eq!(results[0].id, "vec1");
        assert!(results[0].score > results[1].score);
    }
}