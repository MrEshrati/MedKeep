from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _identity_part(value: str | None, label: str):
    if not value or len(value) > 40 or not all(char.isalnum() for char in value):
        raise ValueError(f"{label} must contain 1–40 letters or numbers, without spaces or path separators.")
    return value


def create_package(output_dir: Path, *, project_root: Path = PROJECT_ROOT, source: bool = False,
                   first_name: str | None = None, last_name: str | None = None,
                   student_number: str | None = None):
    if source:
        filename = "MedKeep-source.zip"
    else:
        first = _identity_part(first_name, "First name")
        last = _identity_part(last_name, "Last name")
        number = _identity_part(student_number, "Student number")
        filename = f"DSAProject1_{first}{last}_{number}.zip"
    project_root = project_root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / filename
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=output_dir, prefix=".medkeep-package-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name in ("README.md", "requirements.txt", "run.py", "run.pyw", ".gitignore", ".gitattributes"):
                path = project_root / name
                if path.is_file() and not path.is_symlink():
                    archive.write(path, name)
            for name in ("medkeep", "tests", "docs", "tools", ".github"):
                directory = project_root / name
                if not directory.is_dir() or directory.is_symlink():
                    continue
                for path in directory.rglob("*"):
                    if not path.is_file() or path.is_symlink() or "__pycache__" in path.parts:
                        continue
                    if not path.resolve().is_relative_to(project_root):
                        continue
                    if path.suffix not in (".py", ".md", ".png", ".yml", ".yaml"):
                        continue
                    archive.write(path, path.relative_to(project_root).as_posix())
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise OSError("The generated ZIP failed its integrity check.")
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return destination


def main():
    parser = argparse.ArgumentParser(description="Package MedKeep source without patient data or local settings")
    parser.add_argument("--source", action="store_true", help="create MedKeep-source.zip without student identity")
    parser.add_argument("--first-name")
    parser.add_argument("--last-name")
    parser.add_argument("--student-number")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "dist")
    options = parser.parse_args()
    if options.source and any((options.first_name, options.last_name, options.student_number)):
        parser.error("Use either --source or the three student identity fields.")
    try:
        path = create_package(options.output_dir, source=options.source, first_name=options.first_name,
                              last_name=options.last_name, student_number=options.student_number)
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        parser.exit(2, f"Could not create the source package: {error}\n")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
