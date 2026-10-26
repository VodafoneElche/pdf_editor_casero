"""Ventana principal del lector."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEventLoop, QRect, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QImage, QIntValidator, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
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
        self.miniaturas = QListWidget()
        self.miniaturas.setObjectName("miniaturas")
        self.miniaturas.setItemDelegate(DelegadoMiniatura(self.miniaturas))
        self.miniaturas.setUniformItemSizes(True)
        self.miniaturas.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.miniaturas.setFixedWidth(ANCHO_MINIATURA + 48)
        self.miniaturas.currentRowChanged.connect(self._miniatura_elegida)
        self._cola_miniaturas: list[int] = []
        self._temporizador_mini = QTimer(self, interval=0)
        self._temporizador_mini.timeout.connect(self._generar_miniatura)

        divisor = QWidget()
        lay = QHBoxLayout(divisor)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.miniaturas)
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
            self.acc_guardar, self.acc_guardar_como, self.acc_imprimir, self.acc_ocr, self.acc_editar, self.acc_anterior, self.acc_siguiente, self.acc_alejar, self.acc_acercar,
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
        barra.addAction(self.acc_imprimir)
        barra.addSeparator()
        barra.addAction(self.acc_ocr)
        barra.addAction(self.acc_editar)
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
        for a in (self.acc_guardar_como, self.acc_ancho, self.acc_completa, self.acc_cerrar, self.acc_pantalla, self.acc_acerca):
            menu.addAction(a)
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
            if self.acc_editar.isChecked():
                self.acc_editar.setChecked(False)
                self._cambiar_modo_edicion(False)
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
        self.visor.set_modo_edicion(activo)
        if activo:
            self.statusBar().showMessage(
                "Editar texto: haz clic en una línea para cambiarla (déjala vacía para borrarla) o en un hueco para "
                "escribir. Intro acepta, Esc cancela."
            )
        else:
            self.statusBar().clearMessage()

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
            self.visor.documento_cambiado()

    def rehacer(self):
        if self.doc and self.doc.rehacer():
            self.visor.documento_cambiado()

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
