import sys


def enable_dpi_awareness():
    if sys.platform == "win32":
        import ctypes
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def dark_titlebar(root):
    if sys.platform == "win32":
        import ctypes
        try:
            handle = ctypes.windll.user32.GetParent(root.winfo_id())
            enabled = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(handle, 20, ctypes.byref(enabled), ctypes.sizeof(enabled))
        except (AttributeError, OSError):
            pass
