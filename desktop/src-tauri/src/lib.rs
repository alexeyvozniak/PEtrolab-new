use std::{
    env,
    fs,
    io::{BufRead, BufReader, Write},
    path::PathBuf,
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};

use serde_json::{json, Value};
use tauri::{path::BaseDirectory, AppHandle, Manager, State};
use uuid::Uuid;

struct PythonService {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
}

impl PythonService {
    fn start(app: &AppHandle) -> Result<Self, String> {
        let use_development_python = cfg!(debug_assertions) || env::var("PETROLAB_PYTHON").is_ok();
        let mut command = if use_development_python {
            let executable = env::var("PETROLAB_PYTHON").unwrap_or_else(|_| "python".to_owned());
            let mut command = Command::new(executable);
            command.args(["-m", "petrolab.ndjson_service"]);
            if let Ok(python_path) = env::var("PETROLAB_PYTHONPATH") {
                command.env("PYTHONPATH", python_path);
            }
            command
        } else {
            let service = app
                .path()
                .resolve("binaries/petrolab-service.exe", BaseDirectory::Resource)
                .map_err(|error| format!("Cannot resolve bundled scientific service: {error}"))?;
            Command::new(service)
        };
        command.stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::inherit());

        let mut child = command.spawn().map_err(|error| format!("Cannot start PetroLab scientific service: {error}"))?;
        let stdin = child.stdin.take().ok_or("Scientific service stdin is unavailable.")?;
        let stdout = child.stdout.take().ok_or("Scientific service stdout is unavailable.")?;
        Ok(Self { child, stdin, stdout: BufReader::new(stdout) })
    }

    fn request(&mut self, envelope: Value) -> Result<Value, String> {
        let request_id = envelope
            .get("request_id")
            .and_then(Value::as_str)
            .ok_or("Desktop request has no request_id.")?
            .to_owned();
        serde_json::to_writer(&mut self.stdin, &envelope).map_err(|error| format!("Cannot encode request: {error}"))?;
        self.stdin.write_all(b"\n").map_err(|error| format!("Cannot send request: {error}"))?;
        self.stdin.flush().map_err(|error| format!("Cannot flush request: {error}"))?;

        let mut line = String::new();
        let read = self.stdout.read_line(&mut line).map_err(|error| format!("Cannot read scientific service response: {error}"))?;
        if read == 0 {
            return Err("Scientific service stopped before responding.".to_owned());
        }
        let response: Value = serde_json::from_str(&line).map_err(|error| format!("Scientific service returned invalid JSON: {error}"))?;
        if response.get("request_id").and_then(Value::as_str) != Some(request_id.as_str()) {
            return Err("Scientific service response does not match the request.".to_owned());
        }
        Ok(response)
    }

    fn shutdown(&mut self) {
        let shutdown = json!({
            "protocol_version": "1.0",
            "request_id": Uuid::new_v4().to_string(),
            "command": "shutdown",
            "payload": {},
        });
        let _ = serde_json::to_writer(&mut self.stdin, &shutdown);
        let _ = self.stdin.write_all(b"\n");
        let _ = self.stdin.flush();
        let deadline = Instant::now() + Duration::from_secs(2);
        while Instant::now() < deadline {
            if self.child.try_wait().ok().flatten().is_some() {
                return;
            }
            thread::sleep(Duration::from_millis(25));
        }
    }
}

impl Drop for PythonService {
    fn drop(&mut self) {
        self.shutdown();
        let _ = self.child.kill();
    }
}

#[tauri::command]
fn petrolab_command(envelope: Value, service: State<'_, Mutex<PythonService>>) -> Result<Value, String> {
    let mut service = service.lock().map_err(|_| "Scientific service lock is unavailable.".to_owned())?;
    service.request(envelope)
}

fn staging_root(app: &AppHandle) -> Result<PathBuf, String> {
    let root = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Cannot resolve PetroLab application data directory: {error}"))?
        .join("import-staging");
    fs::create_dir_all(&root).map_err(|error| format!("Cannot create PetroLab import staging directory: {error}"))?;
    Ok(root)
}

#[tauri::command]
fn pick_import_file(app: AppHandle) -> Result<Option<Value>, String> {
    let Some(source) = rfd::FileDialog::new()
        .add_filter("PetroLab data", &["xlsx", "csv", "tsv"])
        .pick_file()
    else {
        return Ok(None);
    };

    let file_name = source
        .file_name()
        .ok_or("Selected import file has no file name.")?
        .to_owned();
    let staging_directory = staging_root(&app)?.join(Uuid::new_v4().to_string());
    fs::create_dir_all(&staging_directory)
        .map_err(|error| format!("Cannot create temporary import directory: {error}"))?;
    let staged = staging_directory.join(file_name);

    if let Err(error) = fs::copy(&source, &staged) {
        let _ = fs::remove_dir_all(&staging_directory);
        return Err(format!(
            "PetroLab can see the selected path but Windows did not allow the file to be read: {} ({error}). If this is a mapped network drive such as O:, reopen PetroLab normally rather than from an elevated installer, or use the network/UNC location.",
            source.to_string_lossy()
        ));
    }

    Ok(Some(json!({
        "original_path": source.to_string_lossy(),
        "local_path": staged.to_string_lossy(),
    })))
}

#[tauri::command]
fn clear_import_staging(app: AppHandle, staged_path: String) -> Result<(), String> {
    let root = staging_root(&app)?;
    let candidate = PathBuf::from(staged_path);
    if !candidate.starts_with(&root) {
        return Err("Refusing to remove a file outside PetroLab import staging.".to_owned());
    }
    if let Some(directory) = candidate.parent() {
        if directory.exists() {
            fs::remove_dir_all(directory).map_err(|error| format!("Cannot clear temporary import file: {error}"))?;
        }
    }
    Ok(())
}

#[tauri::command]
fn project_database_path(app: AppHandle) -> Result<String, String> {
    let directory = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Cannot resolve PetroLab application data directory: {error}"))?;
    fs::create_dir_all(&directory).map_err(|error| format!("Cannot create PetroLab application data directory: {error}"))?;
    Ok(directory.join("petrolab-v2.sqlite").to_string_lossy().into_owned())
}

pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let service = PythonService::start(&app.handle()).map_err(std::io::Error::other)?;
            app.manage(Mutex::new(service));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            petrolab_command,
            pick_import_file,
            clear_import_staging,
            project_database_path
        ])
        .run(tauri::generate_context!())
        .expect("Tauri application failed");
}
