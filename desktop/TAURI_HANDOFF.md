# Tauri shell handoff

The shell starts exactly one local scientific process and routes typed envelope objects through the Rust command `petrolab_command`. It opens no localhost API. Development uses `python -m petrolab.ndjson_service`; the Windows release bundle uses `binaries/petrolab-service.exe`, created by `scripts/build_windows_service.py` and embedded into the installer.

For development, set `PETROLAB_PYTHONPATH` to the repository `src` directory. Optionally set `PETROLAB_PYTHON` when the interpreter is not available as `python`.

Required verification in a Rust-capable environment:

```bash
cd desktop
PETROLAB_PYTHONPATH=../src npm run tauri dev
PETROLAB_PYTHONPATH=../src npm run tauri build
```

For a Windows installer, first run `python -m pip install pyinstaller` and `python scripts/build_windows_service.py` from the repository root. The GitHub workflow performs these steps and uploads the resulting installer as a test artifact.

The frontend API is `src/desktopApi.js`. It sends the protocol envelope defined in `schemas/protocol-envelope.schema.json`; React never reads SQLite or executes scientific code directly.
