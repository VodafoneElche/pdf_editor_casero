"""Ventana principal del lector."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEventLoop, QPoint, QRect, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QImage, QIntValidator, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
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
    QTabBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from . import actualizar, conversion
from .dialogo_ocr import HiloOCR, asegurar_idiomas, elegir_paginas
from .documento import ContrasenaNecesaria, Documento
from .impresion import imprimir
from .ventana_google import ControlGoogle
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
        self.setDropIndicatorShown(False)  # pintamos nuestra propia raya
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self._marca = None
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda pos: self.menuPedido.emit(self.mapToGlobal(pos)))

    FORMATO = "application/x-qabstractitemmodeldatalist"

    def _antes_de(self, pos) -> int:
        """Delante de qué página caería lo soltado en esa posición."""
        destino = self.indexAt(pos)
        if not destino.isValid():
            # Por encima de la primera o por debajo de la última
            if self.count() and pos.y() < self.visualRect(self.model().index(0, 0)).top():
                return 0
            return self.count()
        rect = self.visualRect(destino)
        return destino.row() + 1 if pos.y() > rect.center().y() else destino.row()

    def _es_nuestro(self, e) -> bool:
        return e.source() is self or e.mimeData().hasFormat(self.FORMATO)

    def dragEnterEvent(self, e):
        if self._es_nuestro(e):
            e.setDropAction(Qt.DropAction.MoveAction)
            e.accept()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        # Qt solo deja soltar en el borde entre miniaturas; aceptamos en cualquier sitio
        # y marcamos con una raya dónde quedará la página
        if not self._es_nuestro(e):
            return super().dragMoveEvent(e)
        super().dragMoveEvent(e)  # desplaza la lista si se arrastra cerca del borde
        e.setDropAction(Qt.DropAction.MoveAction)
        e.accept()
        self._marca = self._antes_de(e.position().toPoint())
        self.viewport().update()

    def dragLeaveEvent(self, e):
        self._marca = None
        self.viewport().update()
        super().dragLeaveEvent(e)

    def dropEvent(self, e):
        # No dejamos que la lista mueva sus elementos: movemos la página en el PDF y la lista se rehace
        self._marca = None
        self.viewport().update()
        if not self._es_nuestro(e):
            return super().dropEvent(e)
        desde = self.currentRow()
        antes_de = self._antes_de(e.position().toPoint())
        e.setDropAction(Qt.DropAction.IgnoreAction)
        e.accept()
        if desde >= 0:
            self.paginaSoltada.emit(desde, antes_de)

    def paintEvent(self, e):
        super().paintEvent(e)
        if getattr(self, "_marca", None) is None or not self.count():
            return
        if self._marca < self.count():
            y = self.visualRect(self.model().index(self._marca, 0)).top() - 2
        else:
            y = self.visualRect(self.model().index(self.count() - 1, 0)).bottom() + 2
        p = QPainter(self.viewport())
        p.setPen(QPen(QColor("#c4302b"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(10, y, self.viewport().width() - 10, y)
        p.end()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.borrarPulsado.emit()
        else:
            super().keyPressEvent(e)


class DialogoContrasena(QDialog):
    """Pide la contraseña dos veces (para no equivocarse al escribirla)."""

    def __init__(self, padre):
        super().__init__(padre)
        self.setWindowTitle("Proteger con contraseña")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("El PDF pedirá esta contraseña cada vez que se abra."))
        self.clave = QLineEdit()
        self.clave.setEchoMode(QLineEdit.EchoMode.Password)
        self.clave.setPlaceholderText("Contraseña")
        self.repetir = QLineEdit()
        self.repetir.setEchoMode(QLineEdit.EchoMode.Password)
        self.repetir.setPlaceholderText("Repite la contraseña")
        self.ver = QCheckBox("Ver la contraseña")
        self.ver.toggled.connect(self._mostrar)
        self.aviso = QLabel("")
        self.aviso.setStyleSheet("color: #c4302b;")
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.button(QDialogButtonBox.StandardButton.Ok).setText("Proteger y guardar")
        botones.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botones.accepted.connect(self._aceptar)
        botones.rejected.connect(self.reject)
        for w in (self.clave, self.repetir, self.ver, self.aviso, botones):
            lay.addWidget(w)

    def _mostrar(self, si: bool):
        modo = QLineEdit.EchoMode.Normal if si else QLineEdit.EchoMode.Password
        self.clave.setEchoMode(modo)
        self.repetir.setEchoMode(modo)

    def _aceptar(self):
        if len(self.clave.text()) < 4:
            self.aviso.setText("La contraseña tiene que tener al menos 4 caracteres.")
        elif self.clave.text() != self.repetir.text():
            self.aviso.setText("Las dos contraseñas no coinciden.")
        else:
            self.accept()

    @classmethod
    def pedir(cls, padre) -> str | None:
        d = cls(padre)
        return d.clave.text() if d.exec() == QDialog.DialogCode.Accepted else None


class Bienvenida(QWidget):
    """Pantalla inicial cuando no hay ningún PDF abierto."""

    def __init__(self, ventana: "VentanaPrincipal"):
        super().__init__()
        self.setObjectName("bienvenida")
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo = QLabel()
        logo.setPixmap(
            QPixmap(str(Path(__file__).resolve().parent / "recursos" / "icono.png")).scaled(
                96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        titulo = QLabel("PDF Familiar")
        titulo.setObjectName("tituloBienvenida")
        version = QLabel(f"Versión {__version__}")
        version.setObjectName("textoBienvenida")
        texto = QLabel("Abre un PDF o arrástralo a esta ventana")
        texto.setObjectName("textoBienvenida")
        boton = QToolButton()
        boton.setText("Abrir PDF…")
        boton.setObjectName("botonPrincipal")
        boton.clicked.connect(ventana.abrir_dialogo)
        boton_google = QToolButton()
        boton_google.setText("Traer de Google…")
        boton_google.clicked.connect(lambda: ventana.google.traer())
        self.lista = QListWidget()
        self.lista.setObjectName("recientes")
        self.lista.setMaximumWidth(520)
        # Un clic basta para abrir (antes hacía falta doble clic y el primero solo lo marcaba)
        self.lista.itemClicked.connect(lambda it: ventana.abrir(it.data(Qt.ItemDataRole.UserRole)))
        self.lista.itemActivated.connect(lambda it: ventana.abrir(it.data(Qt.ItemDataRole.UserRole)))
        self.etiqueta_recientes = QLabel("Abiertos recientemente")
        self.etiqueta_recientes.setObjectName("textoBienvenida")
        for w in (logo, titulo, version, texto, boton, boton_google, self.etiqueta_recientes, self.lista):
            lay.addWidget(w, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self._muestras_de_color(ventana), 0, Qt.AlignmentFlag.AlignHCenter)

    def _muestras_de_color(self, ventana: "VentanaPrincipal") -> QWidget:
        """Botones redondos para cambiar los colores, como en un navegador: una fila para el
        fondo y otra para la barra de menú (los mismos colores, un tono más oscuro)."""
        from PySide6.QtWidgets import QButtonGroup, QGridLayout

        from .estilo import TEMAS

        caja = QWidget()
        rejilla = QGridLayout(caja)
        rejilla.setContentsMargins(0, 16, 0, 0)
        rejilla.setHorizontalSpacing(10)
        rejilla.setVerticalSpacing(8)
        tema = ventana.ajustes.value("tema", "gris")
        barra = ventana.ajustes.value("barra", None) or tema
        self.muestras, self.muestras_barra = {}, {}
        for fila, (rotulo, actual, destino, al_pulsar) in enumerate(
            [
                ("Color de fondo:", tema, self.muestras, ventana.cambiar_tema),
                ("Color de la barra:", barra, self.muestras_barra, ventana.cambiar_barra),
            ]
        ):
            etiqueta = QLabel(rotulo)
            etiqueta.setObjectName("textoBienvenida")
            rejilla.addWidget(etiqueta, fila, 0, Qt.AlignmentFlag.AlignRight)
            grupo = QButtonGroup(caja)
            for k, (nombre, (texto, fondo, _, _, color, oscuro)) in enumerate(TEMAS.items()):
                b = QToolButton()
                b.setObjectName("muestraTema")
                b.setCheckable(True)
                b.setChecked(nombre == actual)
                b.setFixedSize(32, 32)
                if destino is self.muestras:
                    b.setToolTip(texto)
                    pintura = f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {fondo}, stop:0.5 {fondo}, stop:0.51 {color}, stop:1 {color})"
                else:
                    b.setToolTip(f"Barra: {texto[0].lower() + texto[1:]}")
                    pintura = oscuro if nombre != "gris" else "#ffffff"
                b.setStyleSheet(f"QToolButton {{ background: {pintura}; }}")
                b.clicked.connect(lambda _=False, n=nombre, f=al_pulsar: f(n))
                grupo.addButton(b)
                rejilla.addWidget(b, fila, k + 1)
                destino[nombre] = b
        return caja

    def actualizar(self, recientes: list[str]):
        self.lista.clear()
        for ruta in recientes:
            it = QListWidgetItem(Path(ruta).name)
            it.setToolTip(ruta)
            it.setData(Qt.ItemDataRole.UserRole, ruta)
            self.lista.addItem(it)
        self.lista.setVisible(bool(recientes))
        self.etiqueta_recientes.setVisible(bool(recientes))


ABRIBLES = (".pdf",) + conversion.EXTENSIONES_WORD


def en_segundo_plano(funcion, *args):
    """Ejecuta `funcion` en otro hilo sin congelar la ventana y devuelve su resultado (o lanza su error)."""
    import threading

    resultado = {}

    def trabajo():
        try:
            resultado["valor"] = funcion(*args)
        except Exception as e:
            resultado["error"] = e

    hilo = threading.Thread(target=trabajo, daemon=True)
    hilo.start()
    bucle = QEventLoop()
    reloj = QTimer(interval=100)
    reloj.timeout.connect(lambda: hilo.is_alive() or bucle.quit())
    reloj.start()
    bucle.exec()
    reloj.stop()
    if "error" in resultado:
        raise resultado["error"]
    return resultado.get("valor")


class VentanaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ajustes = QSettings("PDFCasero", "PDFCasero")
        self.doc: Documento | None = None  # el de la pestaña elegida
        self.abiertos: list[Documento] = []  # uno por pestaña, en el mismo orden
        self._resultados = []
        self._activo = -1
        self._texto_buscado = ""

        self.setWindowTitle(f"PDF Familiar {__version__}")
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

        # Pestañas arriba, una por PDF abierto (como en Adobe)
        self.pestanas = QTabBar()
        self.pestanas.setObjectName("pestanas")
        self.pestanas.setTabsClosable(True)
        self.pestanas.setMovable(True)
        self.pestanas.setDocumentMode(True)
        self.pestanas.setExpanding(False)
        self.pestanas.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.pestanas.currentChanged.connect(self._pestana_elegida)
        self.pestanas.tabCloseRequested.connect(self.cerrar_pestana)
        self.pestanas.tabMoved.connect(self._pestana_movida)
        con_pestanas = QWidget()
        columna = QVBoxLayout(con_pestanas)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(0)
        columna.addWidget(self.pestanas)
        columna.addWidget(divisor, 1)

        self.bienvenida = Bienvenida(self)
        self.pila = QStackedWidget()
        self.pila.addWidget(self.bienvenida)
        self.pila.addWidget(con_pestanas)
        self.setCentralWidget(self.pila)

        self._crear_acciones()
        self._crear_barra()
        self._crear_barra_dibujo()
        self._crear_barra_formulario()
        self.visor.paginaCambiada.connect(self._pagina_cambiada)
        self.visor.zoomCambiado.connect(self._zoom_cambiado)
        self.visor.documentoEditado.connect(self._documento_editado)
        self.statusBar().showMessage("Listo")
        self.bienvenida.actualizar(self.recientes())
        self._actualizar_estado()

        geom = self.ajustes.value("geometria")
        if geom is not None:
            self.restoreGeometry(geom)
        # Al abrir, mira en silencio si hay versión nueva (solo en la versión instalada)
        if actualizar.instalada():
            QTimer.singleShot(3000, self.buscar_actualizacion)

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
        self.acc_formulario = self._accion(
            "Formulario", None, QKeySequence("Ctrl+Shift+F"), self._cambiar_modo_formulario,
            "Crear casillas y zonas rellenables para quien reciba el PDF (Ctrl+Mayús+F)",
        )
        self.acc_formulario.setCheckable(True)
        self.acc_word = self._accion(
            "Guardar copia en Word (.docx)", None, QKeySequence("Ctrl+Shift+W"), self.exportar_word,
            "Guardar una copia en Word (.docx) (Ctrl+Mayús+W)",
        )
        # Jose prefirió quitar "crear formularios" (los recibidos se siguen pudiendo rellenar)
        self.acc_formulario.setVisible(False)
        self.acc_formulario.setShortcuts([])
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
        self.acc_girar_izq = self._accion(
            "↺", None, QKeySequence("Ctrl+Shift+-"), lambda: self.girar_pagina(-90),
            "Girar la página a la izquierda (Ctrl+Mayús+-)",
        )
        self.acc_girar_der = self._accion(
            "↻", None, [QKeySequence("Ctrl+Shift++"), QKeySequence("Ctrl+Shift+=")], lambda: self.girar_pagina(90),
            "Girar la página a la derecha (Ctrl+Mayús++)",
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
        # Cambiar de pestaña como en el navegador
        self._accion("Pestaña siguiente", None, QKeySequence("Ctrl+Tab"), lambda: self._pasar_pestana(1))
        self._accion("Pestaña anterior", None, QKeySequence("Ctrl+Shift+Tab"), lambda: self._pasar_pestana(-1))
        self.acc_pantalla = self._accion("Pantalla completa", "ViewFullscreen", QKeySequence("F11"), self._pantalla_completa)
        self.acc_acerca = self._accion("Acerca de", "HelpAbout", [], self._acerca_de)
        self.acc_actualizar = self._accion(
            "Buscar actualizaciones", "SoftwareUpdateAvailable", [], lambda: self.buscar_actualizacion(avisar=True),
            "Ver si hay una versión nueva de PDF Familiar",
        )
        self.acc_proteger = self._accion(
            "Proteger con contraseña…", "SecurityHigh", [], self.proteger_con_contrasena,
            "Que el PDF pida una contraseña para abrirlo",
        )
        for a, teclas in ((self.acc_siguiente, ["Ctrl+Right"]), (self.acc_anterior, ["Ctrl+Left"])):
            a.setShortcuts([QKeySequence(t) for t in teclas])
        self._acciones_doc = [
            self.acc_guardar, self.acc_guardar_como, self.acc_imprimir, self.acc_ocr, self.acc_editar, self.acc_dibujar, self.acc_formulario, self.acc_word, self.acc_anterior, self.acc_siguiente, self.acc_alejar, self.acc_acercar, self.acc_girar_izq, self.acc_girar_der,
            self.acc_ancho, self.acc_completa, self.acc_buscar, self.acc_cerrar, self.acc_proteger,
        ]

    def _crear_barra(self):
        barra = QToolBar("Principal")
        barra.setObjectName("barraPrincipal")
        barra.setMovable(False)
        barra.setIconSize(QSize(20, 20))
        barra.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(barra)

        # Menú "Más" al principio, como en Acrobat: lo que se usa menos, para que la barra quepa
        menu = QMenu(self)
        for a in (self.acc_imprimir, self.acc_proteger, self.acc_ancho, self.acc_completa, self.acc_cerrar, self.acc_pantalla, self.acc_actualizar, self.acc_acerca):
            menu.addAction(a)
        self.menu_paginas = self._crear_menu_paginas()
        self.boton_paginas.setMenu(self.menu_paginas)
        menu.insertMenu(menu.actions()[0], self.menu_paginas)
        menu.insertSeparator(menu.actions()[1])
        boton_mas = QToolButton()
        boton_mas.setText("☰ Más")
        boton_mas.setToolTip("Más opciones")
        boton_mas.setMenu(menu)
        boton_mas.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        barra.addWidget(boton_mas)
        barra.addSeparator()

        barra.addAction(self.acc_abrir)
        barra.addAction(self.acc_guardar)
        barra.addAction(self.acc_guardar_como)
        barra.addSeparator()
        barra.addAction(self.acc_ocr)
        barra.addAction(self.acc_editar)
        barra.addAction(self.acc_dibujar)
        self.google = ControlGoogle(self)
        barra.addWidget(self.google.boton)
        self.addAction(self.acc_word)  # sin botón propio: está en el menú Google
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
        barra.addAction(self.acc_girar_izq)
        barra.addAction(self.acc_girar_der)

        espacio = QWidget()
        espacio.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        barra.addWidget(espacio)

        self.campo_buscar = QLineEdit()
        self.campo_buscar.setPlaceholderText("Buscar en el documento…")
        self.campo_buscar.setClearButtonEnabled(True)
        self.campo_buscar.setMinimumWidth(120)
        self.campo_buscar.setMaximumWidth(220)
        self.campo_buscar.returnPressed.connect(self._buscar_siguiente)
        self.campo_buscar.textChanged.connect(self._texto_busqueda_cambiado)
        barra.addWidget(self.campo_buscar)
        self.etiqueta_resultados = QLabel("")
        self.etiqueta_resultados.setMinimumWidth(70)
        barra.addWidget(self.etiqueta_resultados)
        # ▲▼ solo sirven para saltar entre los resultados de la búsqueda (no pasan página)
        self.acc_res_ant = self._accion(
            "▲", None, QKeySequence("Shift+F3"), self._buscar_anterior, "Resultado de búsqueda anterior (Mayús+F3)"
        )
        self.acc_res_sig = self._accion(
            "▼", None, QKeySequence("F3"), self._buscar_siguiente, "Resultado de búsqueda siguiente (F3)"
        )
        barra.addAction(self.acc_res_ant)
        barra.addAction(self.acc_res_sig)
        # Buscar mientras se escribe, en cuanto se deja de teclear un momento
        self._temporizador_busqueda = QTimer(self, singleShot=True, interval=350)
        self._temporizador_busqueda.timeout.connect(self._buscar_al_escribir)

    def _actualizar_estado(self):
        hay = self.doc is not None
        for a in self._acciones_doc:
            a.setEnabled(hay)
        self._botones_busqueda()
        self.campo_pagina.setEnabled(hay)
        self.campo_buscar.setEnabled(hay)
        self.pila.setCurrentIndex(1 if hay else 0)
        if hay:
            self.campo_pagina.setValidator(QIntValidator(1, self.doc.num_paginas, self))
            self.etiqueta_total.setText(f" de {self.doc.num_paginas} ")
            self.acc_deshacer.setEnabled(self.doc.puede_deshacer)
            self.acc_rehacer.setEnabled(self.doc.puede_rehacer)
            marca = "● " if self.doc.modificado else ""
            self.setWindowTitle(f"{marca}{self.doc.titulo} – PDF Familiar {__version__}")
            self._rotular_pestanas()
        else:
            self.acc_deshacer.setEnabled(False)
            self.acc_rehacer.setEnabled(False)
            for accion in (self.acc_editar, self.acc_dibujar, self.acc_formulario):
                if accion.isChecked():
                    accion.setChecked(False)
            self._poner_modo("leer")
            self.etiqueta_total.setText(" de 0 ")
            self.campo_pagina.setText("")
            self.setWindowTitle(f"PDF Familiar {__version__}")
            self.bienvenida.actualizar(self.recientes())

    # --- Abrir y cerrar ---------------------------------------------------
    def abrir_dialogo(self):
        carpeta = self.ajustes.value("ultima_carpeta", str(Path.home()))
        rutas, _ = QFileDialog.getOpenFileNames(  # se pueden elegir varios: cada uno en su pestaña
            self, "Abrir", carpeta, "PDF y Word (*.pdf *.docx);;Documentos PDF (*.pdf);;Documentos de Word (*.docx);;Todos (*)"
        )
        for ruta in rutas:
            self.abrir(ruta)

    def abrir(self, ruta: str) -> bool:
        ruta = str(Path(ruta))
        if not Path(ruta).exists():
            QMessageBox.warning(self, "No se encuentra", f"El archivo ya no existe:\n{ruta}")
            self._quitar_reciente(ruta)
            return False
        if ruta.lower().endswith(conversion.EXTENSIONES_WORD):
            return self.importar_word(ruta)
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

        return self._mostrar_documento(doc, ruta)

    def _mostrar_documento(self, doc: Documento, ruta: str, reciente: bool = True) -> bool:
        """Abre el documento en una pestaña nueva (o va a la suya si ya estaba abierto)."""
        ya = next((d for d in self.abiertos if reciente and not getattr(d, "nuevo", False) and d.ruta == doc.ruta), None)
        if ya is not None:
            doc.cerrar()
            self.pestanas.setCurrentIndex(self.abiertos.index(ya))
            self.statusBar().showMessage(f"{ya.ruta.name} ya estaba abierto", 5000)
            return True
        self.abiertos.append(doc)
        self.pestanas.blockSignals(True)
        i = self.pestanas.addTab(doc.ruta.name)
        self.pestanas.blockSignals(False)
        self._activar(doc)
        self.pestanas.setCurrentIndex(i)
        if reciente:
            self._anadir_reciente(ruta)
        self.ajustes.setValue("ultima_carpeta", str(Path(ruta).parent))
        self.statusBar().showMessage(f"{Path(ruta).name} · {doc.num_paginas} páginas", 5000)
        return True

    # --- Word -------------------------------------------------------------
    def importar_word(self, ruta: str) -> bool:
        """Abre un .docx convirtiéndolo en PDF (queda sin guardar hasta que se pulse Guardar)."""
        import tempfile

        carpeta = Path(tempfile.mkdtemp(prefix="pdfcasero_"))
        tmp = carpeta / (Path(ruta).stem + ".pdf")
        self.statusBar().showMessage(f"Convirtiendo {Path(ruta).name} a PDF…")
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            metodo = en_segundo_plano(conversion.word_a_pdf, ruta, str(tmp))
            doc = Documento(tmp)
        except Exception as e:
            QMessageBox.critical(self, "No se pudo convertir", f"No se pudo convertir el documento de Word:\n{ruta}\n\n{e}")
            return False
        finally:
            self.unsetCursor()
        doc.ruta = Path(ruta).with_suffix(".pdf")  # al guardar se propone este nombre, junto al .docx
        doc.nuevo = True
        doc.modificado = True
        if not self._mostrar_documento(doc, ruta, reciente=False):
            return False
        aviso = "con Microsoft Word" if metodo == "Word" else "(sin Word instalado, el diseño puede variar un poco)"
        self.statusBar().showMessage(f"Convertido a PDF {aviso}. Pulsa Guardar para guardarlo como PDF.", 15000)
        return True

    def exportar_word(self):
        if not self.doc:
            return
        sugerido = str(self.doc.ruta.with_suffix(".docx"))
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar copia en Word", sugerido, "Documento de Word (*.docx)")
        if not ruta:
            return
        if not ruta.lower().endswith(".docx"):
            ruta += ".docx"
        paginas = self.elegir_paginas_word()
        if paginas is False:
            return
        if self.convertir_a_docx(ruta, paginas):
            QMessageBox.information(
                self,
                "Guardado en Word",
                f"Listo: {Path(ruta).name}\n\nPara editar en Google Docs es más cómodo el botón "
                "«Google → Enviar a Google Docs», que lo sube y lo trae de vuelta como PDF.",
            )

    def elegir_paginas_word(self):
        """Si el PDF tiene más de una página, pregunta si pasar solo la que se ve o todas.

        Devuelve la lista de páginas (None = todas) o False si se cancela.
        """
        total = self.doc.num_paginas
        if total <= 1:
            return None
        actual = self.visor.pagina_actual
        caja = QMessageBox(self)
        caja.setWindowTitle("¿Qué páginas?")
        texto = f"Este PDF tiene {total} páginas. ¿Envías solo la que estás viendo o el documento entero?"
        if total > 3:
            texto += "\n\nConvertir cada página lleva unos segundos, así que todas pueden tardar varios minutos."
        caja.setText(texto)
        solo = caja.addButton(f"Solo la página {actual + 1}", QMessageBox.ButtonRole.AcceptRole)
        todas = caja.addButton(f"Las {total} páginas", QMessageBox.ButtonRole.AcceptRole)
        caja.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        caja.setDefaultButton(solo)
        caja.exec()
        if caja.clickedButton() is solo:
            return [actual]
        if caja.clickedButton() is todas:
            return None
        return False

    def convertir_a_docx(self, ruta: str, paginas: list[int] | None = None) -> bool:
        """Convierte el PDF abierto (o esas páginas) en el .docx `ruta`, con avance y Cancelar."""
        total = len(paginas) if paginas else self.doc.num_paginas
        dialogo = QProgressDialog("Preparando la conversión…", "Cancelar", 0, 2 * total, self)
        dialogo.setWindowTitle("Convirtiendo")
        dialogo.setWindowModality(Qt.WindowModality.WindowModal)
        dialogo.setMinimumDuration(0)
        dialogo.setValue(0)
        trabajo = conversion.ExportacionWord(self.doc.copia_en_memoria(), ruta, paginas)
        bucle = QEventLoop()
        final = {}

        def comprobar():
            if dialogo.wasCanceled():
                trabajo.cancelar()
                final["r"] = ("cancelado", "")
                bucle.quit()
                return
            r = trabajo.resultado()
            if trabajo.avance:
                fase, i, n = trabajo.avance
                accion = "Analizando" if fase == 1 else "Convirtiendo"
                dialogo.setLabelText(f"{accion} la página {i} de {n}…")
                if fase == 0:  # una sola fase
                    dialogo.setMaximum(n)
                    dialogo.setValue(i - 1)
                else:
                    dialogo.setMaximum(2 * n)
                    dialogo.setValue((fase - 1) * n + i - 1)
            if r is not None:
                final["r"] = r
                bucle.quit()

        reloj = QTimer(interval=300)
        reloj.timeout.connect(comprobar)
        reloj.start()
        dialogo.show()
        bucle.exec()
        reloj.stop()
        dialogo.close()
        estado, detalle = final.get("r", ("error", ""))
        if estado == "error":
            QMessageBox.critical(self, "No se pudo convertir", f"No se pudo convertir a Word.\n\n{detalle}")
        return estado == "ok"

    def _activar(self, doc: Documento | None):
        """Enseña `doc` en el visor, recordando por dónde iba el que se deja."""
        if self.doc is not None and self.doc is not doc:
            self.doc.vista = (self.visor.pagina_actual, self.visor.zoom, self.visor.ajustar_ancho)
        for accion in (self.acc_editar, self.acc_dibujar, self.acc_formulario):
            if accion.isChecked():
                accion.setChecked(False)
        self._poner_modo("leer")
        self._temporizador_mini.stop()
        self.miniaturas.clear()
        self._limpiar_busqueda()
        self._texto_buscado = ""
        self.doc = doc
        pagina, zoom, ancho = getattr(doc, "vista", (0, None, None)) if doc else (0, None, None)
        if zoom is not None:
            self.visor.ajustar_ancho = ancho
            self.visor.zoom = zoom
        self.visor.cargar(doc)
        self._actualizar_estado()
        if doc is None:
            return
        self._preparar_miniaturas()
        self._mostrar_aviso()
        if zoom is not None:
            self.etiqueta_zoom.setText(f"{round(zoom * 100)} %")
        if pagina:
            QTimer.singleShot(0, lambda: self.visor.ir_a_pagina(pagina))

    def _pestana_elegida(self, i: int):
        if 0 <= i < len(self.abiertos) and self.abiertos[i] is not self.doc:
            self._activar(self.abiertos[i])

    def _pasar_pestana(self, paso: int):
        if len(self.abiertos) > 1:
            self.pestanas.setCurrentIndex((self.pestanas.currentIndex() + paso) % len(self.abiertos))

    def _pestana_movida(self, desde: int, hasta: int):
        self.abiertos.insert(hasta, self.abiertos.pop(desde))

    def _rotular_pestanas(self):
        for i, d in enumerate(self.abiertos):
            self.pestanas.setTabText(i, ("● " if d.modificado else "") + d.ruta.name)
            self.pestanas.setTabToolTip(i, str(d.ruta))

    def cerrar_pestana(self, i: int) -> bool:
        """Cierra el PDF de esa pestaña. False si el usuario cancela por cambios sin guardar."""
        if not 0 <= i < len(self.abiertos):
            return True
        if self.abiertos[i] is not self.doc:
            self.pestanas.setCurrentIndex(i)  # que se vea cuál es antes de preguntar
        if not self._confirmar_cambios():
            return False
        doc = self.abiertos.pop(i)
        self.pestanas.blockSignals(True)
        self.pestanas.removeTab(i)
        self.pestanas.blockSignals(False)
        siguiente = self.abiertos[min(i, len(self.abiertos) - 1)] if self.abiertos else None
        self.doc = None  # el que se cierra no guarda vista
        self._activar(siguiente)
        if siguiente is not None:
            self.pestanas.setCurrentIndex(self.abiertos.index(siguiente))
        doc.cerrar()
        return True

    def cerrar_documento(self) -> bool:
        """Cierra el PDF de la pestaña elegida (Ctrl+W)."""
        if self.doc is None:
            return True
        return self.cerrar_pestana(self.abiertos.index(self.doc))

    def cerrar_todos(self) -> bool:
        while self.abiertos:
            if not self.cerrar_pestana(len(self.abiertos) - 1):
                return False
        return True

    # --- Guardar ----------------------------------------------------------
    def guardar(self) -> bool:
        if not self.doc:
            return False
        if getattr(self.doc, "nuevo", False):
            return self.guardar_como()  # viene de Word: aún no tiene archivo PDF propio
        if not self.doc.modificado:
            self.statusBar().showMessage("No hay cambios que guardar", 4000)
            return True
        return self._guardar_en(None)

    def proteger_con_contrasena(self):
        """Pone (o quita) la contraseña que pide el PDF al abrirse y lo guarda."""
        if not self.doc:
            return
        if self.doc.protegido:
            caja = QMessageBox(self)
            caja.setWindowTitle("Contraseña del PDF")
            caja.setIcon(QMessageBox.Icon.Question)
            caja.setText("Este PDF ya pide contraseña para abrirlo. ¿Qué quieres hacer?")
            cambiar = caja.addButton("Cambiar la contraseña", QMessageBox.ButtonRole.AcceptRole)
            quitar = caja.addButton("Quitar la contraseña", QMessageBox.ButtonRole.DestructiveRole)
            caja.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
            caja.exec()
            if caja.clickedButton() is quitar:
                self.doc.poner_contrasena(None)
                if self._guardar_tras_clave():
                    QMessageBox.information(self, "Contraseña quitada", "El PDF ya se abre sin contraseña.")
                return
            if caja.clickedButton() is not cambiar:
                return
        clave = DialogoContrasena.pedir(self)
        if not clave:
            return
        self.doc.poner_contrasena(clave)
        if self._guardar_tras_clave():
            QMessageBox.information(
                self, "PDF protegido",
                f"Listo: «{self.doc.ruta.name}» pide la contraseña para abrirse, aquí y en cualquier "
                "otro programa (Adobe, el navegador, el móvil…).\n\n"
                "Apúntala en un sitio seguro: si se olvida, no hay forma de recuperar el PDF.",
            )

    def _guardar_tras_clave(self) -> bool:
        if getattr(self.doc, "nuevo", False):
            return self.guardar_como()
        return self._guardar_en(None)

    def guardar_como(self) -> bool:
        if not self.doc:
            return False
        if getattr(self.doc, "nuevo", False):
            sugerido = str(self.doc.ruta)
        else:
            sugerido = str(self.doc.ruta.with_name(self.doc.ruta.stem + " (copia).pdf"))
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar como", sugerido, "Documentos PDF (*.pdf)")
        if not ruta:
            return False
        if not ruta.lower().endswith(".pdf"):
            ruta += ".pdf"
        if self._guardar_en(ruta):
            self.doc.nuevo = False
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
    def cambiar_tema(self, nombre: str):
        """Color de fondo. Si la barra no se ha elegido aparte, la barra lo sigue."""
        self.ajustes.setValue("tema", nombre)
        if not self.ajustes.value("barra", None):
            self.bienvenida.muestras_barra[nombre].setChecked(True)
        self._aplicar_colores()

    def cambiar_barra(self, nombre: str):
        self.ajustes.setValue("barra", nombre)
        self._aplicar_colores()

    def _aplicar_colores(self):
        from .estilo import hoja_estilo

        QApplication.instance().setStyleSheet(
            hoja_estilo(self.ajustes.value("tema", "gris"), self.ajustes.value("barra", None))
        )

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
        if not texto.strip():
            self._temporizador_busqueda.stop()
            self._limpiar_busqueda()
        else:
            self._temporizador_busqueda.start()

    def _buscar_al_escribir(self):
        if self.campo_buscar.text().strip() != self._texto_buscado:
            self._buscar_siguiente()

    def _botones_busqueda(self):
        hay = bool(self.doc) and len(self._resultados) > 0
        self.acc_res_ant.setEnabled(hay)
        self.acc_res_sig.setEnabled(hay)

    def _limpiar_busqueda(self):
        self._resultados, self._activo, self._texto_buscado = [], -1, ""
        self.etiqueta_resultados.setText("")
        self.visor.mostrar_resultados([], -1)
        self._botones_busqueda()

    def _ejecutar_busqueda(self) -> bool:
        texto = self.campo_buscar.text().strip()
        if not self.doc or not texto:
            return False
        if texto != self._texto_buscado:
            self._texto_buscado = texto
            self._resultados = self.doc.buscar(texto)
            self._activo = -1
            self._botones_busqueda()
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
        self._cambiar_modo("editar", activo)

    def _cambiar_modo_dibujo(self, activo: bool):
        self._cambiar_modo("dibujar", activo)

    def _cambiar_modo_formulario(self, activo: bool):
        self._cambiar_modo("formulario", activo)

    def _cambiar_modo(self, modo: str, activo: bool):
        """Solo un modo a la vez: al activar uno se desmarcan los otros."""
        botones = {"editar": self.acc_editar, "dibujar": self.acc_dibujar, "formulario": self.acc_formulario}
        if activo:
            for clave, accion in botones.items():
                if clave != modo:
                    accion.setChecked(False)
        self._poner_modo(modo if activo else "leer")

    def _poner_modo(self, modo: str):
        self.visor.set_modo(modo)
        self.barra_dibujo.setVisible(modo == "dibujar")
        self.barra_formulario.setVisible(modo == "formulario")
        mensajes = {
            "editar": "Editar texto: haz clic en una línea para cambiarla (déjala vacía para borrarla) o en un hueco "
            "para escribir. Intro acepta, Esc cancela.",
            "dibujar": "Dibujar: elige herramienta y arrastra. Con Seleccionar mueves, estiras (cuadraditos), "
            "cambias color o borras (Supr). Doble clic cambia el texto de un globo.",
            "formulario": "Formulario: elige el tipo de campo y arrastra donde irá. Con Seleccionar lo mueves o "
            "estiras (cuadradito), doble clic le cambia el nombre, Supr lo borra.",
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

    # --- Barra de formulario -----------------------------------------------
    HERRAMIENTAS_FORMULARIO = (
        ("seleccionar", "Seleccionar", "Seleccionar, mover y estirar campos"),
        ("texto", "Campo de texto", "Arrastra para crear una zona de una línea (nombre, fecha…)"),
        ("multilinea", "Texto largo", "Arrastra para crear una zona de varias líneas (observaciones…)"),
        ("casilla", "Casilla", "Haz clic donde irá una casilla para marcar ✓"),
    )

    def _crear_barra_formulario(self):
        barra = QToolBar("Formulario")
        barra.setObjectName("barraDibujo")
        barra.setMovable(False)
        self.addToolBar(barra)
        control = self.visor.formulario
        grupo = QActionGroup(self)
        self._herramientas_formulario = {}
        for clave, texto, consejo in self.HERRAMIENTAS_FORMULARIO:
            a = QAction(texto, self, checkable=True)
            a.setToolTip(consejo)
            a.triggered.connect(lambda _=False, c=clave: self._elegir_herramienta_formulario(c))
            grupo.addAction(a)
            barra.addAction(a)
            self._herramientas_formulario[clave] = a
        self._herramientas_formulario["seleccionar"].setChecked(True)
        barra.addSeparator()
        self.acc_renombrar_campo = QAction("Cambiar nombre", self)
        self.acc_renombrar_campo.setToolTip("Cambiar el nombre del campo seleccionado (o doble clic)")
        self.acc_renombrar_campo.triggered.connect(
            lambda: control.seleccion and self.visor.pedir_nombre_campo(*control.seleccion)
        )
        barra.addAction(self.acc_renombrar_campo)
        self.acc_borrar_campo = QAction("Borrar campo", self)
        self.acc_borrar_campo.setToolTip("Borrar el campo seleccionado (Supr)")
        self.acc_borrar_campo.triggered.connect(control.borrar_seleccion)
        barra.addAction(self.acc_borrar_campo)
        barra.addSeparator()
        aviso = QLabel("  Para rellenar, sal de este modo y haz clic en las casillas.")
        aviso.setStyleSheet("color: #6b6b73;")
        barra.addWidget(aviso)
        control.al_cambiar_seleccion = self._campo_seleccionado
        self._campo_seleccionado(None)
        barra.hide()
        self.barra_formulario = barra

    def _elegir_herramienta_formulario(self, clave):
        self.visor.formulario.herramienta = clave
        if clave != "seleccionar":
            self.visor.formulario.seleccionar(None)

    def _campo_seleccionado(self, campo):
        self.acc_borrar_campo.setEnabled(campo is not None)
        self.acc_renombrar_campo.setEnabled(campo is not None)
        if campo is not None:
            self.statusBar().showMessage(f"Campo «{campo.nombre}»")

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
        """Franja encima de la página: avisa si el PDF es escaneado o si ya se puede editar."""
        aviso = QFrame()
        aviso.setObjectName("avisoEscaneado")
        lay = QHBoxLayout(aviso)
        lay.setContentsMargins(16, 8, 12, 8)
        self._texto_aviso = QLabel()
        self._boton_aviso = QToolButton()
        self._boton_aviso.setObjectName("botonAviso")
        self._boton_aviso.clicked.connect(self._accion_aviso)
        cerrar = QToolButton()
        cerrar.setText("✕")
        cerrar.setToolTip("Ocultar")
        cerrar.setAutoRaise(True)
        cerrar.clicked.connect(aviso.hide)
        lay.addWidget(self._texto_aviso, 1)
        lay.addWidget(self._boton_aviso)
        lay.addWidget(cerrar)
        aviso.hide()
        return aviso

    def _mostrar_aviso(self):
        """Escaneado (amarillo, botón Hacer editable) o ya editable (verde, botón Editar texto)."""
        if not self.doc:
            self.aviso_escaneado.hide()
            return
        sin_texto = self.doc.paginas_sin_texto()
        self._aviso_escaneado = bool(sin_texto)
        if sin_texto:
            if len(sin_texto) == self.doc.num_paginas:
                texto = "Este PDF parece escaneado: su texto todavía no se puede buscar, copiar ni cambiar."
            else:
                texto = f"{len(sin_texto)} páginas de este PDF parecen escaneadas: su texto todavía no se puede buscar ni cambiar."
            self._texto_aviso.setText(texto)
            self._boton_aviso.setText("Hacer editable")
        else:
            self._texto_aviso.setText(
                "Este PDF ya es editable: su texto se puede buscar, copiar y cambiar sin pasar el OCR."
            )
            self._boton_aviso.setText("Editar texto")
        self.aviso_escaneado.setProperty("editable", not sin_texto)
        self.aviso_escaneado.style().unpolish(self.aviso_escaneado)
        self.aviso_escaneado.style().polish(self.aviso_escaneado)
        self.aviso_escaneado.show()

    def _accion_aviso(self):
        if self._aviso_escaneado:
            self.hacer_editable()
        else:
            self.aviso_escaneado.hide()
            if not self.acc_editar.isChecked():
                self.acc_editar.trigger()

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
            dialogo.setLabelText(f"Reconociendo el texto… {k} de {total} páginas (varias a la vez)")

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
            self._mostrar_aviso()
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
            "Acerca de PDF Familiar",
            f"<b>PDF Familiar {__version__}</b><br>Lector y editor de PDF para uso familiar.<br><br>"
            "Hecho con PySide6 (Qt) y PyMuPDF.",
        )

    # --- Actualizaciones -------------------------------------------------
    def buscar_actualizacion(self, avisar: bool = False):
        """Mira si hay versión nueva. Con `avisar`, también dice si ya está al día o si falla."""
        import threading

        resultado = {}

        def trabajo():
            try:
                resultado["nueva"] = actualizar.buscar_nueva(__version__)
            except Exception as e:
                resultado["error"] = e

        hilo = threading.Thread(target=trabajo, daemon=True)
        hilo.start()
        reloj = QTimer(self, interval=200)

        def mirar():
            if hilo.is_alive():
                return
            reloj.stop()
            reloj.deleteLater()
            if "error" in resultado:
                if avisar:
                    QMessageBox.warning(
                        self, "Buscar actualizaciones",
                        "No se ha podido comprobar si hay una versión nueva. Mira que haya internet y prueba otra vez.",
                    )
            elif resultado.get("nueva"):
                self._ofrecer_actualizacion(resultado["nueva"])
            elif avisar:
                QMessageBox.information(self, "Buscar actualizaciones", f"Ya tienes la última versión ({__version__}).")

        reloj.timeout.connect(mirar)
        reloj.start()

    def _ofrecer_actualizacion(self, nueva: dict):
        if getattr(self, "_actualizando", False):
            return
        caja = QMessageBox(self)
        caja.setIcon(QMessageBox.Icon.Information)
        caja.setWindowTitle("Hay una versión nueva")
        caja.setText(f"<b>Ya está disponible PDF Familiar {nueva['version']}</b> (tienes la {__version__}).")
        caja.setInformativeText("Se descarga e instala sola, y PDF Familiar se vuelve a abrir al terminar.")
        si = caja.addButton("Actualizar ahora", QMessageBox.ButtonRole.AcceptRole)
        caja.addButton("Más tarde", QMessageBox.ButtonRole.RejectRole)
        caja.exec()
        if caja.clickedButton() is not si:
            return
        if not actualizar.instalada():
            QMessageBox.information(self, "Actualizar", "Solo se puede actualizar la versión instalada de PDF Familiar.")
            return
        self._actualizando = True
        try:
            instalador = self._descargar_actualizacion(nueva)
        except Exception as e:
            QMessageBox.warning(self, "Actualizar", f"No se ha podido descargar la versión nueva.\n\n{e}")
            instalador = None
        if instalador is None:
            self._actualizando = False
            return
        # Primero se cierran los PDF (pregunta si hay cambios sin guardar)
        if not self.cerrar_todos():
            self._actualizando = False
            self.statusBar().showMessage("Actualización cancelada: no se han cerrado los PDF", 6000)
            return
        actualizar.instalar(instalador)
        self.close()

    def _descargar_actualizacion(self, nueva: dict):
        from PySide6.QtWidgets import QProgressDialog

        dialogo = QProgressDialog(f"Descargando PDF Familiar {nueva['version']}…", "Cancelar", 0, 100, self)
        dialogo.setWindowTitle("Actualizar")
        dialogo.setWindowModality(Qt.WindowModality.WindowModal)
        dialogo.setMinimumDuration(0)
        estado = {"hecho": 0, "total": 0}

        def avance(hecho, total):
            estado.update(hecho=hecho, total=total)

        reloj = QTimer(self, interval=150)
        reloj.timeout.connect(
            lambda: estado["total"] and dialogo.setValue(int(100 * estado["hecho"] / estado["total"]))
        )
        reloj.start()
        try:
            return en_segundo_plano(actualizar.descargar, nueva, avance, dialogo.wasCanceled)
        finally:
            reloj.stop()
            dialogo.close()

    def dragEnterEvent(self, e):
        if any(u.toLocalFile().lower().endswith(ABRIBLES) for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if u.toLocalFile().lower().endswith(ABRIBLES):
                self.abrir(u.toLocalFile())  # cada uno en su pestaña

    def closeEvent(self, e):
        if not self.cerrar_todos():
            e.ignore()
            return
        self.ajustes.setValue("geometria", self.saveGeometry())
        super().closeEvent(e)
