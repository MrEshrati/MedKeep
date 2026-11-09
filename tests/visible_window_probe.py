"""A separate process lets the test bound native redraw-loop failures."""

from pathlib import Path
import sys
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from medkeep.platform_support import enable_dpi_awareness
from medkeep.service import MedKeepService
from medkeep.ui import MedKeepApp


def main():
    enable_dpi_awareness()
    service = MedKeepService(Path(sys.argv[1]))
    root = tk.Tk()
    root.withdraw()
    try:
        app = MedKeepApp(root, service)
        root.after(250, app.close)
        root.deiconify()
        root.mainloop()
        if not app.closed:
            raise RuntimeError("The visible window did not complete its close callback.")
    finally:
        service.close()


if __name__ == "__main__":
    main()
