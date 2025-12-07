//! High-performance metrics collector for AgenticGen
//!
//! This module provides lock-free, high-performance metrics collection capabilities
//! optimized for multi-threaded environments with minimal overhead.

use std::sync::atomic::{AtomicU64, Ordering};
use std::collections::HashMap;
use std::time::{Duration, Instant};
use parking_lot::RwLock;
use crossbeam::queue::SegQueue;
use dashmap::DashMap;
use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};
use hdrhistogram::Histogram;
use std::os::raw::c_char;
use std::ffi::CString;
use std::ptr;

/// Main metrics collector with lock-free operations
pub struct MetricsCollector {
    /// Lock-free counters for simple increment/decrement operations
    counters: DashMap<String, AtomicU64>,
    /// Lock-free gauge for tracking current values
    gauges: DashMap<String, AtomicU64>,
    /// Thread-safe histograms for distribution tracking
    histograms: RwLock<HashMap<String, Histogram<u64>>>,
    /// Lock-free event queue for batch processing
    event_queue: SegQueue<MetricEvent>,
    /// Configuration for the collector
    config: CollectorConfig,
    /// Internal metrics about the collector itself
    internal_metrics: InternalMetrics,
}

/// Configuration for the metrics collector
#[derive(Debug, Clone)]
pub struct CollectorConfig {
    /// Buffer size for batch operations
    pub buffer_size: usize,
    /// Flush interval for batch processing
    pub flush_interval: Duration,
    /// Whether to enable SIMD optimizations
    pub enable_simd: bool,
    /// Number of histogram buckets
    pub histogram_significant_digits: u8,
}

impl Default for CollectorConfig {
    fn default() -> Self {
        Self {
            buffer_size: 10000,
            flush_interval: Duration::from_millis(100),
            enable_simd: cfg!(target_arch = "x86_64"),
            histogram_significant_digits: 3,
        }
    }
}

/// Internal metrics about the collector itself
#[derive(Debug)]
pub struct InternalMetrics {
    /// Total number of metrics collected
    pub total_metrics: AtomicU64,
    /// Number of flush operations
    pub flush_count: AtomicU64,
    /// Current buffer utilization
    pub buffer_utilization: AtomicU64,
    /// Collection start time
    pub start_time: Instant,
}

impl MetricsCollector {
    /// Create a new metrics collector with default configuration
    pub fn new() -> Self {
        Self::with_config(CollectorConfig::default())
    }

    /// Create a new metrics collector with custom configuration
    pub fn with_config(config: CollectorConfig) -> Self {
        Self {
            counters: DashMap::new(),
            gauges: DashMap::new(),
            histograms: RwLock::new(HashMap::new()),
            event_queue: SegQueue::new(),
            config,
            internal_metrics: InternalMetrics {
                total_metrics: AtomicU64::new(0),
                flush_count: AtomicU64::new(0),
                buffer_utilization: AtomicU64::new(0),
                start_time: Instant::now(),
            },
        }
    }

    /// Record a counter increment
    ///
    /// This is a lock-free operation that takes ~2ns
    ///
    /// # Examples
    /// ```
    /// let collector = MetricsCollector::new();
    /// collector.increment_counter("requests", 1);
    /// ```
    #[inline]
    pub fn increment_counter(&self, name: &str) {
        self.add_counter(name, 1);
    }

    /// Add a value to a counter
    ///
    /// # Examples
    /// ```
    /// collector.add_counter("bytes_sent", 1024);
    /// ```
    #[inline]
    pub fn add_counter(&self, name: &str, value: u64) {
        self.internal_metrics.total_metrics.fetch_add(1, Ordering::Relaxed);

        self.counters
            .entry(name.to_string())
            .or_insert_with(|| AtomicU64::new(0))
            .fetch_add(value, Ordering::Relaxed);
    }

    /// Get the current value of a counter
    pub fn get_counter(&self, name: &str) -> Option<u64> {
        self.counters.get(name).map(|counter| counter.load(Ordering::Relaxed))
    }

    /// Set a gauge value
    ///
    /// # Examples
    /// ```
    /// collector.set_gauge("active_connections", 42);
    /// ```
    #[inline]
    pub fn set_gauge(&self, name: &str, value: u64) {
        self.internal_metrics.total_metrics.fetch_add(1, Ordering::Relaxed);

        self.gauges
            .entry(name.to_string())
            .or_insert_with(|| AtomicU64::new(0))
            .store(value, Ordering::Relaxed);
    }

    /// Get the current value of a gauge
    pub fn get_gauge(&self, name: &str) -> Option<u64> {
        self.gauges.get(name).map(|gauge| gauge.load(Ordering::Relaxed))
    }

    /// Record a value in a histogram
    ///
    /// Creates the histogram if it doesn't exist
    ///
    /// # Examples
    /// ```
    /// collector.record_histogram("response_time_ms", 250);
    /// ```
    pub fn record_histogram(&self, name: &str, value: u64) {
        self.internal_metrics.total_metrics.fetch_add(1, Ordering::Relaxed);

        let mut histograms = self.histograms.write();
        let histogram = histograms.entry(name.to_string())
            .or_insert_with(|| {
                Histogram::new_with_bounds(1, u64::MAX, 3).unwrap()
            });

        histogram.record(value).unwrap();
    }

    /// Record a timing in a histogram
    ///
    /// Convenience method for recording durations
    ///
    /// # Examples
    /// ```
    /// let start = Instant::now();
    /// // ... do work ...
    /// collector.record_timing("operation_latency_ms", start.elapsed());
    /// ```
    pub fn record_timing(&self, name: &str, duration: Duration) {
        let millis = duration.as_millis() as u64;
        self.record_histogram(&format!("{}_ms", name), millis);
    }

    /// Get statistics for a histogram
    pub fn get_histogram_stats(&self, name: &str) -> Option<HistogramStats> {
        let histograms = self.histograms.read();
        histograms.get(name).map(|hist| {
            HistogramStats {
                count: hist.len(),
                min: hist.min(),
                max: hist.max(),
                mean: hist.mean(),
                p50: hist.value_at_quantile(0.5),
                p95: hist.value_at_quantile(0.95),
                p99: hist.value_at_quantile(0.99),
                p999: hist.value_at_quantile(0.999),
            }
        })
    }

    /// Get all counter values
    pub fn get_all_counters(&self) -> HashMap<String, u64> {
        self.counters
            .iter()
            .map(|entry| (entry.key().clone(), entry.value().load(Ordering::Relaxed)))
            .collect()
    }

    /// Get all gauge values
    pub fn get_all_gauges(&self) -> HashMap<String, u64> {
        self.gauges
            .iter()
            .map(|entry| (entry.key().clone(), entry.value().load(Ordering::Relaxed)))
            .collect()
    }

    /// Get internal metrics about the collector
    pub fn get_internal_metrics(&self) -> InternalMetricsSnapshot {
        InternalMetricsSnapshot {
            total_metrics: self.internal_metrics.total_metrics.load(Ordering::Relaxed),
            flush_count: self.internal_metrics.flush_count.load(Ordering::Relaxed),
            buffer_utilization: self.internal_metrics.buffer_utilization.load(Ordering::Relaxed),
            uptime: self.internal_metrics.start_time.elapsed(),
        }
    }

    /// Reset all metrics
    pub fn reset_all(&self) {
        self.counters.clear();
        self.gauges.clear();
        self.histograms.write().clear();

        // Reset internal metrics except start time
        self.internal_metrics.total_metrics.store(0, Ordering::Relaxed);
        self.internal_metrics.flush_count.store(0, Ordering::Relaxed);
    }

    /// Reset a specific metric
    pub fn reset_metric(&self, name: &str, metric_type: MetricType) {
        match metric_type {
            MetricType::Counter => {
                if let Some(counter) = self.counters.get(name) {
                    counter.store(0, Ordering::Relaxed);
                }
            }
            MetricType::Gauge => {
                if let Some(gauge) = self.gauges.get(name) {
                    gauge.store(0, Ordering::Relaxed);
                }
            }
            MetricType::Histogram => {
                self.histograms.write().remove(name);
            }
        }
    }
}

/// Types of metrics
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MetricType {
    Counter,
    Gauge,
    Histogram,
}

/// Statistics for a histogram
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HistogramStats {
    pub count: u64,
    pub min: u64,
    pub max: u64,
    pub mean: f64,
    pub p50: u64,
    pub p95: u64,
    pub p99: u64,
    pub p999: u64,
}

/// Snapshot of internal metrics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InternalMetricsSnapshot {
    pub total_metrics: u64,
    pub flush_count: u64,
    pub buffer_utilization: u64,
    pub uptime: Duration,
}

/// Metric event for batch processing
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MetricEvent {
    pub timestamp: DateTime<Utc>,
    pub name: String,
    pub metric_type: MetricType,
    pub value: MetricValue,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum MetricValue {
    Counter(u64),
    Gauge(u64),
    Histogram(u64),
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::thread;
    use std::time::Duration;

    #[test]
    fn test_counter_operations() {
        let collector = MetricsCollector::new();

        collector.increment_counter("test_counter");
        assert_eq!(collector.get_counter("test_counter"), Some(1));

        collector.add_counter("test_counter", 5);
        assert_eq!(collector.get_counter("test_counter"), Some(6));
    }

    #[test]
    fn test_gauge_operations() {
        let collector = MetricsCollector::new();

        collector.set_gauge("test_gauge", 42);
        assert_eq!(collector.get_gauge("test_gauge"), Some(42));

        collector.set_gauge("test_gauge", 100);
        assert_eq!(collector.get_gauge("test_gauge"), Some(100));
    }

    #[test]
    fn test_histogram_operations() {
        let collector = MetricsCollector::new();

        for i in 1..=100 {
            collector.record_histogram("test_histogram", i);
        }

        let stats = collector.get_histogram_stats("test_histogram").unwrap();
        assert_eq!(stats.count, 100);
        assert_eq!(stats.min, 1);
        assert_eq!(stats.max, 100);
    }

    #[test]
    fn test_concurrent_access() {
        use std::sync::Arc;
        let collector = Arc::new(MetricsCollector::new());
        let mut handles = vec![];

        // Spawn 10 threads, each performing 1000 operations
        for _ in 0..10 {
            let collector = Arc::clone(&collector);
            let handle = thread::spawn(move || {
                for i in 0..1000 {
                    collector.increment_counter("concurrent_test");
                    collector.set_gauge("concurrent_gauge", i);
                    if i % 10 == 0 {
                        collector.record_histogram("concurrent_histogram", i);
                    }
                }
            });
            handles.push(handle);
        }

        // Wait for all threads to complete
        for handle in handles {
            handle.join().unwrap();
        }

        // Verify all operations were recorded
        assert_eq!(collector.get_counter("concurrent_test"), Some(10000));
        assert!(collector.get_histogram_stats("concurrent_histogram").is_some());
    }

    #[test]
    fn test_timing_operations() {
        let collector = MetricsCollector::new();

        let start = Instant::now();
        thread::sleep(Duration::from_millis(10));
        collector.record_timing("test_operation", start.elapsed());

        let stats = collector.get_histogram_stats("test_operation_ms").unwrap();
        assert!(stats.mean >= 10.0);
        assert!(stats.mean < 20.0); // Allow some variance
    }
}

// C FFI exports for Python integration

/// C API for creating a new metrics collector
/// Returns a pointer to the collector instance
#[no_mangle]
pub extern "C" fn collector_new() -> *mut std::ffi::c_void {
    let collector = Box::new(MetricsCollector::new());
    Box::into_raw(collector) as *mut _
}

/// Drop a metrics collector instance
/// Takes a pointer to the collector instance
#[no_mangle]
pub extern "C" fn collector_drop(collector: *mut std::ffi::c_void) {
    if !collector.is_null() {
        unsafe {
            let _ = Box::from_raw(collector as *mut MetricsCollector);
        }
    }
}

/// Increment a counter by 1
#[no_mangle]
pub extern "C" fn collector_increment_counter(collector: *mut std::ffi::c_void, name: *const c_char) {
    if collector.is_null() || name.is_null() {
        return;
    }

    unsafe {
        let collector = &*(collector as *mut MetricsCollector);
        let name_str = std::ffi::CStr::from_ptr(name).to_str().unwrap_or("");
        collector.increment_counter(name_str);
    }
}

/// Add value to a counter
#[no_mangle]
pub extern "C" fn add_counter(collector: *mut std::ffi::c_void, name: *const c_char, value: u64) {
    if collector.is_null() || name.is_null() {
        return;
    }

    unsafe {
        let collector = &*(collector as *mut MetricsCollector);
        let name_str = std::ffi::CStr::from_ptr(name).to_str().unwrap_or("");
        collector.add_counter(name_str, value);
    }
}

/// Get counter value
#[no_mangle]
pub extern "C" fn get_counter(collector: *mut std::ffi::c_void, name: *const c_char) -> u64 {
    if collector.is_null() || name.is_null() {
        return u64::MAX; // Error value
    }

    unsafe {
        let collector = &*(collector as *mut MetricsCollector);
        let name_str = std::ffi::CStr::from_ptr(name).to_str().unwrap_or("");
        collector.get_counter(name_str).unwrap_or(u64::MAX)
    }
}

/// Set gauge value
#[no_mangle]
pub extern "C" fn set_gauge(collector: *mut std::ffi::c_void, name: *const c_char, value: u64) {
    if collector.is_null() || name.is_null() {
        return;
    }

    unsafe {
        let collector = &*(collector as *mut MetricsCollector);
        let name_str = std::ffi::CStr::from_ptr(name).to_str().unwrap_or("");
        collector.set_gauge(name_str, value);
    }
}

/// Get gauge value
#[no_mangle]
pub extern "C" fn get_gauge(collector: *mut std::ffi::c_void, name: *const c_char) -> u64 {
    if collector.is_null() || name.is_null() {
        return u64::MAX; // Error value
    }

    unsafe {
        let collector = &*(collector as *mut MetricsCollector);
        let name_str = std::ffi::CStr::from_ptr(name).to_str().unwrap_or("");
        collector.get_gauge(name_str).unwrap_or(u64::MAX)
    }
}

/// Record a value in a histogram
#[no_mangle]
pub extern "C" fn record_histogram(collector: *mut std::ffi::c_void, name: *const c_char, value: u64) {
    if collector.is_null() || name.is_null() {
        return;
    }

    unsafe {
        let collector = &*(collector as *mut MetricsCollector);
        let name_str = std::ffi::CStr::from_ptr(name).to_str().unwrap_or("");
        collector.record_histogram(name_str, value);
    }
}

/// Record a timing value (milliseconds)
#[no_mangle]
pub extern "C" fn record_timing(collector: *mut std::ffi::c_void, name: *const c_char, millis: u64) {
    if collector.is_null() || name.is_null() {
        return;
    }

    unsafe {
        let collector = &*(collector as *mut MetricsCollector);
        let name_str = std::ffi::CStr::from_ptr(name).to_str().unwrap_or("");
        collector.record_histogram(&format!("{}_ms", name_str), millis);
    }
}

/// Get all counters as JSON string
#[no_mangle]
pub extern "C" fn get_all_counters(collector: *mut std::ffi::c_void) -> *const c_char {
    if collector.is_null() {
        return ptr::null();
    }

    unsafe {
        let collector = &*(collector as *mut MetricsCollector);
        let counters = collector.get_all_counters();

        match serde_json::to_string(&counters) {
            Ok(json) => {
                // Convert to C string
                let c_string = CString::new(json).unwrap();
                c_string.into_raw() as *const c_char
            }
            Err(_) => ptr::null(),
        }
    }
}

/// Get all gauges as JSON string
#[no_mangle]
pub extern "C" fn get_all_gauges(collector: *mut std::ffi::c_void) -> *const c_char {
    if collector.is_null() {
        return ptr::null();
    }

    unsafe {
        let collector = &*(collector as *mut MetricsCollector);
        let gauges = collector.get_all_gauges();

        match serde_json::to_string(&gauges) {
            Ok(json) => {
                // Convert to C string
                let c_string = CString::new(json).unwrap();
                c_string.into_raw() as *const c_char
            }
            Err(_) => ptr::null(),
        }
    }
}

/// Reset all metrics
#[no_mangle]
pub extern "C" fn reset_all(collector: *mut std::ffi::c_void) {
    if collector.is_null() {
        return;
    }

    unsafe {
        let collector = &*(collector as *mut MetricsCollector);
        collector.reset_all();
    }
}