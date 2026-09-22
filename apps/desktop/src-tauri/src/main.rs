#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    path::PathBuf,
    process::{Child, Command},
    sync::Mutex,
};
use tauri::Manager;

struct LocalService(Mutex<Option<Child>>);

fn workspace_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..")
}

fn start_local_service() -> Result<Child, String> {
    let root = workspace_root();
    let python = root.join("python/.venv/bin/python");
    let source = root.join("python/src");
    let data_root = root.join(".local-data");

    Command::new(python)
        .args(["-m", "uvicorn", "pmi.api:app", "--app-dir"])
        .arg(source)
        .args(["--host", "127.0.0.1", "--port", "8000"])
        .env("WOLF_DATA_ROOT", data_root)
        .spawn()
        .map_err(|error| format!("could not start local Python service: {error}"))
}

fn main() {
    tauri::Builder::default()
        .manage(LocalService(Mutex::new(None)))
        .setup(|app| {
            let child = start_local_service()?;
            let state = app.state::<LocalService>();
            *state.0.lock().expect("local service lock was poisoned") = Some(child);
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building TheWolf desktop application")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                let state = app.state::<LocalService>();
                let child = {
                    let mut guard = state.0.lock().expect("local service lock was poisoned");
                    guard.take()
                };
                if let Some(mut child) = child {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        });
}
