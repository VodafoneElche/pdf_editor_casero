"""Prueba la cuenta de Google contra un servidor falso que imita a Google."""

import http.server
import json
import threading
import urllib.parse
import urllib.request

import pymupdf
import pytest

from pdfcasero import google


class FalsoGoogle(http.server.BaseHTTPRequestHandler):
    archivos = {}
    tipos = {}
    tokens = []
    revocados = []

    def log_message(self, *_):
        pass

    def _json(self, datos, codigo=200, cabeceras=None):
        cuerpo = json.dumps(datos).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        for k, v in (cabeceras or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _cuerpo(self):
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def _autorizado(self):
        if self.headers.get("Authorization") != "Bearer ACCESO":
            self._json({"error": {"message": "sin permiso"}}, 401)
            return False
        return True

    def do_POST(self):
        ruta = urllib.parse.urlparse(self.path)
        if ruta.path == "/token":
            datos = urllib.parse.parse_qs(self._cuerpo().decode())
            FalsoGoogle.tokens.append({k: v[0] for k, v in datos.items()})
            if datos["grant_type"] == ["authorization_code"]:
                assert datos["code"] == ["CODIGO"] and datos["code_verifier"]
                return self._json({"access_token": "ACCESO", "refresh_token": "REFRESCO", "expires_in": 3600})
            assert datos["refresh_token"] == ["REFRESCO"]
            return self._json({"access_token": "ACCESO", "expires_in": 3600})
        if ruta.path == "/revoke":
            FalsoGoogle.revocados.append(self._cuerpo())
            return self._json({})
        if ruta.path == "/upload" and self._autorizado():
            meta = json.loads(self._cuerpo())
            origen = {google.TIPO_DOC_GOOGLE: google.TIPO_DOCX, google.TIPO_HOJA_GOOGLE: google.TIPO_XLSX}[meta["mimeType"]]
            assert self.headers["X-Upload-Content-Type"] == origen
            FalsoGoogle.tipos[meta["name"]] = meta["mimeType"]
            return self._json({}, cabeceras={"Location": f"http://127.0.0.1:{self.server.server_port}/sesion/{meta['name']}"})

    def do_PUT(self):
        if self.path.startswith("/sesion/") and self._autorizado():
            nombre = urllib.parse.unquote(self.path.split("/")[-1])
            datos = self._cuerpo()
            id_ = f"id{len(self.archivos)}"
            FalsoGoogle.archivos[id_] = (nombre, datos)
            return self._json({"id": id_, "name": nombre, "webViewLink": f"https://docs.google.com/{id_}"})

    def do_GET(self):
        if not self._autorizado():
            return
        ruta = urllib.parse.urlparse(self.path)
        if ruta.path == "/drive/about":
            return self._json({"user": {"emailAddress": "familia@gmail.com"}})
        if ruta.path == "/drive/files":
            return self._json({"files": [{"id": k, "name": v[0], "mimeType": self.tipos[v[0]], "modifiedTime": "2026-10-27T10:00:00Z"} for k, v in self.archivos.items()]})
        if ruta.path.endswith("/export"):
            id_ = ruta.path.split("/")[-2]
            doc = pymupdf.open()
            doc.new_page().insert_text((72, 72), f"Documento {self.archivos[id_][0]}")
            cuerpo = doc.tobytes()
            self.send_response(200)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)


@pytest.fixture
def falso(monkeypatch):
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FalsoGoogle)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{servidor.server_port}"
    monkeypatch.setattr(google, "URL_TOKEN", base + "/token")
    monkeypatch.setattr(google, "URL_REVOCAR", base + "/revoke")
    monkeypatch.setattr(google, "URL_DRIVE", base + "/drive")
    monkeypatch.setattr(google, "URL_SUBIDA", base + "/upload")
    FalsoGoogle.archivos, FalsoGoogle.tipos, FalsoGoogle.tokens, FalsoGoogle.revocados = {}, {}, [], []
    yield base
    servidor.shutdown()


def navegador_que_acepta(url):
    """Hace de navegador: la persona entra y Google redirige con el código."""
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q["scope"] == [google.PERMISO] and q["code_challenge_method"] == ["S256"]
    vuelta = q["redirect_uri"][0] + "?" + urllib.parse.urlencode({"code": "CODIGO", "state": q["state"][0]})
    threading.Thread(target=lambda: urllib.request.urlopen(vuelta, timeout=5).read(), daemon=True).start()


def test_conectar_subir_listar_y_traer_pdf(falso, tmp_path):
    archivo = tmp_path / "google.json"
    cuenta = google.CuentaGoogle(archivo, cliente=("ID", "SECRETO"))
    assert cuenta.configurada and not cuenta.conectada
    assert cuenta.conectar(abrir=navegador_que_acepta, espera=10) == "familia@gmail.com"
    assert archivo.is_file()
    if google.sys.platform == "win32":  # cifrada con la cuenta de Windows
        assert b"REFRESCO" not in archivo.read_bytes()

    # Otra vez abierta la app: recuerda la sesión y renueva el acceso sola
    cuenta = google.CuentaGoogle(archivo, cliente=("ID", "SECRETO"))
    assert cuenta.conectada and cuenta.correo == "familia@gmail.com"
    docx = tmp_path / "carta.docx"
    docx.write_bytes(b"PK falso docx")
    subido = cuenta.subir_como_doc(str(docx), "Carta")
    assert subido["webViewLink"].startswith("https://docs.google.com/")
    assert FalsoGoogle.tokens[-1]["grant_type"] == "refresh_token"
    assert FalsoGoogle.archivos[subido["id"]] == ("Carta", b"PK falso docx")

    xlsx = tmp_path / "gastos.xlsx"
    xlsx.write_bytes(b"PK falso xlsx")
    cuenta.subir_como_hoja(str(xlsx), "Gastos")

    docs = cuenta.documentos()
    assert [(d["name"], d["mimeType"]) for d in docs] == [("Carta", google.TIPO_DOC_GOOGLE), ("Gastos", google.TIPO_HOJA_GOOGLE)]
    pdf = pymupdf.open(stream=cuenta.descargar_pdf(docs[0]["id"]), filetype="pdf")
    assert "Documento Carta" in pdf[0].get_text()

    cuenta.desconectar()
    assert not cuenta.conectada and not archivo.exists() and FalsoGoogle.revocados


def test_cancelar_el_inicio_de_sesion(falso, tmp_path):
    cuenta = google.CuentaGoogle(tmp_path / "g.json", cliente=("ID", "SECRETO"))
    with pytest.raises(google.Cancelado):
        cuenta.conectar(abrir=lambda url: None, cancelado=lambda: True, espera=10)
    assert not cuenta.conectada


def test_permiso_denegado(falso, tmp_path):
    def deniega(url):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        vuelta = q["redirect_uri"][0] + "?" + urllib.parse.urlencode({"error": "access_denied", "state": q["state"][0]})
        threading.Thread(target=lambda: urllib.request.urlopen(vuelta, timeout=5).read(), daemon=True).start()

    cuenta = google.CuentaGoogle(tmp_path / "g.json", cliente=("ID", "SECRETO"))
    with pytest.raises(google.ErrorGoogle, match="permiso"):
        cuenta.conectar(abrir=deniega, espera=10)


def test_leer_e_instalar_cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    origen = tmp_path / "descargado.json"
    origen.write_text(json.dumps({"installed": {"client_id": "abc.apps.googleusercontent.com", "client_secret": "s"}}))
    google.instalar_cliente(str(origen))
    assert google.leer_cliente() == ("abc.apps.googleusercontent.com", "s")
    malo = tmp_path / "malo.json"
    malo.write_text("{}")
    with pytest.raises(google.ErrorGoogle):
        google.instalar_cliente(str(malo))
