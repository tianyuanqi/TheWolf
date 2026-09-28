#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    fs::File,
    io::{BufRead, BufReader, Read, Write},
    net::{SocketAddr, TcpListener, TcpStream},
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};
use tauri::Manager;

struct LocalService {
    child: Mutex<Option<Child>>,
    token: String,
    port: u16,
    startup_error: Mutex<Option<String>>,
}

const OFFICIAL_SOURCE_URLS: [&str; 2] = [
    "https://disc.static.szse.cn/download/disc/disk03/finalpage/2026-07-14/a4f123a2-bf8a-4583-b077-0a01259eb8db.PDF",
    "https://disc.static.szse.cn/download/disc/disk03/finalpage/2026-08-18/feb8d686-bf51-4395-b9f9-1c94489b5d63.PDF",
];

#[tauri::command]
/// 向桌面页面提供当前进程的本地 API 会话凭据。
fn session_token(state: tauri::State<'_, LocalService>) -> Result<String, String> {
    let mut child = state.child.lock().map_err(|_| "本地服务状态不可用")?;
    if let Some(process) = child.as_mut() {
        if process
            .try_wait()
            .map_err(|error| error.to_string())?
            .is_none()
            && service_is_ready(&state.token, state.port, process.id())
        {
            return Ok(state.token.clone());
        }
    }
    if let Some(mut process) = child.take() {
        stop_child(&mut process);
    }
    Err(state
        .startup_error
        .lock()
        .map_err(|_| "本地服务状态不可用")?
        .clone()
        .unwrap_or_else(|| "本地服务已停止，请重试启动".into()))
}

#[tauri::command]
/// 失败后重新启动受保护的子服务；绝不复用占用端口的其他进程。
fn restart_local_service(state: tauri::State<'_, LocalService>) -> Result<String, String> {
    let mut child = state.child.lock().map_err(|_| "本地服务状态不可用")?;
    if let Some(process) = child.as_mut() {
        if process
            .try_wait()
            .map_err(|error| error.to_string())?
            .is_none()
            && service_is_ready(&state.token, state.port, process.id())
        {
            return Ok(state.token.clone());
        }
    }
    if let Some(mut process) = child.take() {
        stop_child(&mut process);
    }
    match start_local_service(&state.token, state.port) {
        Ok(process) => {
            *child = Some(process);
            *state
                .startup_error
                .lock()
                .map_err(|_| "本地服务状态不可用")? = None;
            Ok(state.token.clone())
        }
        Err(error) => {
            *state
                .startup_error
                .lock()
                .map_err(|_| "本地服务状态不可用")? = Some(error.clone());
            Err(error)
        }
    }
}

#[tauri::command]
/// 只允许在系统浏览器打开本切片已核验的深交所原件地址。
fn open_official_source(source_url: String) -> Result<(), String> {
    if !OFFICIAL_SOURCE_URLS.contains(&source_url.as_str()) {
        return Err("source URL is not an approved SZSE original".into());
    }
    let status = Command::new("open")
        .args(["-u", &source_url])
        .status()
        .map_err(|error| format!("could not open official source: {error}"))?;
    if !status.success() {
        return Err(format!("could not open official source: {status}"));
    }
    Ok(())
}

/// 从系统随机源创建每次启动独立的本地服务会话凭据。
fn new_session_token() -> Result<String, String> {
    let mut random = File::open("/dev/urandom")
        .map_err(|error| format!("could not access operating system randomness: {error}"))?;
    let mut bytes = [0_u8; 32];
    random
        .read_exact(&mut bytes)
        .map_err(|error| format!("could not create session token: {error}"))?;
    Ok(bytes.iter().map(|byte| format!("{byte:02x}")).collect())
}

fn workspace_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..")
}

/// 允许隔离联调指定回环端口，普通桌面开发仍使用 8000。
fn service_port() -> Result<u16, String> {
    match std::env::var("WOLF_SERVICE_PORT") {
        Ok(value) => value
            .parse::<u16>()
            .ok()
            .filter(|port| *port > 0)
            .ok_or_else(|| "WOLF_SERVICE_PORT 必须是有效的非零端口".into()),
        Err(std::env::VarError::NotPresent) => Ok(8000),
        Err(error) => Err(format!("无法读取 WOLF_SERVICE_PORT：{error}")),
    }
}

/// 用本次凭据和子进程 PID 验证就绪响应，避免接纳占用端口的其他服务。
fn service_is_ready(token: &str, port: u16, expected_pid: u32) -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(250)) else {
        return false;
    };
    if stream
        .set_read_timeout(Some(Duration::from_millis(500)))
        .is_err()
        || stream
            .set_write_timeout(Some(Duration::from_millis(500)))
            .is_err()
    {
        return false;
    }
    let request = format!("GET /api/session/ready HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nX-Wolf-Session: {token}\r\nConnection: close\r\n\r\n");
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut response = BufReader::new(stream);
    let mut line = String::new();
    if response.read_line(&mut line).is_err() || !line.starts_with("HTTP/1.1 200 ") {
        return false;
    }
    loop {
        line.clear();
        if response.read_line(&mut line).is_err() || line.is_empty() {
            return false;
        }
        if line == "\r\n" {
            return false;
        }
        let lower = line.to_ascii_lowercase();
        if let Some(value) = lower.strip_prefix("x-wolf-service-pid:") {
            return value.trim().parse::<u32>().ok() == Some(expected_pid);
        }
    }
}

/// 有界等待子服务通过受保护就绪接口；退出或端口冲突立即报错。
fn wait_for_service(child: &mut Child, token: &str, port: u16) -> Result<(), String> {
    let deadline = Instant::now() + Duration::from_secs(8);
    loop {
        if let Some(status) = child.try_wait().map_err(|error| error.to_string())? {
            let address = SocketAddr::from(([127, 0, 0, 1], port));
            if TcpStream::connect_timeout(&address, Duration::from_millis(250)).is_ok() {
                return Err(port_occupied_message(port));
            }
            return Err(format!("本地服务启动失败：子进程退出（{status}）"));
        }
        if service_is_ready(token, port, child.id()) {
            return Ok(());
        }
        if Instant::now() >= deadline {
            return Err("本地服务启动超时，请检查 Python 环境后重试".into());
        }
        thread::sleep(Duration::from_millis(100));
    }
}

/// 失败和窗口退出时均回收已创建的子进程。
fn stop_child(child: &mut Child) {
    let _ = child.kill();
    let _ = child.wait();
}

/// 提示复用已有窗口；端口仍被占用时重试不会改变结果。
fn port_occupied_message(port: u16) -> String {
    format!("本地服务端口 {port} 已被其他进程占用。若已打开 TheWolf，请切回该窗口；否则退出占用进程后重试")
}

/// 启动仅绑定本机回环地址的 Python 服务，并传入独立数据根与会话凭据。
fn start_local_service(token: &str, port: u16) -> Result<Child, String> {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let listener = TcpListener::bind(address).map_err(|error| {
        if error.kind() == std::io::ErrorKind::AddrInUse {
            port_occupied_message(port)
        } else {
            format!("无法检查本地服务端口 {port}：{error}")
        }
    })?;
    drop(listener);
    let root = workspace_root();
    let python = root.join("python/.venv/bin/python");
    let source = root.join("python/src");
    let mut command = Command::new(python);
    command
        .args(["-m", "uvicorn", "pmi.api:app", "--app-dir"])
        .arg(source)
        // 父进程异常退出会关闭管道，Python 服务据此自行释放端口。
        .args(["--host", "127.0.0.1", "--port", &port.to_string()])
        .stdin(Stdio::piped());
    let data_root = std::env::var_os("WOLF_SLICE_DATA_ROOT")
        .map(PathBuf::from)
        .unwrap_or_else(|| root.join(".local-data/slice-002245-sina"));
    command.env("WOLF_SLICE_DATA_ROOT", data_root);
    let mut child = command
        .env("WOLF_SESSION_TOKEN", token)
        .env("WOLF_PARENT_PIPE", "1")
        .env("WOLF_ALLOWED_HOST", format!("127.0.0.1:{port}"))
        .spawn()
        .map_err(|error| format!("无法创建本地 Python 服务进程：{error}"))?;
    if let Err(error) = wait_for_service(&mut child, token, port) {
        stop_child(&mut child);
        return Err(error);
    }
    Ok(child)
}

fn main() {
    tauri::Builder::default()
        // 在创建 Python 子服务前拦截重复启动，并唤起已有主窗口。
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.unminimize();
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .invoke_handler(tauri::generate_handler![
            session_token,
            restart_local_service,
            open_official_source
        ])
        .setup(|app| {
            let token = new_session_token()?;
            let port = service_port()?;
            let (child, startup_error) = match start_local_service(&token, port) {
                Ok(process) => (Some(process), None),
                Err(error) => (None, Some(error)),
            };
            app.manage(LocalService {
                child: Mutex::new(child),
                token,
                port,
                startup_error: Mutex::new(startup_error),
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building TheWolf desktop application")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                let state = app.state::<LocalService>();
                let child = {
                    let mut guard = state.child.lock().expect("local service lock was poisoned");
                    guard.take()
                };
                if let Some(mut child) = child {
                    stop_child(&mut child);
                }
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;

    #[test]
    fn occupied_port_is_reported_after_child_exits() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let mut child = Command::new("sh").args(["-c", "exit 1"]).spawn().unwrap();
        let error = wait_for_service(&mut child, "synthetic-session", port).unwrap_err();
        assert!(error.contains("已被其他进程占用"), "{error}");
        stop_child(&mut child);
    }

    #[test]
    fn ready_check_rejects_other_session() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut request = [0_u8; 256];
            let count = stream.read(&mut request).unwrap();
            assert!(String::from_utf8_lossy(&request[..count])
                .contains("X-Wolf-Session: synthetic-session"));
            stream
                .write_all(b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\n\r\n")
                .unwrap();
        });
        assert!(!service_is_ready("synthetic-session", port, 12345));
        server.join().unwrap();
    }

    #[test]
    fn ready_check_rejects_wrong_process_id() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut request = [0_u8; 256];
            stream.read(&mut request).unwrap();
            stream
                .write_all(b"HTTP/1.1 200 OK\r\nX-Wolf-Service-Pid: 1\r\n\r\n")
                .unwrap();
        });
        assert!(!service_is_ready("synthetic-session", port, 2));
        server.join().unwrap();
    }

    #[test]
    fn failed_start_recovers_after_owned_port_is_released() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let directory = std::env::temp_dir().join(format!("thewolf-r04-{}", std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        let previous_root = std::env::var_os("WOLF_SLICE_DATA_ROOT");
        std::env::set_var("WOLF_SLICE_DATA_ROOT", &directory);
        let failure = start_local_service("synthetic-session", port)
            .err()
            .unwrap();
        assert!(failure.contains("已被其他进程占用"), "{failure}");
        drop(listener);

        let mut service = start_local_service("synthetic-session", port).unwrap();
        assert!(service_is_ready("synthetic-session", port, service.id()));
        assert!(!service_is_ready("wrong-session", port, service.id()));
        stop_child(&mut service);
        assert!(!service_is_ready("synthetic-session", port, service.id()));
        match previous_root {
            Some(value) => std::env::set_var("WOLF_SLICE_DATA_ROOT", value),
            None => std::env::remove_var("WOLF_SLICE_DATA_ROOT"),
        }
        std::fs::remove_dir_all(&directory).unwrap();
    }
}
