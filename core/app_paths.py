"""
=====================================
APP PATHS — Resolusi folder (frozen vs dev)
=====================================
Helper path terpusat. Frozen (.exe) → folder di samping executable;
Dev → root project (parent dari core/).
"""

import sys
from pathlib import Path


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def data_dir() -> Path:
    d = base_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_excel(nama_file: str) -> str:
    """Cari file Excel relatif ke base_dir lalu cwd; kembalikan path absolut jika ketemu."""
    import os
    p = Path(nama_file)
    if p.is_absolute():
        return str(p)
    for basis in (base_dir(), Path(os.getcwd())):
        kandidat = basis / nama_file
        if kandidat.exists():
            return str(kandidat)
    return str(base_dir() / nama_file)
