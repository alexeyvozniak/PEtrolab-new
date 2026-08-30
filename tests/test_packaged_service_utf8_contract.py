from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PackagedServiceUtf8ContractTests(unittest.TestCase):
    def test_packaged_service_forces_utf8_stdio(self) -> None:
        entrypoint = (ROOT / "scripts" / "petrolab_service.py").read_text(encoding="utf-8")
        self.assertIn('reconfigure(encoding="utf-8", errors="strict")', entrypoint)
        self.assertIn('for stream_name in ("stdin", "stdout", "stderr")', entrypoint)

    def test_tauri_launcher_also_forces_utf8_and_consumes_complete_records(self) -> None:
        shell = (ROOT / "desktop" / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")
        self.assertIn('.env("PYTHONUTF8", "1")', shell)
        self.assertIn('.env("PYTHONIOENCODING", "utf-8")', shell)
        self.assertIn("read_until(b'\\n'", shell)
        self.assertIn("serde_json::from_slice(&line)", shell)


if __name__ == "__main__":
    unittest.main()
