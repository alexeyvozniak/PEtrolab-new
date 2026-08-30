# Tauri shell handoff

The shell starts exactly one local Python process, `python -m petrolab.ndjson_service`, and routes typed envelope objects through the Rust command `petrolab_command`. It opens no localhost API.

For development, set `PETROLAB_PYTHONPATH` to the repository `src` directory. Optionally set `PETROLAB_PYTHON` when the interpreter is not available as `python`.

Required verification in a Rust-capable environment:

```bash
cd desktop
PETROLAB_PYTHONPATH=../src npm run tauri dev
PETROLAB_PYTHONPATH=../src npm run tauri build
```

The frontend API is `src/desktopApi.js`. It sends the protocol envelope defined in `schemas/protocol-envelope.schema.json`; React never reads SQLite or executes scientific code directly.
