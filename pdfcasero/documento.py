"""Acceso al PDF con PyMuPDF. No depende de la interfaz, así se puede probar solo."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from . import edicion

MAX_DESHACER = 30


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
        self.modificado = False  # lo activan el OCR y la edición de texto
        self._palabras: dict[int, list] = {}
        self._deshacer: list[bytes] = []
        self._rehacer: list[bytes] = []

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

    def paginas_sin_texto(self) -> list[int]:
        return [n for n in range(self.num_paginas) if not self.tiene_texto(n)]

    def palabras(self, n: int) -> list[tuple]:
        """Palabras de la página en orden de lectura: (x0, y0, x1, y1, texto, bloque, línea, n)."""
        if n not in self._palabras:
            self._palabras[n] = self._doc[n].get_text("words", sort=True)
        return self._palabras[n]

    def texto_entre(self, n: int, desde: int, hasta: int) -> str:
        """Texto de las palabras desde..hasta (incluidas), respetando saltos de línea."""
        partes, anterior = [], None
        for w in self.palabras(n)[desde : hasta + 1]:
            linea = (w[5], w[6])
            if anterior is not None:
                partes.append(" " if linea == anterior else "\n")
            partes.append(w[4])
            anterior = linea
        return "".join(partes)

    def copia_en_memoria(self) -> bytes:
        """El PDF tal como está ahora, para trabajar con él en otro hilo sin tocar este."""
        return self._doc.tobytes()

    def aplicar_ocr(self, n: int, palabras) -> None:
        """Añade a la página n el texto reconocido por el OCR (invisible, pero buscable)."""
        from .ocr import insertar_capa_texto

        insertar_capa_texto(self._doc[n], palabras)
        self._palabras.pop(n, None)
        self.modificado = True

    # --- Edición ------------------------------------------------------------
    def _antes_de_cambiar(self) -> None:
        self._deshacer.append(self._doc.tobytes())
        del self._deshacer[:-MAX_DESHACER]
        self._rehacer.clear()

    def _despues_de_cambiar(self, n: int | None = None) -> None:
        if n is None:
            self._palabras.clear()
        else:
            self._palabras.pop(n, None)
        self.modificado = True

    def punto_de_deshacer(self) -> None:
        """Guarda el estado actual para poder volver a él con Deshacer (p. ej. antes del OCR)."""
        self._antes_de_cambiar()

    def linea_en(self, n: int, x: float, y: float):
        return edicion.linea_en(self._doc[n], pymupdf.Point(x, y))

    def cambiar_linea(self, n: int, linea, texto_nuevo: str) -> None:
        self._antes_de_cambiar()
        edicion.reemplazar_linea(self._doc[n], linea, texto_nuevo)
        self._despues_de_cambiar(n)

    def borrar_palabras(self, n: int, desde: int, hasta: int) -> None:
        palabras = self.palabras(n)[desde : hasta + 1]
        if not palabras:
            return
        rects = [pymupdf.Rect(w[:4]) for w in palabras]
        invisible = any(l.invisible for l in edicion.lineas(self._doc[n]) if l.rect.intersects(rects[0]))
        self._antes_de_cambiar()
        edicion.borrar_zonas(self._doc[n], rects, invisible)
        self._despues_de_cambiar(n)

    def escribir(self, n: int, x: float, y: float, texto: str, tamano: float = edicion.TAMANO_POR_DEFECTO) -> None:
        if not texto.strip():
            return
        self._antes_de_cambiar()
        edicion.escribir(self._doc[n], pymupdf.Point(x, y), texto, tamano)
        self._despues_de_cambiar(n)

    @property
    def puede_deshacer(self) -> bool:
        return bool(self._deshacer)

    @property
    def puede_rehacer(self) -> bool:
        return bool(self._rehacer)

    def deshacer(self) -> bool:
        return self._cambiar_estado(self._deshacer, self._rehacer)

    def rehacer(self) -> bool:
        return self._cambiar_estado(self._rehacer, self._deshacer)

    def _cambiar_estado(self, origen: list, destino: list) -> bool:
        if not origen:
            return False
        destino.append(self._doc.tobytes())
        self._doc.close()
        self._doc = pymupdf.open(stream=origen.pop(), filetype="pdf")
        if self._doc.needs_pass:
            self._doc.authenticate(self._contrasena or "")
        self._despues_de_cambiar()
        return True

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
                    self._palabras.clear()
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
