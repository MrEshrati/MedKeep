"""Small operating-system presentation helpers; independent of domain structures."""

import sys


def enable_dpi_awareness() -> None:
    """Avoid blurry, OS-scaled Windows rendering; call before creating Tk."""
    if sys.platform == "win32":
        import ctypes
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def dark_titlebar(root) -> None:
    """Ask Windows to use dark system chrome around the dark Clinical surface."""
    if sys.platform == "win32":
        import ctypes
        try:
            root.update_idletasks()
            handle = ctypes.windll.user32.GetParent(root.winfo_id())
            enabled = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(handle, 20, ctypes.byref(enabled), ctypes.sizeof(enabled))
        except (AttributeError, OSError):
            pass
