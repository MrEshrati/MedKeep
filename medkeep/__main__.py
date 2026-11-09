"""Run with python -m medkeep [--data-dir PATH]."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="MedKeep offline medical-record desktop application")
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parents[1] / "data",
                        help="local workspace directory (default: data beside the application)")
    parser.add_argument("--version", action="version", version="MedKeep 1.0.0")
    options = parser.parse_args()
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        print("Tkinter is missing. Install Python with Tcl/Tk support (python3-tk on many Linux systems).", file=sys.stderr)
        return 2
    from .platform_support import enable_dpi_awareness
    enable_dpi_awareness()
    try:
        root = tk.Tk()
    except tk.TclError:
        print("A graphical desktop and a working Tcl/Tk installation are required to open MedKeep.", file=sys.stderr)
        return 2
    root.withdraw()
    from .records import DecodeError
    from .service import MedKeepService
    from .ui import MedKeepApp
    try:
        service = MedKeepService(options.data_dir)
    except (OSError, DecodeError) as error:
        messagebox.showerror("MedKeep — workspace unavailable", f"{error}\n\nExisting data was preserved. Close other MedKeep windows or use a different --data-dir.", parent=root)
        root.destroy()
        return 2
    try:
        MedKeepApp(root, service)
        root.deiconify()
        root.mainloop()
    finally:
        service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
