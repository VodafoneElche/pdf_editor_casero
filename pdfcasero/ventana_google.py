"""Botón «Google» de la ventana: conectar la cuenta, enviar a Docs u Hojas de cálculo y traer como PDF."""

from __future__ import annotations

import tempfile
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QToolButton,
    QVBoxLayout,
)

from . import conversion, google
from .documento import Documento

AYUDA_CONFIGURAR = (
    "Para conectar con Google hace falta, una sola vez, el archivo «google_cliente.json» "
    "(ID de cliente OAuth de tipo «Aplicación de escritorio» creado en console.cloud.google.com, "
    "con la API de Google Drive habilitada).\n\n¿Quieres elegir ese archivo ahora?"
)


def con_espera(padre, titulo: str, texto: str, funcion, *args, cancelable: bool = False):
    """Ejecuta funcion(*args, cancelado=...) en otro hilo con un aviso de espera.

    Devuelve su resultado, lanza su error, o google.Cancelado si se pulsa Cancelar.
    """
    evento = threading.Event()
    resultado = {}

    def trabajo():
        try:
            if cancelable:
                resultado["valor"] = funcion(*args, cancelado=evento.is_set)
            else:
                resultado["valor"] = funcion(*args)
        except Exception as e:
            resultado["error"] = e

    dialogo = QProgressDialog(texto, "Cancelar" if cancelable else None, 0, 0, padre)
    dialogo.setWindowTitle(titulo)
    dialogo.setWindowModality(Qt.WindowModality.WindowModal)
    dialogo.setMinimumDuration(300)
    if not cancelable:
        dialogo.setCancelButton(None)
    hilo = threading.Thread(target=trabajo, daemon=True)
    hilo.start()
    bucle = QEventLoop()

    def comprobar():
        if dialogo.wasCanceled():
            evento.set()
        if not hilo.is_alive():
            bucle.quit()

    reloj = QTimer(interval=100)
    reloj.timeout.connect(comprobar)
    reloj.start()
    bucle.exec()
    reloj.stop()
    dialogo.close()
    if "error" in resultado:
        raise resultado["error"]
    return resultado.get("valor")


class ElegirDocumento(QDialog):
    def __init__(self, padre, documentos: list[dict], correo: str):
        super().__init__(padre)
        self.setWindowTitle("Traer de Google")
        self.resize(480, 420)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Documentos y hojas de cálculo enviados desde PDF Casero a <b>{correo}</b>:"))
        self.lista = QListWidget()
        for d in documentos:
            tipo = "Hoja de cálculo" if d.get("mimeType") == google.TIPO_HOJA_GOOGLE else "Documento"
            it = QListWidgetItem(f"{d['name']}    ·    {tipo}    ·    {_fecha(d.get('modifiedTime', ''))}")
            it.setData(Qt.ItemDataRole.UserRole, d)
            self.lista.addItem(it)
        self.lista.setCurrentRow(0)
        self.lista.itemActivated.connect(lambda _: self.accept())
        lay.addWidget(self.lista)
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
        botones.button(QDialogButtonBox.StandardButton.Open).setText("Abrir como PDF")
        botones.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        lay.addWidget(botones)

    def elegido(self) -> dict | None:
        it = self.lista.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None


def _fecha(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return ""


class ControlGoogle:
    """Lo que hace el botón «Google» de la barra."""

    def __init__(self, ventana):
        self.ventana = ventana
        self.cuenta = google.CuentaGoogle()
        self.menu = QMenu(ventana)
        self.menu.aboutToShow.connect(self._rellenar_menu)
        self.boton = QToolButton()
        self.boton.setText("Google")
        self.boton.setToolTip("Editar en Google Docs u Hojas de cálculo con tu Gmail y traerlo de vuelta como PDF")
        self.boton.setMenu(self.menu)
        self.boton.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

    def _rellenar_menu(self):
        m, v = self.menu, self.ventana
        m.clear()
        enviar = m.addAction("Enviar a Google Docs para editar", self.enviar)
        enviar.setEnabled(v.doc is not None)
        hoja = m.addAction("Enviar tablas a Hojas de cálculo de Google", self.enviar_hoja)
        hoja.setEnabled(v.doc is not None)
        m.addAction("Traer de Google como PDF…", self.traer)
        m.addSeparator()
        guardar = m.addAction("Guardar copia en Word (.docx)…", v.exportar_word)
        guardar.setEnabled(v.doc is not None)
        m.addSeparator()
        if self.cuenta.conectada:
            m.addAction(f"Cuenta: {self.cuenta.correo or 'conectada'}").setEnabled(False)
            m.addAction("Cambiar de cuenta…", self.cambiar_cuenta)
            m.addAction("Desconectar la cuenta", self.desconectar)
        else:
            m.addAction("Conectar cuenta de Google…", self.conectar)

    # Cuenta
    def _configurar(self) -> bool:
        if self.cuenta.configurada:
            return True
        if QMessageBox.question(self.ventana, "Configurar Google", AYUDA_CONFIGURAR) != QMessageBox.StandardButton.Yes:
            return False
        ruta, _ = QFileDialog.getOpenFileName(self.ventana, "Elegir google_cliente.json", str(Path.home() / "Downloads"), "JSON (*.json)")
        if not ruta:
            return False
        try:
            google.instalar_cliente(ruta)
        except (OSError, ValueError, google.ErrorGoogle) as e:
            QMessageBox.critical(self.ventana, "Configurar Google", str(e))
            return False
        self.cuenta = google.CuentaGoogle()
        return self.cuenta.configurada

    def conectar(self) -> bool:
        if not self._configurar():
            return False
        try:
            correo = con_espera(
                self.ventana, "Conectar con Google",
                "Se ha abierto el navegador.\nEntra con tu cuenta de Gmail y pulsa «Permitir».",
                self.cuenta.conectar, cancelable=True,
            )
        except google.Cancelado:
            return False
        except google.ErrorGoogle as e:
            QMessageBox.critical(self.ventana, "Conectar con Google", str(e))
            return False
        self.ventana.statusBar().showMessage(f"Cuenta de Google conectada: {correo}", 8000)
        return True

    def _asegurar_conexion(self) -> bool:
        return self.cuenta.conectada or self.conectar()

    def cambiar_cuenta(self):
        self.cuenta.desconectar()
        self.conectar()

    def desconectar(self):
        texto = f"¿Desconectar {self.cuenta.correo} de PDF Casero en este ordenador?\nTus documentos siguen en Google Drive."
        if QMessageBox.question(self.ventana, "Desconectar", texto) == QMessageBox.StandardButton.Yes:
            self.cuenta.desconectar()
            self.ventana.statusBar().showMessage("Cuenta de Google desconectada", 5000)

    def _con_cuenta(self, titulo, texto, funcion, *args):
        """Como con_espera, enseñando los errores de Google. None si ha fallado."""
        try:
            return con_espera(self.ventana, titulo, texto, funcion, *args)
        except google.ErrorGoogle as e:
            QMessageBox.critical(self.ventana, titulo, str(e))
            return None

    # Enviar y traer
    def enviar(self):
        v = self.ventana
        if not v.doc or not self._asegurar_conexion():
            return
        nombre = v.doc.ruta.stem
        docx = Path(tempfile.mkdtemp(prefix="pdfcasero_")) / f"{nombre}.docx"
        if not v.convertir_a_docx(str(docx)):
            return
        subido = self._con_cuenta(
            "Enviar a Google Docs", f"Subiendo «{nombre}» a tu Google Drive…", self.cuenta.subir_como_doc, str(docx), nombre
        )
        docx.unlink(missing_ok=True)
        if not subido:
            return
        enlace = subido.get("webViewLink") or f"https://docs.google.com/document/d/{subido['id']}/edit"
        webbrowser.open(enlace)
        QMessageBox.information(
            v, "Enviado a Google Docs",
            f"«{nombre}» se ha abierto en Google Docs ({self.cuenta.correo}).\n\n"
            "Cuando termines de editarlo, vuelve aquí y pulsa\nGoogle → Traer de Google como PDF.",
        )

    def enviar_hoja(self):
        v = self.ventana
        if not v.doc or not self._asegurar_conexion():
            return
        nombre = v.doc.ruta.stem
        xlsx = Path(tempfile.mkdtemp(prefix="pdfcasero_")) / f"{nombre}.xlsx"
        try:
            tablas = con_espera(
                v, "Enviar a Hojas de cálculo", "Buscando las tablas del PDF…",
                conversion.pdf_a_excel, v.doc.copia_en_memoria(), str(xlsx), cancelable=True,
            )
        except InterruptedError:
            return
        except Exception as e:
            QMessageBox.critical(v, "Enviar a Hojas de cálculo", f"No se han podido sacar las tablas.\n\n{e}")
            return
        subido = self._con_cuenta(
            "Enviar a Hojas de cálculo", f"Subiendo «{nombre}» a tu Google Drive…", self.cuenta.subir_como_hoja, str(xlsx), nombre
        )
        xlsx.unlink(missing_ok=True)
        if not subido:
            return
        webbrowser.open(subido.get("webViewLink") or f"https://docs.google.com/spreadsheets/d/{subido['id']}/edit")
        if tablas:
            detalle = f"Se han pasado {tablas} tablas (una pestaña por página)."
        else:
            detalle = "No se han encontrado tablas: cada línea de texto va en una fila."
        QMessageBox.information(
            v, "Enviado a Hojas de cálculo",
            f"«{nombre}» se ha abierto en Hojas de cálculo de Google ({self.cuenta.correo}).\n{detalle}\n\n"
            "Para tenerlo en PDF, pulsa Google → Traer de Google como PDF.",
        )

    def traer(self):
        v = self.ventana
        if not self._asegurar_conexion():
            return
        documentos = self._con_cuenta("Traer de Google", "Buscando tus documentos…", self.cuenta.documentos)
        if documentos is None:
            return
        if not documentos:
            QMessageBox.information(
                v, "Traer de Google",
                "Todavía no hay documentos enviados desde PDF Casero con esta cuenta.\n\n"
                "Abre un PDF y pulsa Google → Enviar a Google Docs o Enviar tablas a Hojas de cálculo.",
            )
            return
        dialogo = ElegirDocumento(v, documentos, self.cuenta.correo)
        if dialogo.exec() != QDialog.DialogCode.Accepted or not (elegido := dialogo.elegido()):
            return
        datos = self._con_cuenta(
            "Traer de Google", f"Descargando «{elegido['name']}» como PDF…", self.cuenta.descargar_pdf, elegido["id"]
        )
        if not datos:
            return
        nombre = "".join(c for c in elegido["name"] if c not in '<>:"/\\|?*').strip() or "documento"
        tmp = Path(tempfile.mkdtemp(prefix="pdfcasero_")) / f"{nombre}.pdf"
        tmp.write_bytes(datos)
        doc = Documento(tmp)
        carpeta = Path(v.ajustes.value("ultima_carpeta", str(Path.home() / "Documents")))
        doc.ruta = carpeta / f"{nombre}.pdf"  # al guardar se propone este nombre
        doc.nuevo = True
        doc.modificado = True
        if v._mostrar_documento(doc, str(doc.ruta), reciente=False):
            v.statusBar().showMessage("Traído de Google. Pulsa Guardar para guardarlo como PDF.", 15000)
