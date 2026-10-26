"""Acceso al PDF con PyMuPDF. No depende de la interfaz, así se puede probar solo."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pymupdf


class ContrasenaNecesaria(Exception):
    """El PDF está protegido y hace falta una contraseña."""


@dataclass
class Resultado:
    pagina: int  # empieza en 0
    rect: pymupdf.Rect  # en puntos PDF


class Documento:
    def __init__(self, ruta: str | Path, contrasena: str | None = None):
        self.ruta = Path(ruta)
        self._doc = pymupdf.open(self.ruta)
        if self._doc.needs_pass:
            if not contrasena or not self._doc.authenticate(contrasena):
                self._doc.close()
                raise ContrasenaNecesaria(str(self.ruta))
        self._contrasena = contrasena
        self.modificado = False  # lo activarán el OCR y la edición de texto

    @property
    def num_paginas(self) -> int:
        return self._doc.page_count

    @property
    def titulo(self) -> str:
        titulo = (self._doc.metadata or {}).get("title") or ""
        return titulo.strip() or self.ruta.name

    def tamano_pagina(self, n: int) -> tuple[float, float]:
        """Ancho y alto de la página en puntos (1/72 de pulgada)."""
        r = self._doc[n].rect
        return r.width, r.height

    def renderizar(self, n: int, escala: float) -> tuple[bytes, int, int, int]:
        """Devuelve (bytes RGB, ancho, alto, bytes por fila) de la página a esa escala."""
        pix = self._doc[n].get_pixmap(matrix=pymupdf.Matrix(escala, escala), alpha=False)
        return pix.samples, pix.width, pix.height, pix.stride

    def buscar(self, texto: str) -> list[Resultado]:
        """Busca el texto en todas las páginas (sin distinguir mayúsculas)."""
        texto = texto.strip()
        if not texto:
            return []
        resultados = []
        for n in range(self.num_paginas):
            for rect in self._doc[n].search_for(texto):
                resultados.append(Resultado(n, rect))
        return resultados

    def tiene_texto(self, n: int) -> bool:
        """False si la página parece escaneada (sin texto), útil para el OCR."""
        return bool(self._doc[n].get_text("text").strip())

    def guardar(self, ruta: str | Path | None = None) -> Path:
        """Guarda en `ruta` (Guardar como) o encima del archivo actual (Guardar).

        Se escribe primero en un archivo temporal de la misma carpeta y luego se
        reemplaza el destino, para no dejar nunca un PDF a medias si algo falla.
        """
        destino = Path(ruta) if ruta else self.ruta
        mismo = destino.resolve() == self.ruta.resolve()
        fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=destino.parent)
        os.close(fd)
        try:
            self._doc.save(tmp, garbage=3, deflate=True)
            if mismo:
                # Windows no deja reemplazar un archivo abierto: cerrar, reemplazar y reabrir
                self._doc.close()
                try:
                    os.replace(tmp, destino)
                finally:
                    # Reabrir siempre, aunque falle el reemplazo, para no quedarnos sin documento
                    self._doc = pymupdf.open(destino)
                    if self._doc.needs_pass:
                        self._doc.authenticate(self._contrasena or "")
            else:
                os.replace(tmp, destino)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        self.ruta = destino
        self.modificado = False
        return destino

    def cerrar(self) -> None:
        self._doc.close()
