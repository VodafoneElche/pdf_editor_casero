"""PDF Familiar: lector y editor de PDF para uso familiar."""

VERSION_BASE = "1.0"
try:  # el número de compilación lo escribe el instalador (GitHub Actions)
    from ._compilacion import COMPILACION
except ImportError:
    COMPILACION = "0"

__version__ = f"{VERSION_BASE}.{COMPILACION}"
