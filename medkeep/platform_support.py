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
