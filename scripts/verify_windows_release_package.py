"""Check that the MSI and release metadata match a successful Windows build."""

import argparse
from hashlib import file_digest
import json
from pathlib import Path
import re


def verify_package(directory, commit, run_id, attempt, version):
    directory = Path(directory)
    installer = f"PetroLab_{version}_x64_en-US.msi"
    expected = {installer, "build-info.json", "SHA256SUMS.txt"}
    members = list(directory.iterdir())
    if {item.name for item in members} != expected or any(not item.is_file() or item.is_symlink() for item in members):
        raise ValueError("Expected exactly the MSI, build identity and checksum files.")

    metadata = json.loads((directory / "build-info.json").read_text(encoding="utf-8-sig"))
    identity = {"commit": commit, "run_id": run_id, "attempt": attempt, "installer": installer}
    if not isinstance(metadata, dict) or any(metadata.get(key) != value for key, value in identity.items()):
        raise ValueError("Package identity does not match the selected Windows run and version.")

    checksum = metadata.get("sha256")
    if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise ValueError("Package has an invalid SHA-256 value.")
    if (directory / "SHA256SUMS.txt").read_text(encoding="ascii").rstrip("\r\n") != f"{checksum}  {installer}":
        raise ValueError("Checksum file does not match the package metadata.")
    with (directory / installer).open("rb") as stream:
        if file_digest(stream, "sha256").hexdigest() != checksum:
            raise ValueError("Installer bytes do not match the verified SHA-256.")
    return installer


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("commit")
    parser.add_argument("run_id")
    parser.add_argument("attempt")
    parser.add_argument("version")
    args = parser.parse_args()
    try:
        print(verify_package(args.directory, args.commit, args.run_id, args.attempt, args.version))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Windows release package rejected: {error}\n")
