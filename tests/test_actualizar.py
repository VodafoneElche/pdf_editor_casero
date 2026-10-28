"""Buscar e instalar versiones nuevas desde GitHub Releases."""

import io
import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pdfcasero import actualizar


class Respuesta(io.BytesIO):
    def __init__(self, datos: bytes):
        super().__init__(datos)
        self.headers = {"Content-Length": str(len(datos))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def publicada(version, nombre=None, url=None, tamano=5):
    nombre = nombre or f"PDFCasero-Instalador-{version}.exe"
    url = url or f"{actualizar.DESCARGAS}v{version}/{nombre}"
    return json.dumps({"tag_name": f"v{version}", "assets": [{"name": nombre, "browser_download_url": url, "size": tamano}]}).encode()


def test_numero_de_version():
    assert actualizar.numero("v1.0.31") == (1, 0, 31)
    assert actualizar.numero("1.0.9") < actualizar.numero("1.0.10")


def test_encuentra_version_nueva(monkeypatch):
    monkeypatch.setattr(actualizar, "_pedir", lambda url, tiempo=15: Respuesta(publicada("1.0.31")))
    nueva = actualizar.buscar_nueva("1.0.30")
    assert nueva["version"] == "1.0.31" and nueva["nombre"] == "PDFCasero-Instalador-1.0.31.exe"
    assert actualizar.buscar_nueva("1.0.31") is None
    assert actualizar.buscar_nueva("1.1.0") is None


def test_solo_acepta_el_instalador_de_este_repositorio(monkeypatch):
    raro = publicada("2.0.1", url="https://ejemplo.com/PDFCasero-Instalador-2.0.1.exe")
    monkeypatch.setattr(actualizar, "_pedir", lambda url, tiempo=15: Respuesta(raro))
    assert actualizar.buscar_nueva("1.0.30") is None
    otro = publicada("2.0.1", nombre="virus.exe")
    monkeypatch.setattr(actualizar, "_pedir", lambda url, tiempo=15: Respuesta(otro))
    assert actualizar.buscar_nueva("1.0.30") is None


def test_descarga_completa_y_cortada(monkeypatch, tmp_path):
    monkeypatch.setattr(actualizar.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(actualizar, "_pedir", lambda url, tiempo=15: Respuesta(b"12345"))
    nueva = {"version": "1.0.31", "url": "x", "nombre": "PDFCasero-Instalador-1.0.31.exe", "tamano": 5}
    ruta = actualizar.descargar(nueva)
    assert ruta.read_bytes() == b"12345"
    with pytest.raises(OSError):
        actualizar.descargar(dict(nueva, tamano=9))
    assert actualizar.descargar(nueva, cancelado=lambda: True) is None


def test_la_ventana_ofrece_actualizar(monkeypatch, tmp_path):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QMessageBox

    monkeypatch.setattr(QSettings, "value", lambda self, clave, defecto=None, **_: defecto)
    monkeypatch.setattr(QSettings, "setValue", lambda *a, **k: None)
    from pdfcasero.ventana import VentanaPrincipal

    app = QApplication.instance() or QApplication([])
    v = VentanaPrincipal()
    v.show()
    textos, lanzado = [], []
    nueva = {"version": "9.0.1", "url": "x", "nombre": "PDFCasero-Instalador-9.0.1.exe", "tamano": 1}

    def responder(caja):
        textos.append(caja.text())
        caja._pulsado = caja.buttons()[0]  # «Actualizar ahora»
        return 0

    monkeypatch.setattr(QMessageBox, "exec", responder)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda caja: caja._pulsado)
    monkeypatch.setattr(actualizar, "instalada", lambda: True)
    monkeypatch.setattr(actualizar, "descargar", lambda n, avance, cancelado: tmp_path / n["nombre"])
    monkeypatch.setattr(actualizar, "instalar", lambda ruta: lanzado.append(ruta))
    v._ofrecer_actualizacion(nueva)
    assert "9.0.1" in textos[0]
    assert lanzado == [tmp_path / "PDFCasero-Instalador-9.0.1.exe"]
    assert not v.isVisible()
    app.processEvents()
