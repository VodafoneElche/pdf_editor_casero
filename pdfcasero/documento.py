"""Acceso al PDF con PyMuPDF. No depende de la interfaz, así se puede probar solo."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from . import dibujo, edicion, formularios

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
        return self.texto_de_palabras(n, range(desde, hasta + 1))

    def texto_de_palabras(self, n: int, indices) -> str:
        """Texto de esas palabras (por su número), en orden y respetando saltos de línea."""
        palabras = self.palabras(n)
        partes, anterior = [], None
        for w in (palabras[k] for k in sorted(indices) if k < len(palabras)):
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
        """Línea de texto bajo el punto; si no hay, letras de una imagen (formularios impresos, escaneos)."""
        punto = pymupdf.Point(x, y)
        return edicion.linea_en(self._doc[n], punto) or edicion.linea_de_imagen(self._doc[n], punto)

    def donde_escribir(self, n: int, x: float, y: float, tamano: float) -> tuple[float, float]:
        """Esquina superior izquierda del texto nuevo para un clic en (x, y).

        Si hay un renglón (una raya, como en "Fdo.: ____") justo debajo, el texto
        se apoya encima; si no, queda centrado en altura sobre el clic.
        """
        renglon = edicion.renglon_cercano(self._doc[n], pymupdf.Point(x, y))
        if renglon is not None:
            return x, renglon - 1.5 - tamano * 0.8
        return x, y - tamano * 0.55

    def cambiar_linea(self, n: int, linea, texto_nuevo: str) -> None:
        self._antes_de_cambiar()
        edicion.reemplazar_linea(self._doc[n], linea, texto_nuevo)
        self._despues_de_cambiar(n)

    def borrar_palabras(self, n: int, desde: int, hasta: int) -> None:
        self.borrar_palabras_elegidas(n, range(desde, hasta + 1))

    def borrar_palabras_elegidas(self, n: int, indices) -> None:
        todas = self.palabras(n)
        palabras = [todas[k] for k in sorted(indices) if k < len(todas)]
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

    # --- Organizar páginas ---------------------------------------------------
    def insertar_en_blanco(self, antes_de: int) -> int:
        """Añade una página en blanco del mismo tamaño que la vecina. Devuelve su número."""
        antes_de = max(0, min(antes_de, self.num_paginas))
        vecina = self._doc[max(0, antes_de - 1)] if self.num_paginas else None
        ancho, alto = (vecina.rect.width, vecina.rect.height) if vecina else (595, 842)
        self._antes_de_cambiar()
        self._doc.new_page(antes_de, width=ancho, height=alto)
        self._despues_de_cambiar()
        return antes_de

    def insertar_archivo(self, antes_de: int, ruta: str | Path, contrasena: str | None = None) -> int:
        """Inserta las páginas de otro PDF, o una imagen como página nueva. Devuelve cuántas páginas añade."""
        antes_de = max(0, min(antes_de, self.num_paginas))
        otro = pymupdf.open(ruta)
        try:
            if otro.needs_pass and not otro.authenticate(contrasena or ""):
                raise ContrasenaNecesaria(str(ruta))
            if not otro.is_pdf:
                otro = self._imagen_como_pdf(otro)
            cuantas = otro.page_count
            self._antes_de_cambiar()
            self._doc.insert_pdf(otro, start_at=antes_de)
        finally:
            otro.close()
        self._despues_de_cambiar()
        return cuantas

    def _imagen_como_pdf(self, imagen: pymupdf.Document) -> pymupdf.Document:
        """Coloca cada imagen centrada en una página del tamaño de las del documento."""
        ancho, alto = (self._doc[0].rect.width, self._doc[0].rect.height) if self.num_paginas else (595, 842)
        nuevo = pymupdf.open()
        for pagina_img in imagen:
            pix = pagina_img.get_pixmap()
            if pix.width > pix.height and alto > ancho:
                ancho_p, alto_p = alto, ancho  # imagen apaisada: página apaisada
            else:
                ancho_p, alto_p = ancho, alto
            pagina = nuevo.new_page(width=ancho_p, height=alto_p)
            margen = 24
            pagina.insert_image(pagina.rect + (margen, margen, -margen, -margen), pixmap=pix, keep_proportion=True)
        imagen.close()
        return nuevo

    def borrar_paginas(self, paginas: list[int]) -> None:
        paginas = sorted({p for p in paginas if 0 <= p < self.num_paginas})
        if not paginas or len(paginas) >= self.num_paginas:
            raise ValueError("Un PDF tiene que tener al menos una página")
        self._antes_de_cambiar()
        self._doc.delete_pages(paginas)
        self._despues_de_cambiar()

    def mover_pagina(self, desde: int, antes_de: int) -> int:
        """Mueve la página `desde` delante de la que ahora es `antes_de`. Devuelve su nueva posición."""
        if antes_de in (desde, desde + 1):
            return desde
        self._antes_de_cambiar()
        self._doc.move_page(desde, antes_de if antes_de < self.num_paginas else -1)
        self._despues_de_cambiar()
        return antes_de if antes_de < desde else antes_de - 1

    def duplicar_pagina(self, n: int) -> int:
        self._antes_de_cambiar()
        self._doc.fullcopy_page(n, n + 1 if n + 1 < self.num_paginas else -1)
        self._despues_de_cambiar()
        return n + 1

    def girar_pagina(self, n: int, grados: int = 90) -> None:
        self._antes_de_cambiar()
        pagina = self._doc[n]
        pagina.set_rotation((pagina.rotation + grados) % 360)
        self._despues_de_cambiar()

    # --- Formularios ---------------------------------------------------------
    def campos(self, n: int):
        return formularios.campos(self._doc[n])

    def campo_en(self, n: int, x: float, y: float):
        return formularios.campo_en(self._doc[n], x, y)

    def crear_campo(self, n: int, tipo: str, rect) -> int:
        nombre = formularios.nombre_libre(self._doc, tipo)
        self._antes_de_cambiar()
        xref = formularios.crear(self._doc[n], tipo, pymupdf.Rect(rect), nombre)
        self._despues_de_cambiar(n)
        return xref

    def mover_campo(self, n: int, xref: int, rect) -> None:
        self._antes_de_cambiar()
        formularios.mover(self._doc[n], xref, pymupdf.Rect(rect))
        self._despues_de_cambiar(n)

    def renombrar_campo(self, n: int, xref: int, nombre: str) -> None:
        nombre = nombre.strip()
        otros = {c.nombre for p in range(self.num_paginas) for c in self.campos(p) if c.xref != xref}
        if not nombre or nombre in otros:
            raise ValueError(f"Ya hay otro campo que se llama «{nombre}»" if nombre else "El nombre no puede estar vacío")
        self._antes_de_cambiar()
        formularios.renombrar(self._doc[n], xref, nombre)
        self._despues_de_cambiar(n)

    def rellenar_campo(self, n: int, xref: int, valor) -> None:
        self._antes_de_cambiar()
        formularios.poner_valor(self._doc[n], xref, valor)
        self._despues_de_cambiar(n)

    def borrar_campo(self, n: int, xref: int) -> None:
        self._antes_de_cambiar()
        formularios.borrar(self._doc[n], xref)
        self._despues_de_cambiar(n)

    # --- Dibujos ------------------------------------------------------------
    def dibujo_en(self, n: int, x: float, y: float):
        return dibujo.dibujo_en(self._doc[n], (x, y))

    def dibujos(self, n: int):
        return dibujo.dibujos(self._doc[n])

    def anadir_dibujo(self, n: int, d: "dibujo.Dibujo") -> int:
        self._antes_de_cambiar()
        xref = dibujo.crear(self._doc[n], d).xref
        self._despues_de_cambiar(n)
        return xref

    def cambiar_dibujo(self, n: int, xref: int, d: "dibujo.Dibujo") -> int:
        """Sustituye un dibujo por su versión modificada. Devuelve la nueva referencia."""
        self._antes_de_cambiar()
        nuevo = dibujo.reemplazar(self._doc[n], xref, d)
        self._despues_de_cambiar(n)
        return nuevo

    def borrar_dibujo(self, n: int, xref: int) -> None:
        self._antes_de_cambiar()
        dibujo.borrar(self._doc[n], xref)
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
