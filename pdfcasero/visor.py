"""Vista continua de páginas con zoom. Solo dibuja las páginas que se ven."""

from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QGuiApplication, QImage, QKeySequence, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QInputDialog, QLineEdit, QMenu, QMessageBox, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from .documento import Documento, Resultado
from .herramientas_dibujo import ControladorDibujo
from .herramientas_formulario import ControladorFormulario

# 100 % de zoom = tamaño real en una pantalla de 96 ppp
PUNTOS_A_PIXELES = 96 / 72
ZOOM_MIN, ZOOM_MAX = 0.25, 5.0
MARGEN = 16
MAX_CACHE = 24
TAMANO_TEXTO_NUEVO = 12


class PaginaWidget(QWidget):
    def __init__(self, visor: "VisorPDF", indice: int):
        super().__init__()
        self.visor = visor
        self.indice = indice
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    def _punto_pdf(self, evento) -> QPointF:
        return evento.position() / self.visor.escala

    def _tupla(self, evento) -> tuple[float, float]:
        p = self._punto_pdf(evento)
        return (p.x(), p.y())

    @property
    def _dibujando(self) -> bool:
        return self.visor.modo == "dibujar"

    @property
    def _formulario(self) -> bool:
        return self.visor.modo == "formulario"

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self._dibujando:
            self.visor.dibujo.soltar(self.indice, self._tupla(e))
        elif self._formulario:
            self.visor.formulario.soltar(self.indice, self._tupla(e))
        else:
            self.visor.terminar_seleccion()

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self._dibujando:
            self.visor.dibujo.pulsar(self.indice, self._tupla(e))
        elif self._formulario:
            self.visor.formulario.pulsar(self.indice, self._tupla(e))
        elif self.visor.modo_edicion:
            self.visor.editar_en(self, self._punto_pdf(e))
        elif not self.visor.rellenar_en(self, self._tupla(e)):
            recuadro = bool(e.modifiers() & Qt.KeyboardModifier.AltModifier)
            self.visor.empezar_seleccion(self.indice, self._punto_pdf(e), recuadro)

    def mouseMoveEvent(self, e):
        p = self._punto_pdf(e)
        if self._dibujando:
            self.setCursor(
                Qt.CursorShape.ArrowCursor if self.visor.dibujo.herramienta == "seleccionar" else Qt.CursorShape.CrossCursor
            )
            if e.buttons() & Qt.MouseButton.LeftButton:
                self.visor.dibujo.arrastrar(self.indice, self._tupla(e))
            return
        if self._formulario:
            self.setCursor(
                Qt.CursorShape.ArrowCursor
                if self.visor.formulario.herramienta == "seleccionar"
                else Qt.CursorShape.CrossCursor
            )
            if e.buttons() & Qt.MouseButton.LeftButton:
                self.visor.formulario.arrastrar(self.indice, self._tupla(e))
            return
        if self.visor.modo_edicion:
            self.setCursor(Qt.CursorShape.IBeamCursor)
            return
        if e.buttons() & Qt.MouseButton.LeftButton:
            self.visor.extender_seleccion(self.indice, p)
        elif self.visor.doc is not None and self.visor.doc.campo_en(self.indice, p.x(), p.y()) is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            return
        sobre_texto = self.visor.palabra_en(self.indice, p, exacta=True) is not None
        self.setCursor(Qt.CursorShape.IBeamCursor if sobre_texto else Qt.CursorShape.ArrowCursor)

    def mouseDoubleClickEvent(self, e):
        if self._dibujando:
            self.visor.dibujo.doble_clic(self.indice, self._tupla(e))
            return
        if self._formulario:
            self.visor.formulario.doble_clic(self.indice, self._tupla(e))
            return
        if self.visor.modo_edicion:
            return
        i = self.visor.palabra_en(self.indice, self._punto_pdf(e), exacta=True)
        if i is not None:
            self.visor.fijar_seleccion(self.indice, i, i)

    def contextMenuEvent(self, e):
        self.visor.menu_contextual(e.globalPos())

    def paintEvent(self, _evento):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.GlobalColor.white)
        img = self.visor.imagen_pagina(self.indice)
        if img is not None:
            p.drawImage(QRectF(self.rect()), img)
        escala = self.visor.escala
        azul = QColor(0, 110, 230, 80)
        for x0, y0, x1, y1 in self.visor.rects_seleccion(self.indice):
            p.fillRect(QRectF(x0 * escala, y0 * escala, (x1 - x0) * escala, (y1 - y0) * escala), azul)
        caja = self.visor.caja_de(self.indice)
        if caja is not None:
            p.setPen(QPen(QColor(0, 110, 230), 1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(caja.x() * escala, caja.y() * escala, caja.width() * escala, caja.height() * escala))
        for res, activo in self.visor.resaltados_de(self.indice):
            color = QColor(255, 140, 0, 120) if activo else QColor(255, 230, 0, 100)
            r = res.rect
            p.fillRect(QRectF(r.x0 * escala, r.y0 * escala, r.width * escala, r.height * escala), color)
        if self._dibujando:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            self.visor.dibujo.pintar(p, self.indice, escala)
        elif self._formulario:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            self.visor.formulario.pintar(p, self.indice, escala)
        p.end()


class EditorEnLinea(QLineEdit):
    """Cuadro de texto que aparece encima de la página para escribir o cambiar una línea."""

    FAMILIAS = {"ti": "Times New Roman", "co": "Courier New"}

    def __init__(self, pagina: PaginaWidget, rect: QRectF, texto: str, tamano_px: float, al_terminar, fuente_pdf="helv"):
        super().__init__(texto, pagina)
        self._al_terminar = al_terminar
        self._terminado = False
        self.setObjectName("editorEnLinea")
        fuente = self.font()
        if fuente_pdf[:2] in self.FAMILIAS:
            fuente.setFamily(self.FAMILIAS[fuente_pdf[:2]])
        fuente.setPixelSize(max(8, round(tamano_px)))
        self.setFont(fuente)
        alto = max(rect.height(), tamano_px * 1.5)
        ancho = max(rect.width() + tamano_px * 4, tamano_px * 12)
        self.setGeometry(round(rect.x() - 3), round(rect.y() - (alto - rect.height()) / 2), round(ancho), round(alto))
        self.selectAll()
        self.show()
        self.setFocus()

    def _terminar(self, aceptar: bool):
        if self._terminado:
            return
        self._terminado = True
        self._al_terminar(self.text() if aceptar else None)
        self.deleteLater()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._terminar(True)
        elif e.key() == Qt.Key.Key_Escape:
            self._terminar(False)
        else:
            super().keyPressEvent(e)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self._terminar(True)


class VisorPDF(QScrollArea):
    paginaCambiada = Signal(int)
    documentoEditado = Signal()
    zoomCambiado = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc: Documento | None = None
        self.zoom = 1.0
        self.ajustar_ancho = True
        self._cache: OrderedDict[tuple[int, float], QImage] = OrderedDict()
        self._paginas: list[PaginaWidget] = []
        self._resultados: list[Resultado] = []
        self._activo = -1
        self._pagina_actual = 0
        self._seleccion: tuple[int, list[int]] | None = None  # página, índices de las palabras elegidas
        self._caja: tuple[int, QPointF, QPointF] | None = None  # Alt + arrastrar: recuadro en curso
        self._ancla: int | None = None
        self._ancla_pagina = -1

        self.acc_copiar = QAction("Copiar", self)
        self.acc_copiar.setShortcut(QKeySequence.StandardKey.Copy)
        self.acc_copiar.triggered.connect(self.copiar)
        self.acc_sel_pagina = QAction("Seleccionar todo el texto de la página", self)
        self.acc_sel_pagina.setShortcut(QKeySequence.StandardKey.SelectAll)
        self.acc_sel_pagina.triggered.connect(self.seleccionar_pagina)
        self.acc_borrar = QAction("Borrar el texto seleccionado", self)
        self.acc_borrar.setShortcut(QKeySequence.StandardKey.Delete)
        self.acc_borrar.triggered.connect(self.borrar_seleccion)
        self.addActions([self.acc_copiar, self.acc_sel_pagina, self.acc_borrar])
        self.modo = "leer"
        self.dibujo = ControladorDibujo(self)
        self.formulario = ControladorFormulario(self)
        self._editor: EditorEnLinea | None = None

        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.setObjectName("visor")
        self._contenedor = QWidget()
        self._contenedor.setObjectName("fondoVisor")
        self._layout = QVBoxLayout(self._contenedor)
        self._layout.setContentsMargins(MARGEN, MARGEN, MARGEN, MARGEN)
        self._layout.setSpacing(MARGEN)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.setWidget(self._contenedor)

        self.verticalScrollBar().valueChanged.connect(self._al_desplazar)
        self._temporizador_ajuste = QTimer(self, singleShot=True, interval=60)
        self._temporizador_ajuste.timeout.connect(self._aplicar_ajuste_ancho)

    # --- Documento -------------------------------------------------------
    def cargar(self, doc: Documento | None) -> None:
        for w in self._paginas:
            w.deleteLater()
        self._paginas.clear()
        self._cache.clear()
        self._resultados, self._activo = [], -1
        self._seleccion = self._ancla = self._caja = None
        self.dibujo.cancelar()
        self.formulario.cancelar()
        self.doc = doc
        if doc is None:
            return
        for i in range(doc.num_paginas):
            w = PaginaWidget(self, i)
            self._layout.addWidget(w, 0, Qt.AlignmentFlag.AlignHCenter)
            self._paginas.append(w)
        self._pagina_actual = 0
        if self.ajustar_ancho:
            self._aplicar_ajuste_ancho()
        else:
            self._redimensionar()
        self.verticalScrollBar().setValue(0)
        self.paginaCambiada.emit(0)

    @property
    def escala(self) -> float:
        """Píxeles lógicos por punto PDF."""
        return self.zoom * PUNTOS_A_PIXELES

    def imagen_pagina(self, i: int) -> QImage | None:
        if self.doc is None:
            return None
        dpr = self.devicePixelRatioF()
        clave = (i, round(self.escala * dpr, 4))
        img = self._cache.get(clave)
        if img is None:
            datos, an, al, paso = self.doc.renderizar(i, clave[1])
            img = QImage(datos, an, al, paso, QImage.Format.Format_RGB888).copy()
            img.setDevicePixelRatio(dpr)
            self._cache[clave] = img
            while len(self._cache) > MAX_CACHE:
                self._cache.popitem(last=False)
        else:
            self._cache.move_to_end(clave)
        return img

    # --- Zoom ------------------------------------------------------------
    def set_zoom(self, zoom: float, ajustar_ancho: bool = False) -> None:
        zoom = max(ZOOM_MIN, min(ZOOM_MAX, zoom))
        self.ajustar_ancho = ajustar_ancho
        if abs(zoom - self.zoom) < 1e-4:
            return
        pagina = self._pagina_actual
        self.zoom = zoom
        self._redimensionar()
        self.ir_a_pagina(pagina)
        self.zoomCambiado.emit(self.zoom)

    def acercar(self):
        self.set_zoom(self.zoom * 1.2)

    def alejar(self):
        self.set_zoom(self.zoom / 1.2)

    def zoom_ajustar_ancho(self):
        self.ajustar_ancho = True
        self._aplicar_ajuste_ancho()

    def zoom_pagina_completa(self):
        if not self.doc:
            return
        an, al = self.doc.tamano_pagina(self._pagina_actual)
        vp = self.viewport().size()
        z = min((vp.width() - 2 * MARGEN) / an, (vp.height() - 2 * MARGEN) / al) / PUNTOS_A_PIXELES
        self.set_zoom(z)

    def _aplicar_ajuste_ancho(self):
        if not self.doc or not self.ajustar_ancho:
            return
        ancho_max = max(self.doc.tamano_pagina(i)[0] for i in range(min(self.doc.num_paginas, 20)))
        disponible = self.viewport().width() - 2 * MARGEN
        self.set_zoom(disponible / (ancho_max * PUNTOS_A_PIXELES), ajustar_ancho=True)
        self._redimensionar()

    def _redimensionar(self):
        if not self.doc:
            return
        for w in self._paginas:
            an, al = self.doc.tamano_pagina(w.indice)
            w.setFixedSize(round(an * self.escala), round(al * self.escala))
        self._contenedor.adjustSize()

    def resizeEvent(self, evento):
        super().resizeEvent(evento)
        if self.ajustar_ancho:
            self._temporizador_ajuste.start()

    def wheelEvent(self, evento: QWheelEvent):
        if evento.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.acercar() if evento.angleDelta().y() > 0 else self.alejar()
            evento.accept()
        else:
            super().wheelEvent(evento)

    # --- Navegación ------------------------------------------------------
    @property
    def pagina_actual(self) -> int:
        return self._pagina_actual

    def ir_a_pagina(self, i: int, y_puntos: float | None = None) -> None:
        if not self._paginas:
            return
        i = max(0, min(len(self._paginas) - 1, i))
        self._contenedor.layout().activate()
        w = self._paginas[i]
        y = w.y() - MARGEN
        if y_puntos is not None:
            y = w.y() + int(y_puntos * self.escala) - self.viewport().height() // 3
        self.verticalScrollBar().setValue(y)
        self._fijar_pagina(i)

    def pagina_siguiente(self):
        self.ir_a_pagina(self._pagina_actual + 1)

    def pagina_anterior(self):
        self.ir_a_pagina(self._pagina_actual - 1)

    def _al_desplazar(self, _valor):
        if not self._paginas:
            return
        centro = self.verticalScrollBar().value() + self.viewport().height() // 2
        for w in self._paginas:
            if w.y() + w.height() + MARGEN // 2 >= centro:
                self._fijar_pagina(w.indice)
                break

    def _fijar_pagina(self, i):
        if i != self._pagina_actual:
            self._pagina_actual = i
            self.paginaCambiada.emit(i)

    # --- Resaltado de búsqueda --------------------------------------------
    def mostrar_resultados(self, resultados: list[Resultado], activo: int) -> None:
        self._resultados, self._activo = resultados, activo
        if 0 <= activo < len(resultados):
            r = resultados[activo]
            self.ir_a_pagina(r.pagina, r.rect.y0)
        self._contenedor.update()
        for w in self._paginas:
            w.update()

    def resaltados_de(self, i: int):
        for n, r in enumerate(self._resultados):
            if r.pagina == i:
                yield r, n == self._activo

    # --- Selección de texto -------------------------------------------------
    def palabra_en(self, pagina: int, p: QPointF, exacta: bool = False) -> int | None:
        """Índice de la palabra bajo el punto; si no es exacta, la más cercana."""
        if self.doc is None:
            return None
        mejor, distancia = None, float("inf")
        for k, w in enumerate(self.doc.palabras(pagina)):
            dx = max(w[0] - p.x(), 0, p.x() - w[2])
            dy = max(w[1] - p.y(), 0, p.y() - w[3])
            d = dx * dx + dy * dy * 4  # pesa más estar en la misma línea
            if d < distancia:
                mejor, distancia = k, d
        if exacta and distancia > 0:
            return None
        return mejor

    def empezar_seleccion(self, pagina: int, p: QPointF, recuadro: bool = False):
        """Clic para seleccionar texto. Con `recuadro` (tecla Alt) se elige solo lo de dentro de un rectángulo."""
        self._seleccion = None
        self._ancla_pagina = pagina
        if recuadro:
            self._ancla = None
            self._caja = (pagina, p, p)
        else:
            self._ancla = self.palabra_en(pagina, p)
            self._caja = None
        self._repintar()

    def extender_seleccion(self, pagina: int, p: QPointF):
        if pagina != self._ancla_pagina:
            return
        if self._caja is not None:
            inicio = self._caja[1]
            self._caja = (pagina, inicio, p)
            x0, x1 = sorted((inicio.x(), p.x()))
            y0, y1 = sorted((inicio.y(), p.y()))
            dentro = [
                k
                for k, w in enumerate(self.doc.palabras(pagina))
                if x0 <= (w[0] + w[2]) / 2 <= x1 and y0 <= (w[1] + w[3]) / 2 <= y1
            ]
            self._seleccion = (pagina, dentro) if dentro else None
            self._repintar()
            return
        if self._ancla is None:
            return
        fin = self.palabra_en(pagina, p)
        if fin is not None:
            self.fijar_seleccion(pagina, self._ancla, fin)

    def terminar_seleccion(self):
        if self._caja is not None:
            self._caja = None
            self._repintar()

    def caja_de(self, pagina: int) -> QRectF | None:
        """Recuadro de Alt + arrastrar que hay que dibujar en esa página (en puntos PDF)."""
        if self._caja is None or self._caja[0] != pagina:
            return None
        return QRectF(self._caja[1], self._caja[2]).normalized()

    def fijar_seleccion(self, pagina: int, desde: int, hasta: int):
        self._seleccion = (pagina, list(range(min(desde, hasta), max(desde, hasta) + 1)))
        self._repintar()

    def seleccionar_pagina(self):
        if self.doc and self.doc.palabras(self._pagina_actual):
            self.fijar_seleccion(self._pagina_actual, 0, len(self.doc.palabras(self._pagina_actual)) - 1)

    def texto_seleccionado(self) -> str:
        if not self.doc or not self._seleccion:
            return ""
        return self.doc.texto_de_palabras(*self._seleccion)

    def copiar(self):
        texto = self.texto_seleccionado()
        if texto:
            QGuiApplication.clipboard().setText(texto)

    def rects_seleccion(self, pagina: int):
        if not self.doc or not self._seleccion or self._seleccion[0] != pagina:
            return []
        palabras = self.doc.palabras(pagina)
        return [palabras[k][:4] for k in self._seleccion[1] if k < len(palabras)]

    def menu_contextual(self, posicion):
        menu = QMenu(self)
        self.acc_copiar.setEnabled(bool(self._seleccion))
        menu.addAction(self.acc_copiar)
        menu.addAction(self.acc_sel_pagina)
        menu.exec(posicion)
        self.acc_copiar.setEnabled(True)

    # --- Edición de texto ---------------------------------------------------
    @property
    def modo_edicion(self) -> bool:
        return self.modo == "editar"

    def set_modo(self, modo: str):
        """'leer' (seleccionar texto y rellenar campos), 'editar' (texto), 'dibujar' o 'formulario'."""
        self.modo = modo
        self._seleccion = self._ancla = self._caja = None
        self.dibujo.cancelar()
        self.formulario.cancelar()
        self._repintar()

    def set_modo_edicion(self, activo: bool):
        self.set_modo("editar" if activo else "leer")

    def pedir_texto(self, n, p, texto, al_terminar, tamano=14):
        """Abre un cuadro para escribir en el punto p (en puntos PDF) de la página n."""
        if self._editor is not None:
            return
        escala = self.escala

        def terminar(nuevo):
            self._editor = None
            if nuevo is not None:
                al_terminar(nuevo.strip())

        rect = QRectF(p[0] * escala, p[1] * escala, 0, tamano * escala * 1.2)
        self._editor = EditorEnLinea(self._paginas[n], rect, texto, tamano * escala, terminar)

    def editar_en(self, pagina: PaginaWidget, p: QPointF):
        """Clic en modo edición: cambiar la línea que hay debajo, o escribir texto nuevo."""
        if self.doc is None or self._editor is not None:
            return
        n, escala = pagina.indice, self.escala
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            linea = self.doc.linea_en(n, p.x(), p.y())
        finally:
            self.unsetCursor()
        if linea is not None:
            r = linea.rect
            rect = QRectF(r.x0 * escala, r.y0 * escala, r.width * escala, r.height * escala)
            texto, tamano = linea.texto, linea.tamano
            fuente_pdf = "helv" if linea.invisible else linea.fuente

            def terminar(nuevo):
                self._editor = None
                if nuevo is not None and nuevo != texto:
                    self.doc.cambiar_linea(n, linea, nuevo)
                    self.documento_cambiado()
        else:
            tamano = TAMANO_TEXTO_NUEVO
            fuente_pdf = "helv"
            x, y = self.doc.donde_escribir(n, p.x(), p.y(), tamano)
            rect = QRectF(x * escala, y * escala, 0, tamano * escala)
            texto = ""

            def terminar(nuevo):
                self._editor = None
                if nuevo:
                    self.doc.escribir(n, x, y, nuevo, tamano)
                    self.documento_cambiado()

        self._editor = EditorEnLinea(pagina, rect, texto, tamano * escala, terminar, fuente_pdf)

    # --- Formularios --------------------------------------------------------
    def rellenar_en(self, pagina: PaginaWidget, p) -> bool:
        """Clic en modo lectura sobre un campo: rellenarlo. Devuelve True si había campo."""
        if self.doc is None or self._editor is not None:
            return False
        n = pagina.indice
        campo = self.doc.campo_en(n, *p)
        if campo is None or campo.tipo == "otro":
            return False
        if campo.tipo == "casilla":
            self.doc.rellenar_campo(n, campo.xref, not campo.marcado)
            self.documento_cambiado()
            return True
        if campo.tipo == "multilinea":
            texto, ok = QInputDialog.getMultiLineText(self, campo.nombre, "Escribe el texto:", str(campo.valor))
            if ok and texto != campo.valor:
                self.doc.rellenar_campo(n, campo.xref, texto)
                self.documento_cambiado()
            return True
        escala, r = self.escala, campo.rect
        rect = QRectF(r.x0 * escala, r.y0 * escala, r.width * escala, r.height * escala)
        tamano = min(11, r.height * 0.7)

        def terminar(nuevo):
            self._editor = None
            if nuevo is not None and nuevo != campo.valor:
                self.doc.rellenar_campo(n, campo.xref, nuevo)
                self.documento_cambiado()

        self._editor = EditorEnLinea(pagina, rect, str(campo.valor), tamano * escala, terminar)
        return True

    def pedir_nombre_campo(self, n, campo):
        nombre, ok = QInputDialog.getText(self, "Nombre del campo", "Nombre:", text=campo.nombre)
        if not ok or nombre.strip() == campo.nombre:
            return
        try:
            self.formulario.renombrar(n, campo, nombre.strip())
        except ValueError as error:
            QMessageBox.warning(self, "Nombre del campo", str(error))

    def borrar_seleccion(self):
        if self.modo == "dibujar":
            self.dibujo.borrar_seleccion()
            return
        if self.modo == "formulario":
            self.formulario.borrar_seleccion()
            return
        if self.doc is None or not self._seleccion:
            return
        self.doc.borrar_palabras_elegidas(*self._seleccion)
        self.documento_cambiado()

    def documento_cambiado(self, conservar_dibujo: bool = False):
        """El contenido de la página ha cambiado: volver a dibujar."""
        if not conservar_dibujo:
            self.dibujo.cancelar()
            self.formulario.cancelar()
        self._cache.clear()
        self._seleccion = self._ancla = self._caja = None
        self._resultados, self._activo = [], -1
        self._repintar()
        self.documentoEditado.emit()

    def texto_actualizado(self):
        """Tras el OCR: la imagen no cambia, pero sí el texto que se puede seleccionar."""
        self._seleccion = self._ancla = self._caja = None
        for w in self._paginas:
            w.update()

    def _repintar(self):
        for w in self._paginas:
            w.update()
