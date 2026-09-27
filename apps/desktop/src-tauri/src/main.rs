#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    fs::File,
    io::Read,
    path::PathBuf,
    process::{Child, Command},
    sync::Mutex,
};
use tauri::Manager;

struct LocalService {
    child: Mutex<Option<Child>>,
    token: String,
}

const OFFICIAL_SOURCE_URLS: [&str; 2] = [
    "https://disc.static.szse.cn/download/disc/disk03/finalpage/2026-07-14/a4f123a2-bf8a-4583-b077-0a01259eb8db.PDF",
    "https://disc.static.szse.cn/download/disc/disk03/finalpage/2026-08-18/feb8d686-bf51-4395-b9f9-1c94489b5d63.PDF",
];

#[tauri::command]
/// 向桌面页面提供当前进程的本地 API 会话凭据。
fn session_token(state: tauri::State<'_, LocalService>) -> String {
    state.token.clone()
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

/// 启动仅绑定本机回环地址的 Python 服务，并传入独立数据根与会话凭据。
fn start_local_service(token: &str) -> Result<Child, String> {
    let root = workspace_root();
    let python = root.join("python/.venv/bin/python");
    let source = root.join("python/src");
    let mut command = Command::new(python);
    command
        .args(["-m", "uvicorn", "pmi.api:app", "--app-dir"])
        .arg(source)
        .args(["--host", "127.0.0.1", "--port", "8000"]);
    let data_root = std::env::var_os("WOLF_SLICE_DATA_ROOT")
        .map(PathBuf::from)
        .unwrap_or_else(|| root.join(".local-data/slice-002245-sina"));
    command.env("WOLF_SLICE_DATA_ROOT", data_root);
    command
        .env("WOLF_SESSION_TOKEN", token)
        .env("WOLF_ALLOWED_HOST", "127.0.0.1:8000")
        .spawn()
        .map_err(|error| format!("could not start local Python service: {error}"))
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            session_token,
            open_official_source
        ])
        .setup(|app| {
            let token = new_session_token()?;
            let child = start_local_service(&token)?;
            app.manage(LocalService {
                child: Mutex::new(Some(child)),
                token,
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
                    if let Err(error) = child.kill() {
                        eprintln!("could not stop local Python service: {error}");
                    }
                    if let Err(error) = child.wait() {
                        eprintln!("could not reap local Python service: {error}");
                    }
                }
            }
        });
}
