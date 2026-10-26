"""Ventana principal del lector."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEventLoop, QPoint, QRect, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QImage, QIntValidator, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QProgressDialog,
    QMessageBox,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStackedWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .dialogo_ocr import HiloOCR, asegurar_idiomas, elegir_paginas
from .documento import ContrasenaNecesaria, Documento
from .impresion import imprimir
from .visor import VisorPDF

MAX_RECIENTES = 8
ANCHO_MINIATURA = 110


def icono(nombre: str) -> QIcon:
    return QIcon.fromTheme(getattr(QIcon.ThemeIcon, nombre))


class DelegadoMiniatura(QStyledItemDelegate):
    """Dibuja la miniatura centrada con el número de página debajo."""

    ALTO = int(ANCHO_MINIATURA * 1.42)

    def sizeHint(self, _opcion, _indice):
        return QSize(ANCHO_MINIATURA + 20, self.ALTO + 34)

    def paint(self, p: QPainter, opcion, indice):
        r = opcion.rect
        seleccionada = bool(opcion.state & QStyle.StateFlag.State_Selected)
        if seleccionada:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#f6d9d7"))
            p.drawRoundedRect(r.adjusted(4, 2, -4, -2), 6, 6)
        icono_pag: QIcon = indice.data(Qt.ItemDataRole.DecorationRole)
        caja = QRect(r.x() + (r.width() - ANCHO_MINIATURA) // 2, r.y() + 6, ANCHO_MINIATURA, self.ALTO)
        if icono_pag and not icono_pag.isNull():
            pix = icono_pag.pixmap(caja.size(), opcion.widget.devicePixelRatioF() if opcion.widget else 1.0)
            tam = pix.deviceIndependentSize().toSize()
            caja = QRect(caja.x(), caja.y(), tam.width(), tam.height())
            p.drawPixmap(caja, pix)
        else:
            p.fillRect(caja, Qt.GlobalColor.white)
        p.setPen(QColor("#c4302b") if seleccionada else QColor("#c9c9d0"))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(caja.adjusted(0, 0, -1, -1))
        p.setPen(QColor("#c4302b") if seleccionada else QColor("#55555c"))
        p.drawText(QRect(r.x(), caja.bottom() + 4, r.width(), 20), Qt.AlignmentFlag.AlignHCenter, indice.data())


class ListaMiniaturas(QListWidget):
    """Columna de miniaturas: se pueden arrastrar para reordenar las páginas."""

    paginaSoltada = Signal(int, int)  # página movida, delante de qué página
    borrarPulsado = Signal()
    menuPedido = Signal(QPoint)

    def __init__(self):
        super().__init__()
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDropIndicatorShown(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda pos: self.menuPedido.emit(self.mapToGlobal(pos)))

    def dropEvent(self, e):
        # No dejamos que la lista mueva sus elementos: movemos la página en el PDF y la lista se rehace
        desde = self.currentRow()
        destino = self.indexAt(e.position().toPoint())
        if not destino.isValid():
            antes_de = self.count()
        else:
            fila = destino.row()
            rect = self.visualRect(destino)
            antes_de = fila + 1 if e.position().y() > rect.center().y() else fila
        e.setDropAction(Qt.DropAction.IgnoreAction)
        e.accept()
        if desde >= 0:
            self.paginaSoltada.emit(desde, antes_de)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.borrarPulsado.emit()
        else:
            super().keyPressEvent(e)


class Bienvenida(QWidget):
    """Pantalla inicial cuando no hay ningún PDF abierto."""

    def __init__(self, ventana: "VentanaPrincipal"):
        super().__init__()
        self.setObjectName("bienvenida")
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titulo = QLabel("PDF Casero")
        titulo.setObjectName("tituloBienvenida")
        texto = QLabel("Abre un PDF o arrástralo a esta ventana")
        texto.setObjectName("textoBienvenida")
        boton = QToolButton()
        boton.setText("Abrir PDF…")
        boton.setObjectName("botonPrincipal")
        boton.clicked.connect(ventana.abrir_dialogo)
        self.lista = QListWidget()
        self.lista.setObjectName("recientes")
        self.lista.setMaximumWidth(520)
        self.lista.itemActivated.connect(lambda it: ventana.abrir(it.data(Qt.ItemDataRole.UserRole)))
        self.etiqueta_recientes = QLabel("Abiertos recientemente")
        self.etiqueta_recientes.setObjectName("textoBienvenida")
        for w in (titulo, texto, boton, self.etiqueta_recientes, self.lista):
            lay.addWidget(w, 0, Qt.AlignmentFlag.AlignHCenter)

    def actualizar(self, recientes: list[str]):
        self.lista.clear()
        for ruta in recientes:
            it = QListWidgetItem(Path(ruta).name)
            it.setToolTip(ruta)
            it.setData(Qt.ItemDataRole.UserRole, ruta)
            self.lista.addItem(it)
        self.lista.setVisible(bool(recientes))
        self.etiqueta_recientes.setVisible(bool(recientes))


class VentanaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ajustes = QSettings("PDFCasero", "PDFCasero")
        self.doc: Documento | None = None
        self._resultados = []
        self._activo = -1
        self._texto_buscado = ""

        self.setWindowTitle("PDF Casero")
        self.setAcceptDrops(True)
        self.resize(1200, 850)

        self.visor = VisorPDF()
        self.miniaturas = ListaMiniaturas()
        self.miniaturas.setObjectName("miniaturas")
        self.miniaturas.setItemDelegate(DelegadoMiniatura(self.miniaturas))
        self.miniaturas.setUniformItemSizes(True)
        self.miniaturas.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.miniaturas.setFixedWidth(ANCHO_MINIATURA + 48)
        self.miniaturas.currentRowChanged.connect(self._miniatura_elegida)
        self.miniaturas.paginaSoltada.connect(self._pagina_soltada)
        self.miniaturas.borrarPulsado.connect(self.borrar_paginas_elegidas)
        self.miniaturas.menuPedido.connect(self._menu_paginas)
        self._cola_miniaturas: list[int] = []
        self._temporizador_mini = QTimer(self, interval=0)
        self._temporizador_mini.timeout.connect(self._generar_miniatura)

        divisor = QWidget()
        lay = QHBoxLayout(divisor)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        izquierda = QVBoxLayout()
        izquierda.setContentsMargins(0, 0, 0, 0)
        izquierda.setSpacing(0)
        self.boton_paginas = QToolButton()
        self.boton_paginas.setObjectName("botonPaginas")
        self.boton_paginas.setText("Páginas")
        self.boton_paginas.setToolTip("Añadir, quitar, girar o duplicar páginas. Arrastra las miniaturas para reordenar.")
        self.boton_paginas.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.boton_paginas.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.boton_paginas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        izquierda.addWidget(self.boton_paginas)
        izquierda.addWidget(self.miniaturas)
        lay.addLayout(izquierda)
        derecha = QVBoxLayout()
        derecha.setContentsMargins(0, 0, 0, 0)
        derecha.setSpacing(0)
        self.aviso_escaneado = self._crear_aviso_escaneado()
        derecha.addWidget(self.aviso_escaneado)
        derecha.addWidget(self.visor, 1)
        lay.addLayout(derecha, 1)

        self.bienvenida = Bienvenida(self)
        self.pila = QStackedWidget()
        self.pila.addWidget(self.bienvenida)
        self.pila.addWidget(divisor)
        self.setCentralWidget(self.pila)

        self._crear_acciones()
        self._crear_barra()
        self._crear_barra_dibujo()
        self.visor.paginaCambiada.connect(self._pagina_cambiada)
        self.visor.zoomCambiado.connect(self._zoom_cambiado)
        self.visor.documentoEditado.connect(self._documento_editado)
        self.statusBar().showMessage("Listo")
        self.bienvenida.actualizar(self.recientes())
        self._actualizar_estado()

        geom = self.ajustes.value("geometria")
        if geom is not None:
            self.restoreGeometry(geom)

    # --- Interfaz ---------------------------------------------------------
    def _accion(self, texto, icono_nombre, atajo, funcion, consejo=None):
        a = QAction(icono(icono_nombre) if icono_nombre else QIcon(), texto, self)
        if atajo:
            a.setShortcuts(atajo if isinstance(atajo, list) else [atajo])
        a.setToolTip(consejo or texto)
        a.triggered.connect(funcion)
        self.addAction(a)
        return a

    def _crear_acciones(self):
        S = QKeySequence.StandardKey
        self.acc_abrir = self._accion("Abrir", "DocumentOpen", S.Open, self.abrir_dialogo, "Abrir un PDF (Ctrl+O)")
        self.acc_guardar = self._accion("Guardar", "DocumentSave", S.Save, self.guardar, "Guardar (Ctrl+S)")
        self.acc_guardar_como = self._accion(
            "Guardar como", "DocumentSaveAs", QKeySequence("Ctrl+Shift+S"), self.guardar_como,
            "Guardar una copia con otro nombre (Ctrl+Mayús+S)",
        )
        self.acc_editar = self._accion(
            "Editar texto", None, QKeySequence("Ctrl+T"), self._cambiar_modo_edicion,
            "Cambiar, borrar o escribir texto (Ctrl+T)",
        )
        self.acc_editar.setCheckable(True)
        self.acc_dibujar = self._accion(
            "Dibujar", None, QKeySequence("Ctrl+D"), self._cambiar_modo_dibujo,
            "Flechas, líneas, formas, globos, texto y lápiz (Ctrl+D)",
        )
        self.acc_dibujar.setCheckable(True)
        self.acc_deshacer = self._accion("↶", None, S.Undo, self.deshacer, "Deshacer (Ctrl+Z)")
        self.acc_rehacer = self._accion("↷", None, [QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")], self.rehacer, "Rehacer (Ctrl+Y)")
        self.acc_ocr = self._accion(
            "Hacer editable", None, QKeySequence("Ctrl+E"), self.hacer_editable,
            "Reconocer el texto de un PDF escaneado para poder buscarlo y copiarlo (Ctrl+E)",
        )
        self.acc_imprimir = self._accion("Imprimir", "DocumentPrint", S.Print, self._imprimir, "Imprimir (Ctrl+P)")
        self.acc_anterior = self._accion("◀", None, [], self.visor.pagina_anterior, "Página anterior")
        self.acc_siguiente = self._accion("▶", None, [], self.visor.pagina_siguiente, "Página siguiente")
        self.acc_alejar = self._accion("−", None, S.ZoomOut, self.visor.alejar, "Alejar (Ctrl -)")
        self.acc_acercar = self._accion(
            "+", None, [QKeySequence("Ctrl++"), QKeySequence("Ctrl+=")], self.visor.acercar, "Acercar (Ctrl +)"
        )
        self.acc_ancho = self._accion(
            "Ajustar al ancho", "ZoomFitBest", QKeySequence("Ctrl+0"), self.visor.zoom_ajustar_ancho,
            "Ajustar al ancho de la ventana (Ctrl+0)",
        )
        self.acc_completa = self._accion(
            "Ver página completa", "ZoomFitBest", QKeySequence("Ctrl+1"), self.visor.zoom_pagina_completa,
            "Ver la página completa (Ctrl+1)",
        )
        self.acc_buscar = self._accion("Buscar", "EditFind", S.Find, self._enfocar_busqueda, "Buscar (Ctrl+F)")
        self.acc_cerrar = self._accion("Cerrar", "WindowClose", S.Close, self.cerrar_documento, "Cerrar PDF (Ctrl+W)")
        self.acc_pantalla = self._accion("Pantalla completa", "ViewFullscreen", QKeySequence("F11"), self._pantalla_completa)
        self.acc_acerca = self._accion("Acerca de", "HelpAbout", [], self._acerca_de)
        for a, teclas in ((self.acc_siguiente, ["Ctrl+Right"]), (self.acc_anterior, ["Ctrl+Left"])):
            a.setShortcuts([QKeySequence(t) for t in teclas])
        self._acciones_doc = [
            self.acc_guardar, self.acc_guardar_como, self.acc_imprimir, self.acc_ocr, self.acc_editar, self.acc_dibujar, self.acc_anterior, self.acc_siguiente, self.acc_alejar, self.acc_acercar,
            self.acc_ancho, self.acc_completa, self.acc_buscar, self.acc_cerrar,
        ]

    def _crear_barra(self):
        barra = QToolBar("Principal")
        barra.setObjectName("barraPrincipal")
        barra.setMovable(False)
        barra.setIconSize(QSize(20, 20))
        barra.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(barra)

        barra.addAction(self.acc_abrir)
        barra.addAction(self.acc_guardar)
        barra.addSeparator()
        barra.addAction(self.acc_ocr)
        barra.addAction(self.acc_editar)
        barra.addAction(self.acc_dibujar)
        barra.addAction(self.acc_deshacer)
        barra.addAction(self.acc_rehacer)
        barra.addSeparator()
        barra.addAction(self.acc_anterior)
        self.campo_pagina = QLineEdit("")
        self.campo_pagina.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.campo_pagina.setFixedWidth(56)
        self.campo_pagina.setToolTip("Escribe un número de página y pulsa Intro")
        self.campo_pagina.returnPressed.connect(self._ir_a_pagina_escrita)
        barra.addWidget(self.campo_pagina)
        self.etiqueta_total = QLabel(" de 0 ")
        barra.addWidget(self.etiqueta_total)
        barra.addAction(self.acc_siguiente)
        barra.addSeparator()
        barra.addAction(self.acc_alejar)
        self.etiqueta_zoom = QLabel("100 %")
        self.etiqueta_zoom.setFixedWidth(52)
        self.etiqueta_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        barra.addWidget(self.etiqueta_zoom)
        barra.addAction(self.acc_acercar)

        espacio = QWidget()
        espacio.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        barra.addWidget(espacio)

        self.campo_buscar = QLineEdit()
        self.campo_buscar.setPlaceholderText("Buscar en el documento…")
        self.campo_buscar.setClearButtonEnabled(True)
        self.campo_buscar.setMinimumWidth(160)
        self.campo_buscar.setMaximumWidth(220)
        self.campo_buscar.returnPressed.connect(self._buscar_siguiente)
        self.campo_buscar.textChanged.connect(self._texto_busqueda_cambiado)
        barra.addWidget(self.campo_buscar)
        self.etiqueta_resultados = QLabel("")
        self.etiqueta_resultados.setMinimumWidth(70)
        barra.addWidget(self.etiqueta_resultados)
        self.acc_res_ant = self._accion("▲", None, QKeySequence("Shift+F3"), self._buscar_anterior, "Resultado anterior")
        self.acc_res_sig = self._accion("▼", None, QKeySequence("F3"), self._buscar_siguiente, "Resultado siguiente")
        barra.addAction(self.acc_res_ant)
        barra.addAction(self.acc_res_sig)
        self._acciones_doc += [self.acc_res_ant, self.acc_res_sig]
        barra.addSeparator()
        # Lo que se usa menos va en un menú para que la barra quepa en pantallas pequeñas
        menu = QMenu(self)
        for a in (self.acc_guardar_como, self.acc_imprimir, self.acc_ancho, self.acc_completa, self.acc_cerrar, self.acc_pantalla, self.acc_acerca):
            menu.addAction(a)
        self.menu_paginas = self._crear_menu_paginas()
        self.boton_paginas.setMenu(self.menu_paginas)
        menu.insertMenu(menu.actions()[0], self.menu_paginas)
        menu.insertSeparator(menu.actions()[1])
        boton_mas = QToolButton()
        boton_mas.setText("Más")
        boton_mas.setToolTip("Más opciones")
        boton_mas.setMenu(menu)
        boton_mas.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        barra.addWidget(boton_mas)

    def _actualizar_estado(self):
        hay = self.doc is not None
        for a in self._acciones_doc:
            a.setEnabled(hay)
        self.campo_pagina.setEnabled(hay)
        self.campo_buscar.setEnabled(hay)
        self.pila.setCurrentIndex(1 if hay else 0)
        if hay:
            self.campo_pagina.setValidator(QIntValidator(1, self.doc.num_paginas, self))
            self.etiqueta_total.setText(f" de {self.doc.num_paginas} ")
            self.acc_deshacer.setEnabled(self.doc.puede_deshacer)
            self.acc_rehacer.setEnabled(self.doc.puede_rehacer)
            marca = "● " if self.doc.modificado else ""
            self.setWindowTitle(f"{marca}{self.doc.titulo} – PDF Casero")
        else:
            self.acc_deshacer.setEnabled(False)
            self.acc_rehacer.setEnabled(False)
            for accion in (self.acc_editar, self.acc_dibujar):
                if accion.isChecked():
                    accion.setChecked(False)
            self._poner_modo("leer")
            self.etiqueta_total.setText(" de 0 ")
            self.campo_pagina.setText("")
            self.setWindowTitle("PDF Casero")
            self.bienvenida.actualizar(self.recientes())

    # --- Abrir y cerrar ---------------------------------------------------
    def abrir_dialogo(self):
        carpeta = self.ajustes.value("ultima_carpeta", str(Path.home()))
        ruta, _ = QFileDialog.getOpenFileName(self, "Abrir PDF", carpeta, "Documentos PDF (*.pdf);;Todos (*)")
        if ruta:
            self.abrir(ruta)

    def abrir(self, ruta: str) -> bool:
        ruta = str(Path(ruta))
        if not Path(ruta).exists():
            QMessageBox.warning(self, "No se encuentra", f"El archivo ya no existe:\n{ruta}")
            self._quitar_reciente(ruta)
            return False
        contrasena = None
        while True:
            try:
                doc = Documento(ruta, contrasena)
                break
            except ContrasenaNecesaria:
                texto = "Este PDF está protegido. Escribe la contraseña:" if contrasena is None else "Contraseña incorrecta. Inténtalo otra vez:"
                contrasena, ok = QInputDialog.getText(self, "Contraseña", texto, QLineEdit.EchoMode.Password)
                if not ok:
                    return False
            except Exception as e:  # PDF dañado o no es un PDF
                QMessageBox.critical(self, "No se pudo abrir", f"No se pudo abrir el archivo:\n{ruta}\n\n{e}")
                return False

        if not self.cerrar_documento():
            doc.cerrar()
            return False
        self.doc = doc
        self._actualizar_estado()
        self.visor.cargar(doc)
        self._preparar_miniaturas()
        self.aviso_escaneado.setVisible(bool(doc.paginas_sin_texto()))
        self._anadir_reciente(ruta)
        self.ajustes.setValue("ultima_carpeta", str(Path(ruta).parent))
        self.statusBar().showMessage(f"{Path(ruta).name} · {doc.num_paginas} páginas", 5000)
        return True

    def cerrar_documento(self) -> bool:
        """Cierra el PDF. Devuelve False si el usuario cancela por tener cambios sin guardar."""
        if not self._confirmar_cambios():
            return False
        self._temporizador_mini.stop()
        self.miniaturas.clear()
        self.visor.cargar(None)
        self._limpiar_busqueda()
        if self.doc:
            self.doc.cerrar()
            self.doc = None
        self._actualizar_estado()
        return True

    # --- Guardar ----------------------------------------------------------
    def guardar(self) -> bool:
        if not self.doc:
            return False
        if not self.doc.modificado:
            self.statusBar().showMessage("No hay cambios que guardar", 4000)
            return True
        return self._guardar_en(None)

    def guardar_como(self) -> bool:
        if not self.doc:
            return False
        sugerido = str(self.doc.ruta.with_name(self.doc.ruta.stem + " (copia).pdf"))
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar como", sugerido, "Documentos PDF (*.pdf)")
        if not ruta:
            return False
        if not ruta.lower().endswith(".pdf"):
            ruta += ".pdf"
        if self._guardar_en(ruta):
            self._anadir_reciente(str(self.doc.ruta))
            return True
        return False

    def _guardar_en(self, ruta) -> bool:
        try:
            destino = self.doc.guardar(ruta)
        except Exception as e:
            QMessageBox.critical(self, "No se pudo guardar", f"No se pudo guardar el archivo.\n\n{e}")
            return False
        self._actualizar_estado()
        self.statusBar().showMessage(f"Guardado en {destino}", 5000)
        return True

    def _confirmar_cambios(self) -> bool:
        if not self.doc or not self.doc.modificado:
            return True
        r = QMessageBox.question(
            self, "Cambios sin guardar", f"¿Quieres guardar los cambios en «{self.doc.ruta.name}»?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if r == QMessageBox.StandardButton.Save:
            return self.guardar()
        return r == QMessageBox.StandardButton.Discard

    # --- Recientes --------------------------------------------------------
    def recientes(self) -> list[str]:
        valor = self.ajustes.value("recientes", [])
        if isinstance(valor, str):
            valor = [valor]
        return [r for r in (valor or []) if r]

    def _anadir_reciente(self, ruta):
        lista = [r for r in self.recientes() if r != ruta]
        self.ajustes.setValue("recientes", [ruta] + lista[: MAX_RECIENTES - 1])

    def _quitar_reciente(self, ruta):
        self.ajustes.setValue("recientes", [r for r in self.recientes() if r != ruta])
        self.bienvenida.actualizar(self.recientes())

    # --- Miniaturas -------------------------------------------------------
    def _preparar_miniaturas(self):
        self.miniaturas.blockSignals(True)
        self.miniaturas.clear()
        for i in range(self.doc.num_paginas):
            it = QListWidgetItem(str(i + 1))
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.miniaturas.addItem(it)
        self.miniaturas.setCurrentRow(0)
        self.miniaturas.blockSignals(False)
        self._cola_miniaturas = list(range(self.doc.num_paginas))
        self._temporizador_mini.start()

    def _generar_miniatura(self):
        if not self.doc or not self._cola_miniaturas:
            self._temporizador_mini.stop()
            return
        i = self._cola_miniaturas.pop(0)
        an, _ = self.doc.tamano_pagina(i)
        dpr = self.devicePixelRatioF()
        datos, w, h, paso = self.doc.renderizar(i, ANCHO_MINIATURA * dpr / an)
        img = QImage(datos, w, h, paso, QImage.Format.Format_RGB888).copy()
        img.setDevicePixelRatio(dpr)
        self.miniaturas.item(i).setIcon(QIcon(QPixmap.fromImage(img)))

    def _miniatura_elegida(self, fila):
        if fila >= 0 and fila != self.visor.pagina_actual:
            self.visor.ir_a_pagina(fila)

    # --- Eventos del visor ------------------------------------------------
    def _pagina_cambiada(self, i):
        self.campo_pagina.setText(str(i + 1))
        self.miniaturas.blockSignals(True)
        self.miniaturas.setCurrentRow(i)
        self.miniaturas.blockSignals(False)
        # Las páginas aún sin miniatura que se están viendo pasan delante en la cola
        if i in self._cola_miniaturas:
            self._cola_miniaturas.remove(i)
            self._cola_miniaturas.insert(0, i)

    def _ir_a_pagina_escrita(self):
        if self.campo_pagina.text().isdigit():
            self.visor.ir_a_pagina(int(self.campo_pagina.text()) - 1)
        self.visor.setFocus()

    def _zoom_cambiado(self, z):
        self.etiqueta_zoom.setText(f"{round(z * 100)} %")

    # --- Búsqueda ---------------------------------------------------------
    def _enfocar_busqueda(self):
        self.campo_buscar.setFocus()
        self.campo_buscar.selectAll()

    def _texto_busqueda_cambiado(self, texto):
        if not texto:
            self._limpiar_busqueda()

    def _limpiar_busqueda(self):
        self._resultados, self._activo, self._texto_buscado = [], -1, ""
        self.etiqueta_resultados.setText("")
        self.visor.mostrar_resultados([], -1)

    def _ejecutar_busqueda(self) -> bool:
        texto = self.campo_buscar.text().strip()
        if not self.doc or not texto:
            return False
        if texto != self._texto_buscado:
            self._texto_buscado = texto
            self._resultados = self.doc.buscar(texto)
            self._activo = -1
            if not self._resultados:
                self.etiqueta_resultados.setText("Sin resultados")
                self.visor.mostrar_resultados([], -1)
                return False
        return bool(self._resultados)

    def _buscar_siguiente(self):
        if self._ejecutar_busqueda():
            self._mover_resultado(+1)

    def _buscar_anterior(self):
        if self._ejecutar_busqueda():
            self._mover_resultado(-1)

    def _mover_resultado(self, paso):
        n = len(self._resultados)
        if self._activo < 0:
            # Empezar por el primer resultado desde la página actual
            actual = self.visor.pagina_actual
            candidatos = [k for k, r in enumerate(self._resultados) if r.pagina >= actual]
            self._activo = candidatos[0] if candidatos else 0
        else:
            self._activo = (self._activo + paso) % n
        self.etiqueta_resultados.setText(f"{self._activo + 1} de {n}")
        self.visor.mostrar_resultados(self._resultados, self._activo)

    # --- Editar texto ----------------------------------------------------
    def _cambiar_modo_edicion(self, activo: bool):
        if activo:
            self.acc_dibujar.setChecked(False)
        self._poner_modo("editar" if activo else "leer")

    def _cambiar_modo_dibujo(self, activo: bool):
        if activo:
            self.acc_editar.setChecked(False)
        self._poner_modo("dibujar" if activo else "leer")

    def _poner_modo(self, modo: str):
        self.visor.set_modo(modo)
        self.barra_dibujo.setVisible(modo == "dibujar")
        mensajes = {
            "editar": "Editar texto: haz clic en una línea para cambiarla (déjala vacía para borrarla) o en un hueco "
            "para escribir. Intro acepta, Esc cancela.",
            "dibujar": "Dibujar: elige herramienta y arrastra. Con Seleccionar mueves, estiras (cuadraditos), "
            "cambias color o borras (Supr). Doble clic cambia el texto de un globo.",
        }
        if modo in mensajes:
            self.statusBar().showMessage(mensajes[modo])
        else:
            self.statusBar().clearMessage()

    # --- Barra de dibujo ---------------------------------------------------
    COLORES = (
        ("Rojo", (0.85, 0.1, 0.1)),
        ("Azul", (0.1, 0.35, 0.85)),
        ("Verde", (0.1, 0.6, 0.2)),
        ("Naranja", (0.95, 0.55, 0.0)),
        ("Morado", (0.5, 0.2, 0.7)),
        ("Negro", (0.0, 0.0, 0.0)),
    )
    GROSORES = (("Fino", 1.0), ("Normal", 2.0), ("Grueso", 4.0), ("Muy grueso", 7.0))
    HERRAMIENTAS = (
        ("seleccionar", "Seleccionar", "Seleccionar, mover y estirar dibujos"),
        ("flecha", "Flecha", "Arrastra desde el inicio hasta la punta"),
        ("linea", "Línea", "Arrastra para trazar una línea"),
        ("rect", "Rectángulo", "Arrastra de una esquina a la otra"),
        ("elipse", "Círculo", "Arrastra para dibujar un círculo o elipse"),
        ("globo", "Globo", "Arrastra desde lo que quieres señalar hasta donde irá el globo"),
        ("texto", "Texto", "Haz clic donde quieras escribir"),
        ("lapiz", "Lápiz", "Dibuja a mano alzada"),
    )

    def _crear_barra_dibujo(self):
        barra = QToolBar("Dibujo")
        barra.setObjectName("barraDibujo")
        barra.setMovable(False)
        self.addToolBarBreak()
        self.addToolBar(barra)
        control = self.visor.dibujo

        grupo = QActionGroup(self)
        self._acciones_herramienta = {}
        for clave, texto, consejo in self.HERRAMIENTAS:
            a = QAction(texto, self, checkable=True)
            a.setToolTip(consejo)
            a.triggered.connect(lambda _=False, c=clave: self._elegir_herramienta(c))
            grupo.addAction(a)
            barra.addAction(a)
            self._acciones_herramienta[clave] = a
        self._acciones_herramienta["seleccionar"].setChecked(True)
        barra.addSeparator()

        grupo_color = QActionGroup(self)
        self._acciones_color = []
        for nombre, rgb in self.COLORES:
            pix = QPixmap(18, 18)
            pix.fill(QColor.fromRgbF(*rgb))
            a = QAction(QIcon(pix), "", self, checkable=True)
            a.setToolTip(nombre)
            a.triggered.connect(lambda _=False, c=rgb: control.aplicar_estilo(color=c))
            grupo_color.addAction(a)
            barra.addAction(a)
            self._acciones_color.append((rgb, a))
        self._acciones_color[0][1].setChecked(True)
        barra.addSeparator()

        self.combo_grosor = QComboBox()
        for nombre, valor in self.GROSORES:
            self.combo_grosor.addItem(nombre, valor)
        self.combo_grosor.setCurrentIndex(1)
        self.combo_grosor.setToolTip("Grosor de la línea")
        self.combo_grosor.activated.connect(
            lambda i: control.aplicar_estilo(grosor=self.combo_grosor.itemData(i))
        )
        barra.addWidget(self.combo_grosor)
        self.acc_relleno = QAction("Relleno", self, checkable=True)
        self.acc_relleno.setToolTip("Rellenar rectángulos y círculos con un color suave")
        self.acc_relleno.triggered.connect(lambda v: control.aplicar_estilo(relleno=v))
        barra.addAction(self.acc_relleno)
        barra.addSeparator()
        self.acc_borrar_dibujo = QAction("Borrar dibujo", self)
        self.acc_borrar_dibujo.setToolTip("Borrar el dibujo seleccionado (Supr)")
        self.acc_borrar_dibujo.triggered.connect(control.borrar_seleccion)
        self.acc_borrar_dibujo.setEnabled(False)
        barra.addAction(self.acc_borrar_dibujo)
        control.al_cambiar_seleccion = self._dibujo_seleccionado
        barra.hide()
        self.barra_dibujo = barra

    def _elegir_herramienta(self, clave):
        self.visor.dibujo.herramienta = clave
        if clave != "seleccionar":
            self.visor.dibujo.seleccionar(None)

    def _dibujo_seleccionado(self, d):
        """Al seleccionar un dibujo, la barra muestra su color y su grosor."""
        self.acc_borrar_dibujo.setEnabled(d is not None)
        if d is None:
            return
        control = self.visor.dibujo
        control.color, control.grosor, control.relleno = d.color, d.grosor, d.relleno
        for rgb, a in self._acciones_color:
            if all(abs(x - y) < 0.02 for x, y in zip(rgb, d.color)):
                a.setChecked(True)
        indice = min(range(len(self.GROSORES)), key=lambda i: abs(self.GROSORES[i][1] - d.grosor))
        self.combo_grosor.setCurrentIndex(indice)
        self.acc_relleno.setChecked(d.relleno)

    def _documento_editado(self):
        self._texto_buscado = ""
        self._resultados, self._activo = [], -1
        self.etiqueta_resultados.setText("")
        self._actualizar_estado()
        self._regenerar_miniatura()

    def _regenerar_miniatura(self, n=None):
        paginas = range(self.doc.num_paginas) if n is None else [n]
        for i in paginas:
            if i not in self._cola_miniaturas:
                self._cola_miniaturas.insert(0, i)
        self._temporizador_mini.start()

    def deshacer(self):
        if self.doc and self.doc.deshacer():
            self._estructura_cambiada(self.visor.pagina_actual)

    def rehacer(self):
        if self.doc and self.doc.rehacer():
            self._estructura_cambiada(self.visor.pagina_actual)

    # --- Organizar páginas --------------------------------------------------
    def _crear_menu_paginas(self) -> QMenu:
        menu = QMenu("Páginas", self)
        menu.addAction("Insertar página en blanco antes", lambda: self.insertar_en_blanco(despues=False))
        menu.addAction("Insertar página en blanco después", lambda: self.insertar_en_blanco(despues=True))
        menu.addAction("Insertar PDF o imagen después…", self.insertar_archivo)
        menu.addSeparator()
        menu.addAction("Duplicar página", self.duplicar_pagina)
        menu.addAction("Girar a la derecha", lambda: self.girar_pagina(90))
        menu.addAction("Girar a la izquierda", lambda: self.girar_pagina(-90))
        menu.addSeparator()
        menu.addAction("Borrar página(s)", self.borrar_paginas_elegidas)
        return menu

    def _menu_paginas(self, posicion):
        if self.doc:
            self._crear_menu_paginas().exec(posicion)

    def _paginas_elegidas(self) -> list[int]:
        filas = sorted(self.miniaturas.row(it) for it in self.miniaturas.selectedItems())
        return filas or [self.visor.pagina_actual]

    def _estructura_cambiada(self, ir_a: int):
        """Han cambiado las páginas (cuántas o su orden): rehacer la vista y las miniaturas."""
        ir_a = max(0, min(ir_a, self.doc.num_paginas - 1))
        self._limpiar_busqueda()
        self.visor.cargar(self.doc)
        self._preparar_miniaturas()
        self._actualizar_estado()
        QTimer.singleShot(0, lambda: self.visor.ir_a_pagina(ir_a))
        self.miniaturas.setCurrentRow(ir_a)

    def insertar_en_blanco(self, despues=True):
        if not self.doc:
            return
        n = self.visor.pagina_actual + (1 if despues else 0)
        self._estructura_cambiada(self.doc.insertar_en_blanco(n))
        self.statusBar().showMessage(
            f"Página en blanco añadida (página {n + 1}). Puedes escribir en ella con Editar texto o hacer un esquema con Dibujar.",
            8000,
        )

    def insertar_archivo(self):
        if not self.doc:
            return
        carpeta = self.ajustes.value("ultima_carpeta", str(Path.home()))
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Insertar PDF o imagen", carpeta, "PDF e imágenes (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp);;Todos (*)"
        )
        if not ruta:
            return
        n = self.visor.pagina_actual + 1
        contrasena = None
        while True:
            try:
                cuantas = self.doc.insertar_archivo(n, ruta, contrasena)
                break
            except ContrasenaNecesaria:
                contrasena, ok = QInputDialog.getText(
                    self, "Contraseña", "Ese PDF está protegido. Escribe la contraseña:", QLineEdit.EchoMode.Password
                )
                if not ok:
                    return
            except Exception as e:
                QMessageBox.critical(self, "No se pudo insertar", f"No se pudo insertar el archivo:\n{ruta}\n\n{e}")
                return
        self._estructura_cambiada(n)
        self.statusBar().showMessage(f"{cuantas} página(s) de {Path(ruta).name} añadidas después de la página {n}.", 8000)

    def duplicar_pagina(self):
        if self.doc:
            self._estructura_cambiada(self.doc.duplicar_pagina(self.visor.pagina_actual))

    def girar_pagina(self, grados):
        if not self.doc:
            return
        paginas = self._paginas_elegidas()
        for n in paginas:
            self.doc.girar_pagina(n, grados)
        self._estructura_cambiada(paginas[0])

    def borrar_paginas_elegidas(self):
        if not self.doc:
            return
        paginas = self._paginas_elegidas()
        if len(paginas) >= self.doc.num_paginas:
            QMessageBox.information(self, "No se puede", "Un PDF tiene que tener al menos una página.")
            return
        texto = f"la página {paginas[0] + 1}" if len(paginas) == 1 else f"{len(paginas)} páginas"
        r = QMessageBox.question(self, "Borrar páginas", f"¿Borrar {texto}? Puedes deshacerlo con Ctrl+Z.")
        if r == QMessageBox.StandardButton.Yes:
            self.doc.borrar_paginas(paginas)
            self._estructura_cambiada(paginas[0])

    def _pagina_soltada(self, desde, antes_de):
        if self.doc:
            nueva = self.doc.mover_pagina(desde, antes_de)
            if nueva != desde:
                self._estructura_cambiada(nueva)

    # --- OCR: hacer editable ---------------------------------------------
    def _crear_aviso_escaneado(self) -> QFrame:
        aviso = QFrame()
        aviso.setObjectName("avisoEscaneado")
        lay = QHBoxLayout(aviso)
        lay.setContentsMargins(16, 8, 12, 8)
        texto = QLabel("Este PDF parece escaneado: su texto todavía no se puede buscar ni copiar.")
        boton = QToolButton()
        boton.setText("Hacer editable")
        boton.setObjectName("botonAviso")
        boton.clicked.connect(self.hacer_editable)
        cerrar = QToolButton()
        cerrar.setText("✕")
        cerrar.setToolTip("Ocultar")
        cerrar.setAutoRaise(True)
        cerrar.clicked.connect(aviso.hide)
        lay.addWidget(texto, 1)
        lay.addWidget(boton)
        lay.addWidget(cerrar)
        aviso.hide()
        return aviso

    def hacer_editable(self):
        if not self.doc:
            return
        paginas = elegir_paginas(self, self.doc)
        if not paginas:
            return
        tessdata = asegurar_idiomas(self)
        if not tessdata:
            return

        dialogo = QProgressDialog("Reconociendo el texto…", "Cancelar", 0, len(paginas), self)
        dialogo.setWindowTitle("Hacer editable")
        dialogo.setWindowModality(Qt.WindowModality.WindowModal)
        dialogo.setMinimumDuration(0)
        dialogo.setValue(0)
        self.doc.punto_de_deshacer()  # para poder deshacer el OCR entero de una vez
        hilo = HiloOCR(self.doc.copia_en_memoria(), paginas, tessdata)
        hechas = []
        errores = []

        def pagina_lista(n, palabras):
            self.doc.aplicar_ocr(n, palabras)
            hechas.append(n)
            dialogo.setValue(len(hechas))

        def avance(k, total):
            dialogo.setLabelText(f"Reconociendo el texto… página {paginas[k] + 1} ({k + 1} de {total})")

        hilo.paginaLista.connect(pagina_lista)
        hilo.avance.connect(avance)
        hilo.fallo.connect(errores.append)
        dialogo.canceled.connect(lambda: setattr(hilo, "cancelado", True))
        bucle = QEventLoop()
        hilo.finished.connect(bucle.quit)
        hilo.start()
        bucle.exec()
        dialogo.close()
        self._ocr_terminado(hechas, len(paginas), errores)

    def _ocr_terminado(self, hechas, total, errores):
        self._texto_buscado = ""  # que la próxima búsqueda incluya el texto nuevo
        self.visor.texto_actualizado()
        self._actualizar_estado()
        if errores:
            QMessageBox.critical(self, "Error en el reconocimiento", f"No se pudo terminar el reconocimiento.\n\n{errores[0]}")
        if hechas:
            self.aviso_escaneado.setVisible(bool(self.doc.paginas_sin_texto()))
            sin_texto = sum(1 for n in hechas if not self.doc.tiene_texto(n))
            mensaje = f"Listo: {len(hechas)} de {total} páginas reconocidas. Ya puedes buscar y copiar el texto."
            if sin_texto:
                mensaje += f" ({sin_texto} sin texto legible)"
            self.statusBar().showMessage(mensaje + " Recuerda guardar.", 15000)

    # --- Otros ------------------------------------------------------------
    def _imprimir(self):
        if self.doc:
            if imprimir(self.doc, self, self.visor.pagina_actual):
                self.statusBar().showMessage("Enviado a la impresora", 5000)

    def _pantalla_completa(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def _acerca_de(self):
        QMessageBox.about(
            self,
            "Acerca de PDF Casero",
            f"<b>PDF Casero {__version__}</b><br>Lector y editor de PDF para uso familiar.<br><br>"
            "Hecho con PySide6 (Qt) y PyMuPDF.",
        )

    def dragEnterEvent(self, e):
        if any(u.toLocalFile().lower().endswith(".pdf") for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if u.toLocalFile().lower().endswith(".pdf"):
                self.abrir(u.toLocalFile())
                break

    def closeEvent(self, e):
        if not self.cerrar_documento():
            e.ignore()
            return
        self.ajustes.setValue("geometria", self.saveGeometry())
        super().closeEvent(e)
