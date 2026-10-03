from __future__ import annotations

import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = PROJECT_ROOT / "dist"
EXCLUDED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "data", "dist"}


def should_include(path: Path) -> bool:
    relative_parts = path.relative_to(PROJECT_ROOT).parts
    has_excluded_part = any(
        part in EXCLUDED_PARTS or part.endswith(".egg-info") for part in relative_parts
    )
    has_excluded_name = path.name == ".coverage" or path.name.endswith((".pyc", ".pyo"))
    return not has_excluded_part and not has_excluded_name


def main() -> None:
    version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    DIST_DIR.mkdir(exist_ok=True)
    archive_path = DIST_DIR / f"redlake-ai-v{version}.zip"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for candidate in sorted(PROJECT_ROOT.rglob("*")):
            if candidate.is_file() and should_include(candidate):
                archive.write(candidate, candidate.relative_to(PROJECT_ROOT))
    checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path = archive_path.with_suffix(".zip.sha256")
    checksum_path.write_text(f"{checksum}  {archive_path.name}\n", encoding="utf-8")
    print(f"Created {archive_path.name}")
    print(f"SHA256  {checksum}")


if __name__ == "__main__":
    main()
