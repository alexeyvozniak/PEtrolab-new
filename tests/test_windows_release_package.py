from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_windows_release_package.py"


class WindowsReleasePackageTests(unittest.TestCase):
    def test_package_must_match_run_version_and_exact_installer_bytes(self):
        with TemporaryDirectory() as directory:
            package = Path(directory)
            version, commit = "0.1.7", "a" * 40
            installer = package / f"PetroLab_{version}_x64_en-US.msi"
            contents = b"bytes of the clean-tested installer"
            installer.write_bytes(contents)
            checksum = sha256(contents).hexdigest()
            metadata = {"commit": commit, "run_id": "123", "attempt": "2", "installer": installer.name,
                        "sha256": checksum, "upgrade_baselines": ["rehearsal", "historical"]}
            info = package / "build-info.json"
            info.write_text(json.dumps(metadata), encoding="utf-8-sig")
            sums = package / "SHA256SUMS.txt"
            sums.write_text(f"{checksum}  {installer.name}\n", encoding="ascii")

            def verify(*, run="123", attempt="2", tag_version=version):
                return subprocess.run([sys.executable, str(SCRIPT), str(package), commit, run, attempt, tag_version],
                                      capture_output=True, text=True, timeout=10)

            valid = verify()
            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertEqual(valid.stdout.strip(), installer.name)
            self.assertNotEqual(verify(run="124").returncode, 0)
            self.assertNotEqual(verify(attempt="1").returncode, 0)
            self.assertNotEqual(verify(tag_version="0.1.8").returncode, 0)
            for baselines in (None, ["rehearsal"], ["historical"]):
                incomplete = {**metadata, "upgrade_baselines": baselines}
                info.write_text(json.dumps(incomplete), encoding="utf-8-sig")
                missing_upgrade = verify()
                self.assertNotEqual(missing_upgrade.returncode, 0)
                self.assertIn("both the rehearsal and historical MSI upgrades", missing_upgrade.stderr)
            info.write_text(json.dumps(metadata), encoding="utf-8-sig")
            installer.write_bytes(contents + b"!")
            wrong_bytes = verify()
            self.assertNotEqual(wrong_bytes.returncode, 0)
            self.assertIn("Installer bytes", wrong_bytes.stderr)
            installer.write_bytes(contents)
            sums.write_text(f"{'0' * 64}  {installer.name}\n", encoding="ascii")
            wrong_sums = verify()
            self.assertNotEqual(wrong_sums.returncode, 0)
            self.assertIn("Checksum file", wrong_sums.stderr)
