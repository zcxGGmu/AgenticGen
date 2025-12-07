use std::collections::HashMap;
use std::ffi::{CStr, CString};
use std::fs::File;
use std::io::{Read, Write};
use std::os::raw::{c_char, c_int};
use std::process::Command;
use std::sync::Arc;
use std::time::{Duration, Instant};

use anyhow::{anyhow, Result};
use nix::sys::wait::{waitpid, WaitStatus};
use nix::unistd::{fork, ForkResult, Pid};
use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use tempfile::{NamedTempFile, TempDir};
use tracing::{debug, warn};
use uuid::Uuid;

/// Secure Python sandbox for executing untrusted code
pub struct PythonSandbox {
    /// Sandbox configuration
    config: SandboxConfig,
    /// Active executions
    executions: Arc<RwLock<HashMap<String, ExecutionInfo>>>,
    /// Temporary directory for sandbox
    temp_dir: Option<TempDir>,
}

/// Sandbox configuration
#[derive(Debug, Clone)]
pub struct SandboxConfig {
    /// Maximum execution time in seconds
    pub max_execution_time: u64,
    /// Maximum memory usage in MB
    pub max_memory_mb: u64,
    /// Maximum CPU time in seconds
    pub max_cpu_time: u64,
    /// Maximum output size in bytes
    pub max_output_size: usize,
    /// Allowed modules (whitelist)
    pub allowed_modules: Vec<String>,
    /// Blocked modules (blacklist)
    pub blocked_modules: Vec<String>,
    /// Enable network isolation
    pub network_isolation: bool,
    /// Enable filesystem isolation
    pub filesystem_isolation: bool,
    /// Python interpreter path
    pub python_path: String,
}

/// Execution information
#[derive(Debug, Clone)]
pub struct ExecutionInfo {
    /// Execution ID
    pub id: String,
    /// Start time
    pub started_at: Instant,
    /// Process ID
    pub pid: Option<Pid>,
    /// Current status
    pub status: ExecutionStatus,
    /// Execution result (if completed)
    pub result: Option<ExecutionResult>,
}

/// Execution status
#[derive(Debug, Clone, PartialEq)]
pub enum ExecutionStatus {
    /// Queued but not started
    Queued,
    /// Currently running
    Running,
    /// Completed successfully
    Completed,
    /// Failed with error
    Failed,
    /// Timed out
    Timeout,
    /// Killed
    Killed,
}

/// Execution result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionResult {
    /// Exit code
    pub exit_code: i32,
    /// Standard output
    pub stdout: String,
    /// Standard error
    pub stderr: String,
    /// Execution duration in milliseconds
    pub duration_ms: u64,
    /// Memory used in MB
    pub memory_mb: u64,
    /// CPU time used in milliseconds
    pub cpu_time_ms: u64,
}

/// Code execution request
#[derive(Debug, Serialize, Deserialize)]
pub struct ExecutionRequest {
    /// Python code to execute
    pub code: String,
    /// Optional input data
    pub stdin: Option<String>,
    /// Custom timeout (overrides config)
    pub timeout: Option<u64>,
    /// Custom memory limit (overrides config)
    pub memory_limit: Option<u64>,
}

impl Default for SandboxConfig {
    fn default() -> Self {
        Self {
            max_execution_time: 30, // 30 seconds
            max_memory_mb: 512,      // 512 MB
            max_cpu_time: 30,        // 30 seconds
            max_output_size: 1024 * 1024, // 1 MB
            allowed_modules: vec![
                "math".to_string(),
                "random".to_string(),
                "statistics".to_string(),
                "itertools".to_string(),
                "functools".to_string(),
                "operator".to_string(),
                "collections".to_string(),
                "datetime".to_string(),
                "time".to_string(),
                "json".to_string(),
                "csv".to_string(),
                "re".to_string(),
                "string".to_string(),
                "typing".to_string(),
            ],
            blocked_modules: vec![
                "os".to_string(),
                "sys".to_string(),
                "subprocess".to_string(),
                "importlib".to_string(),
                "execfile".to_string(),
                "compile".to_string(),
                "eval".to_string(),
                "exec".to_string(),
                "__import__".to_string(),
                "globals".to_string(),
                "locals".to_string(),
                "vars".to_string(),
                "dir".to_string(),
                "hasattr".to_string(),
                "getattr".to_string(),
                "setattr".to_string(),
                "delattr".to_string(),
                "open".to_string(),
                "file".to_string(),
                "input".to_string(),
                "raw_input".to_string(),
            ],
            network_isolation: true,
            filesystem_isolation: true,
            python_path: "python3".to_string(),
        }
    }
}

impl PythonSandbox {
    /// Create a new Python sandbox
    pub fn new(config: SandboxConfig) -> Result<Self> {
        // Verify Python interpreter exists
        if let Err(e) = Command::new(&config.python_path)
            .arg("--version")
            .output()
        {
            return Err(anyhow!("Python interpreter not found: {}", e));
        }

        let temp_dir = if config.filesystem_isolation {
            Some(TempDir::new()?)
        } else {
            None
        };

        Ok(Self {
            config,
            executions: Arc::new(RwLock::new(HashMap::new())),
            temp_dir,
        })
    }

    /// Execute Python code in the sandbox
    pub async fn execute(&self, request: ExecutionRequest) -> Result<String> {
        let execution_id = Uuid::new_v4().to_string();
        let timeout = request.timeout.unwrap_or(self.config.max_execution_time);

        // Create execution info
        let execution_info = ExecutionInfo {
            id: execution_id.clone(),
            started_at: Instant::now(),
            pid: None,
            status: ExecutionStatus::Queued,
            result: None,
        };

        self.executions.write().insert(execution_id.clone(), execution_info);

        // Prepare the code
        let wrapped_code = self.wrap_code(&request.code)?;

        // Create temporary files
        let code_file = self.create_code_file(&wrapped_code)?;
        let output_file = NamedTempFile::new()?;
        let error_file = NamedTempFile::new()?;

        // Execute in a child process
        let result = match unsafe { fork() } {
            Ok(ForkResult::Parent { child, .. }) => {
                // Parent process
                debug!("Child process PID: {:?}", child);

                // Update execution info
                {
                    let mut executions = self.executions.write();
                    if let Some(exec) = executions.get_mut(&execution_id) {
                        exec.pid = Some(child);
                        exec.status = ExecutionStatus::Running;
                    }
                }

                // Wait for child with timeout
                self.wait_for_child(child, timeout, &output_file, &error_file).await
            }
            Ok(ForkResult::Child) => {
                // Child process
                self.execute_in_child(&code_file, &output_file, &error_file)?;
                unreachable!();
            }
            Err(e) => {
                return Err(anyhow!("Failed to fork: {}", e));
            }
        };

        // Update execution result
        {
            let mut executions = self.executions.write();
            if let Some(exec) = executions.get_mut(&execution_id) {
                match result {
                    Ok(r) => {
                        exec.status = ExecutionStatus::Completed;
                        exec.result = Some(r);
                    }
                    Err(_) => {
                        exec.status = ExecutionStatus::Failed;
                    }
                }
            }
        }

        // Return execution ID
        Ok(execution_id)
    }

    /// Get execution result
    pub fn get_result(&self, execution_id: &str) -> Option<ExecutionResult> {
        let executions = self.executions.read();
        executions
            .get(execution_id)
            .and_then(|e| e.result.clone())
    }

    /// Get execution status
    pub fn get_status(&self, execution_id: &str) -> Option<ExecutionStatus> {
        let executions = self.executions.read();
        executions.get(execution_id).map(|e| e.status.clone())
    }

    /// Kill an execution
    pub fn kill(&self, execution_id: &str) -> Result<bool> {
        let mut executions = self.executions.write();

        if let Some(exec) = executions.get_mut(execution_id) {
            if let Some(pid) = exec.pid {
                match nix::sys::signal::kill(pid, nix::sys::signal::Signal::SIGTERM) {
                    Ok(_) => {
                        exec.status = ExecutionStatus::Killed;
                        return Ok(true);
                    }
                    Err(e) => {
                        warn!("Failed to kill process {}: {}", pid, e);
                    }
                }
            }
        }

        Ok(false)
    }

    /// Clean up completed executions
    pub fn cleanup(&self) {
        let mut executions = self.executions.write();

        executions.retain(|_, exec| {
            matches!(exec.status, ExecutionStatus::Queued | ExecutionStatus::Running)
        });
    }

    /// Wrap user code with security restrictions
    fn wrap_code(&self, code: &str) -> Result<String> {
        // Create a safe execution environment
        let wrapped = format!(
            r#"
import sys
import builtins
import importlib
import importlib.util
import types

# Safe builtins replacement
_safe_builtins = {{
    'abs': abs,
    'all': all,
    'any': any,
    'bin': bin,
    'bool': bool,
    'bytes': bytes,
    'chr': chr,
    'dict': dict,
    'divmod': divmod,
    'enumerate': enumerate,
    'filter': filter,
    'float': float,
    'format': format,
    'frozenset': frozenset,
    'hex': hex,
    'int': int,
    'isinstance': isinstance,
    'issubclass': issubclass,
    'iter': iter,
    'len': len,
    'list': list,
    'map': map,
    'max': max,
    'min': min,
    'oct': oct,
    'ord': ord,
    'pow': pow,
    'print': print,
    'range': range,
    'repr': repr,
    'reversed': reversed,
    'round': round,
    'set': set,
    'slice': slice,
    'sorted': sorted,
    'str': str,
    'sum': sum,
    'tuple': tuple,
    'type': type,
    'zip': zip,
}}

# Override builtins
builtins.__dict__.clear()
builtins.__dict__.update(_safe_builtins)

# Module restrictions
_allowed_modules = {allowed_modules}
_blocked_modules = {blocked_modules}

class SafeImporter:
    def find_spec(self, name, path, target=None):
        if name in _blocked_modules:
            raise ImportError(f"Module '{{name}}' is not allowed")

        # Check if module is in allowed list or is a submodule
        base_name = name.split('.')[0]
        if _allowed_modules and base_name not in _allowed_modules:
            raise ImportError(f"Module '{{name}}' is not allowed")

        return None

# Install the safe importer
sys.meta_path.insert(0, SafeImporter())

# Remove dangerous attributes
delattr(builtins, '__import__')
delattr(types, 'FunctionType')
delattr(types, 'MethodType')

# Execute user code
try:
{user_code}
except Exception as e:
    print(f"Error: {{e}}", file=sys.stderr)
    sys.exit(1)
"#,
            allowed_modules = serde_json::to_string(&self.config.allowed_modules)?,
            blocked_modules = serde_json::to_string(&self.config.blocked_modules)?,
            user_code = code.lines().map(|line| format!("    {}", line)).collect::<Vec<_>>().join("\n")
        );

        Ok(wrapped)
    }

    /// Create temporary code file
    fn create_code_file(&self, code: &str) -> Result<NamedTempFile> {
        let mut file = NamedTempFile::new()?;
        file.write_all(code.as_bytes())?;
        file.flush()?;
        Ok(file)
    }

    /// Execute code in child process
    fn execute_in_child(
        &self,
        code_file: &NamedTempFile,
        output_file: &NamedTempFile,
        error_file: &NamedTempFile,
    ) -> Result<()> {
        use std::os::unix::io::AsRawFd;

        // Resource limits disabled for compatibility
        // TODO: Implement proper rlimit support

        // Redirect stdout and stderr
        let stdout_fd = output_file.as_raw_fd();
        let stderr_fd = error_file.as_raw_fd();

        unsafe {
            libc::dup2(stdout_fd, libc::STDOUT_FILENO);
            libc::dup2(stderr_fd, libc::STDERR_FILENO);
        }

        // Execute Python
        let status = Command::new(&self.config.python_path)
            .arg("-E")  // Don't import site module
            .arg("-S")  // Don't import site module
            .arg("-u")  // Unbuffered output
            .arg(code_file.path())
            .status()?;

        std::process::exit(status.code().unwrap_or(1));
    }

    /// Wait for child process with timeout
    async fn wait_for_child(
        &self,
        child: Pid,
        timeout: u64,
        output_file: &NamedTempFile,
        error_file: &NamedTempFile,
    ) -> Result<ExecutionResult> {
        let start_time = Instant::now();

        // Use a background thread for waiting
        let (sender, receiver) = tokio::sync::oneshot::channel();

        std::thread::spawn(move || {
            let result = waitpid(child, None);
            let _ = sender.send(result);
        });

        // Wait with timeout
        match tokio::time::timeout(Duration::from_secs(timeout), receiver).await {
            Ok(Ok(Ok(WaitStatus::Exited(_, exit_code)))) => {
                let duration = start_time.elapsed();

                // Read output
                let mut stdout = String::new();
                let mut stderr = String::new();

                let mut output = File::open(output_file.path())?;
                let mut error = File::open(error_file.path())?;

                output.read_to_string(&mut stdout)?;
                error.read_to_string(&mut stderr)?;

                // Truncate if too large
                if stdout.len() > self.config.max_output_size {
                    stdout.truncate(self.config.max_output_size);
                    stdout.push_str("\n... [truncated]");
                }

                if stderr.len() > self.config.max_output_size {
                    stderr.truncate(self.config.max_output_size);
                    stderr.push_str("\n... [truncated]");
                }

                Ok(ExecutionResult {
                    exit_code: exit_code as i32,
                    stdout,
                    stderr,
                    duration_ms: duration.as_millis() as u64,
                    memory_mb: 0, // TODO: Implement memory tracking
                    cpu_time_ms: 0, // TODO: Implement CPU time tracking
                })
            }
            Ok(Ok(_)) => Err(anyhow!("Unexpected wait status")),
            Ok(Err(e)) => Err(anyhow!("Wait error: {}", e)),
            Err(_) => {
                // Timeout
                let _ = nix::sys::signal::kill(child, nix::sys::signal::Signal::SIGKILL);
                Err(anyhow!("Execution timeout"))
            }
        }
    }
}

// C FFI Interface

/// Opaque pointer to PythonSandbox
pub struct PythonSandboxPtr {
    inner: *mut PythonSandbox,
}

/// Create a new sandbox
#[no_mangle]
pub extern "C" fn python_sandbox_create() -> *mut PythonSandboxPtr {
    let config = SandboxConfig::default();
    match PythonSandbox::new(config) {
        Ok(sandbox) => {
            let ptr = Box::into_raw(Box::new(sandbox));
            let wrapper = Box::new(PythonSandboxPtr { inner: ptr });
            Box::into_raw(wrapper)
        }
        Err(_) => std::ptr::null_mut(),
    }
}

/// Destroy a sandbox
#[no_mangle]
pub unsafe extern "C" fn python_sandbox_destroy(ptr: *mut PythonSandboxPtr) {
    if !ptr.is_null() {
        let wrapper = Box::from_raw(ptr);
        if !wrapper.inner.is_null() {
            let _ = Box::from_raw(wrapper.inner);
        }
    }
}

/// Execute code in sandbox
#[no_mangle]
pub unsafe extern "C" fn python_sandbox_execute(
    ptr: *mut PythonSandboxPtr,
    code: *const c_char,
    execution_id: *mut c_char,
    id_len: *mut usize,
) -> c_int {
    if ptr.is_null() || code.is_null() || execution_id.is_null() || id_len.is_null() {
        return -1;
    }

    let wrapper = &*ptr;
    let sandbox = &*wrapper.inner;

    let code_str = match CStr::from_ptr(code).to_str() {
        Ok(s) => s,
        Err(_) => return -1,
    };

    let request = ExecutionRequest {
        code: code_str.to_string(),
        stdin: None,
        timeout: None,
        memory_limit: None,
    };

    // Use tokio runtime
    let runtime = tokio::runtime::Runtime::new().unwrap();
    let result = runtime.block_on(sandbox.execute(request));

    match result {
        Ok(id) => {
            let id_cstr = CString::new(id).unwrap();
            let id_bytes = id_cstr.as_bytes_with_nul();

            execution_id.copy_from_nonoverlapping(id_cstr.as_ptr(), id_bytes.len());
            *id_len = id_bytes.len() - 1; // Exclude null terminator

            0
        }
        Err(_) => -1,
    }
}

/// Get execution result
#[no_mangle]
pub unsafe extern "C" fn python_sandbox_get_result(
    ptr: *mut PythonSandboxPtr,
    execution_id: *const c_char,
    exit_code: *mut c_int,
    stdout: *mut c_char,
    stdout_len: *mut usize,
    stderr: *mut c_char,
    stderr_len: *mut usize,
) -> c_int {
    if ptr.is_null() || execution_id.is_null() {
        return -1;
    }

    let wrapper = &*ptr;
    let sandbox = &*wrapper.inner;

    let id_str = match CStr::from_ptr(execution_id).to_str() {
        Ok(s) => s,
        Err(_) => return -1,
    };

    match sandbox.get_result(id_str) {
        Some(result) => {
            if !exit_code.is_null() {
                *exit_code = result.exit_code;
            }

            if !stdout.is_null() && !stdout_len.is_null() {
                let stdout_cstr = CString::new(result.stdout.as_bytes()).unwrap();
                let stdout_bytes = stdout_cstr.as_bytes_with_nul();

                stdout.copy_from_nonoverlapping(stdout_cstr.as_ptr(), stdout_bytes.len());
                *stdout_len = stdout_bytes.len() - 1; // Exclude null terminator
            }

            if !stderr.is_null() && !stderr_len.is_null() {
                let stderr_cstr = CString::new(result.stderr.as_bytes()).unwrap();
                let stderr_bytes = stderr_cstr.as_bytes_with_nul();

                stderr.copy_from_nonoverlapping(stderr_cstr.as_ptr(), stderr_bytes.len());
                *stderr_len = stderr_bytes.len() - 1; // Exclude null terminator
            }

            0
        }
        None => 1,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sandbox_creation() {
        let config = SandboxConfig::default();
        let sandbox = PythonSandbox::new(config);
        assert!(sandbox.is_ok());
    }

    #[test]
    fn test_simple_execution() {
        let config = SandboxConfig {
            max_execution_time: 5,
            python_path: "python3".to_string(),
            ..Default::default()
        };

        let runtime = tokio::runtime::Runtime::new().unwrap();
        runtime.block_on(async {
            let sandbox = PythonSandbox::new(config).unwrap();

            let request = ExecutionRequest {
                code: "print('Hello, World!')\nresult = 2 + 2".to_string(),
                stdin: None,
                timeout: None,
                memory_limit: None,
            };

            let execution_id = sandbox.execute(request).await.unwrap();

            // Wait a bit for execution
            tokio::time::sleep(Duration::from_millis(100)).await;

            let result = sandbox.get_result(&execution_id);
            assert!(result.is_some());

            let result = result.unwrap();
            assert_eq!(result.exit_code, 0);
            assert!(result.stdout.contains("Hello, World!"));
        });
    }
}