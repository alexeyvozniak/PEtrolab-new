"""PyInstaller entry point for the local PetroLab scientific service."""

from petrolab.ndjson_service import serve


if __name__ == "__main__":
    serve()
