"""Actualizaciones: mira en GitHub Releases si hay una versión nueva y la instala.

El instalador lo descarga la propia app, así que Windows no le pone la marca de
«descargado de internet» y no sale el aviso azul de SmartScreen al instalarlo.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO = "VodafoneElche/pdf_editor_casero"
ULTIMA = f"https://api.github.com/repos/{REPO}/releases/latest"
DESCARGAS = f"https://github.com/{REPO}/releases/download/"
_NOMBRE = re.compile(r"^PDFCasero-Instalador-[\d.]+\.exe$")


def numero(version: str) -> tuple[int, ...]:
    """"v1.0.31" → (1, 0, 31). Lo que no sean cifras se ignora."""
    return tuple(int(n) for n in re.findall(r"\d+", version))


def instalada() -> bool:
    """Solo la versión instalada (el .exe empaquetado) puede actualizarse."""
    return bool(getattr(sys, "frozen", False)) and sys.platform == "win32"


def _pedir(url: str, tiempo: float = 15):
    req = urllib.request.Request(url, headers={"User-Agent": "PDF-Familiar", "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=tiempo)


def buscar_nueva(actual: str) -> dict | None:
    """La versión publicada si es más nueva que `actual`: {"version", "url", "nombre", "tamano"}."""
    with _pedir(ULTIMA) as r:
        datos = json.load(r)
    version = datos.get("tag_name", "").lstrip("v")
    if not version or numero(version) <= numero(actual):
        return None
    for adjunto in datos.get("assets", []):
        nombre, url = adjunto.get("name", ""), adjunto.get("browser_download_url", "")
        # Solo el instalador de este repositorio
        if _NOMBRE.match(nombre) and url.startswith(DESCARGAS):
            return {"version": version, "url": url, "nombre": nombre, "tamano": int(adjunto.get("size") or 0)}
    return None


def descargar(nueva: dict, avance=lambda hecho, total: None, cancelado=lambda: False) -> Path | None:
    """Descarga el instalador a la carpeta temporal. None si se cancela."""
    carpeta = Path(tempfile.gettempdir()) / "PDFFamiliar-actualizacion"
    carpeta.mkdir(exist_ok=True)
    destino = carpeta / nueva["nombre"]
    parcial = destino.with_suffix(".parcial")
    total, hecho = nueva["tamano"], 0
    with _pedir(nueva["url"], tiempo=60) as r, open(parcial, "wb") as f:
        total = total or int(r.headers.get("Content-Length") or 0)
        while trozo := r.read(256 * 1024):
            if cancelado():
                break
            f.write(trozo)
            hecho += len(trozo)
            avance(hecho, total)
    if cancelado() or (total and hecho != total):
        parcial.unlink(missing_ok=True)
        if not cancelado():
            raise OSError("La descarga se ha cortado. Prueba otra vez.")
        return None
    os.replace(parcial, destino)
    return destino


def instalar(instalador: Path) -> None:
    """Lanza el instalador por su cuenta (sigue aunque la app se cierre) y vuelve a abrir la app al acabar."""
    banderas = 0
    if sys.platform == "win32":
        banderas = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [str(instalador), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/reabrir=si"],
        creationflags=banderas, close_fds=True,
    )
