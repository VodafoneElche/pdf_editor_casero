"""Cuenta de Google: enviar documentos a Google Docs y traerlos de vuelta como PDF.

Se usa solo la biblioteca estándar de Python (sin paquetes de Google):
- Inicio de sesión OAuth para aplicaciones de escritorio: se abre el navegador,
  la persona entra con su Gmail y Google devuelve un código a un servidor
  local de un solo uso (127.0.0.1). Con PKCE, como pide Google.
- Permiso "drive.file": la app solo ve los archivos que ella misma ha subido,
  no el resto del Drive.
- La sesión se guarda en %LOCALAPPDATA%\\PDFCasero\\google.json, cifrada con
  la cuenta de Windows (DPAPI) para que otro usuario del PC no pueda usarla.

El ID de cliente (google_cliente.json, descargado de Google Cloud) va en la
carpeta de recursos del programa o en %LOCALAPPDATA%\\PDFCasero.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

URL_AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
URL_TOKEN = "https://oauth2.googleapis.com/token"
URL_REVOCAR = "https://oauth2.googleapis.com/revoke"
URL_DRIVE = "https://www.googleapis.com/drive/v3"
URL_SUBIDA = "https://www.googleapis.com/upload/drive/v3/files"
PERMISO = "https://www.googleapis.com/auth/drive.file"
TIPO_DOC_GOOGLE = "application/vnd.google-apps.document"
TIPO_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TIPO_HOJA_GOOGLE = "application/vnd.google-apps.spreadsheet"
TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

PAGINA_FIN = """<!doctype html><meta charset="utf-8"><title>PDF Familiar</title>
<body style="font-family:Segoe UI,sans-serif;text-align:center;margin-top:15vh;color:#1d1d1f">
<h2>{titulo}</h2><p>{texto}</p></body>"""


class ErrorGoogle(Exception):
    """Error que se puede enseñar tal cual a la persona."""


class Cancelado(ErrorGoogle):
    pass


def carpeta_datos() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(Path.home(), ".local", "share")
    return Path(base) / "PDFCasero"


def _recursos() -> Path:
    base = getattr(sys, "_MEIPASS", None)
    return (Path(base) / "pdfcasero" if base else Path(__file__).resolve().parent) / "recursos"


def leer_cliente() -> tuple[str, str] | None:
    """(client_id, client_secret) del JSON de Google Cloud, o None si no está."""
    for ruta in (carpeta_datos() / "google_cliente.json", _recursos() / "google_cliente.json"):
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        datos = datos.get("installed") or datos.get("web") or datos
        if datos.get("client_id"):
            return datos["client_id"], datos.get("client_secret", "")
    return None


def instalar_cliente(origen: str) -> None:
    """Copia un google_cliente.json elegido por la persona a su carpeta de datos."""
    datos = json.loads(Path(origen).read_text(encoding="utf-8-sig"))
    if not (datos.get("installed") or {}).get("client_id"):
        raise ErrorGoogle("Ese archivo no es un ID de cliente de «Aplicación de escritorio» de Google Cloud.")
    carpeta_datos().mkdir(parents=True, exist_ok=True)
    (carpeta_datos() / "google_cliente.json").write_text(json.dumps(datos), encoding="utf-8")


# --- Guardar la sesión cifrada (Windows) ----------------------------------------
def _dpapi(datos: bytes, cifrar: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    entrada = BLOB(len(datos), ctypes.cast(ctypes.create_string_buffer(datos, len(datos)), ctypes.POINTER(ctypes.c_char)))
    salida = BLOB()
    funcion = ctypes.windll.crypt32.CryptProtectData if cifrar else ctypes.windll.crypt32.CryptUnprotectData
    if cifrar:
        ok = funcion(ctypes.byref(entrada), "PDFCasero", None, None, None, 0, ctypes.byref(salida))
    else:
        ok = funcion(ctypes.byref(entrada), None, None, None, None, 0, ctypes.byref(salida))
    if not ok:
        raise OSError("DPAPI")
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(salida.pbData)


def _proteger(datos: bytes) -> bytes:
    return b"dpapi:" + base64.b64encode(_dpapi(datos, True)) if sys.platform == "win32" else datos


def _desproteger(datos: bytes) -> bytes:
    if datos.startswith(b"dpapi:"):
        return _dpapi(base64.b64decode(datos[6:]), False)
    return datos


# --- Peticiones ------------------------------------------------------------------
def _peticion(url, datos=None, cabeceras=None, metodo=None, timeout=60):
    """Devuelve (cuerpo_bytes, cabeceras_respuesta). Lanza ErrorGoogle con un mensaje claro."""
    if isinstance(datos, dict):
        datos = urllib.parse.urlencode(datos).encode()
    req = urllib.request.Request(url, data=datos, headers=cabeceras or {}, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), r.headers
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace")
        try:
            detalle = json.loads(cuerpo)
            detalle = detalle.get("error_description") or (detalle.get("error") or {}).get("message") or detalle.get("error")
        except ValueError:
            detalle = cuerpo[:200]
        raise ErrorGoogle(f"Google ha respondido con un error ({e.code}): {detalle}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErrorGoogle(f"No se ha podido conectar con Google. ¿Hay internet?\n({e})") from e


class CuentaGoogle:
    def __init__(self, archivo: Path | None = None, cliente: tuple[str, str] | None = None):
        self.archivo = archivo or carpeta_datos() / "google.json"
        self._cliente = cliente
        self._acceso = None  # (token, caduca_en)
        self._datos = self._cargar()

    # Estado
    @property
    def cliente(self):
        if self._cliente is None:
            self._cliente = leer_cliente()
        return self._cliente

    @property
    def configurada(self) -> bool:
        return self.cliente is not None

    @property
    def conectada(self) -> bool:
        return bool(self._datos.get("refresh_token"))

    @property
    def correo(self) -> str:
        return self._datos.get("correo", "")

    def _cargar(self) -> dict:
        try:
            return json.loads(_desproteger(self.archivo.read_bytes()))
        except (OSError, ValueError):
            return {}

    def _guardar(self):
        self.archivo.parent.mkdir(parents=True, exist_ok=True)
        self.archivo.write_bytes(_proteger(json.dumps(self._datos).encode()))

    # Inicio de sesión
    def conectar(self, abrir=webbrowser.open, cancelado=lambda: False, espera=300) -> str:
        """Abre el navegador para entrar con Google. Devuelve el correo de la cuenta."""
        if not self.configurada:
            raise ErrorGoogle("Falta el ID de cliente de Google (google_cliente.json).")
        client_id, client_secret = self.cliente
        verificador = secrets.token_urlsafe(64)
        reto = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
        estado = secrets.token_urlsafe(16)
        respuesta = {}

        class Recibir(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if q.get("state", [""])[0] != estado:
                    self.send_response(404)
                    self.end_headers()
                    return
                respuesta.update({k: v[0] for k, v in q.items()})
                bien = "code" in q
                pagina = PAGINA_FIN.format(
                    titulo="Cuenta conectada ✔" if bien else "No se ha conectado",
                    texto="Ya puedes cerrar esta pestaña y volver a PDF Familiar." if bien
                    else "Vuelve a PDF Familiar e inténtalo otra vez.",
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(pagina.encode())

            def log_message(self, *_):
                pass

        servidor = http.server.HTTPServer(("127.0.0.1", 0), Recibir)
        servidor.timeout = 0.3
        redireccion = f"http://127.0.0.1:{servidor.server_port}"
        url = URL_AUTORIZAR + "?" + urllib.parse.urlencode({
            "client_id": client_id, "redirect_uri": redireccion, "response_type": "code",
            "scope": PERMISO, "state": estado, "code_challenge": reto,
            "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent select_account",
        })
        try:
            abrir(url)
            limite = time.monotonic() + espera
            while not respuesta:
                if cancelado():
                    raise Cancelado("Cancelado.")
                if time.monotonic() > limite:
                    raise ErrorGoogle("Se ha acabado el tiempo para iniciar sesión.")
                servidor.handle_request()
        finally:
            servidor.server_close()
        if "code" not in respuesta:
            raise ErrorGoogle("No se ha dado permiso a PDF Familiar" + (f" ({respuesta['error']})." if "error" in respuesta else "."))
        cuerpo, _ = _peticion(URL_TOKEN, {
            "code": respuesta["code"], "client_id": client_id, "client_secret": client_secret,
            "redirect_uri": redireccion, "grant_type": "authorization_code", "code_verifier": verificador,
        })
        tokens = json.loads(cuerpo)
        if not tokens.get("refresh_token"):
            raise ErrorGoogle("Google no ha devuelto la sesión. Inténtalo otra vez.")
        self._datos = {"refresh_token": tokens["refresh_token"]}
        self._acceso = (tokens["access_token"], time.time() + int(tokens.get("expires_in", 3600)) - 60)
        info = self._api("GET", URL_DRIVE + "/about?fields=user(emailAddress)")
        self._datos["correo"] = info.get("user", {}).get("emailAddress", "")
        self._guardar()
        return self.correo

    def desconectar(self):
        token = self._datos.get("refresh_token")
        self._datos, self._acceso = {}, None
        try:
            self.archivo.unlink()
        except OSError:
            pass
        if token:
            try:
                _peticion(URL_REVOCAR, {"token": token}, timeout=10)
            except ErrorGoogle:
                pass  # sin internet: la sesión local ya está borrada

    def _token(self) -> str:
        if self._acceso and time.time() < self._acceso[1]:
            return self._acceso[0]
        if not self.conectada:
            raise ErrorGoogle("No hay ninguna cuenta de Google conectada.")
        client_id, client_secret = self.cliente
        try:
            cuerpo, _ = _peticion(URL_TOKEN, {
                "refresh_token": self._datos["refresh_token"], "client_id": client_id,
                "client_secret": client_secret, "grant_type": "refresh_token",
            })
        except ErrorGoogle as e:
            if "invalid_grant" in str(e) or "(400)" in str(e):
                self.desconectar()
                raise ErrorGoogle("La sesión de Google ha caducado. Vuelve a conectar la cuenta.") from e
            raise
        t = json.loads(cuerpo)
        self._acceso = (t["access_token"], time.time() + int(t.get("expires_in", 3600)) - 60)
        return self._acceso[0]

    def _api(self, metodo, url, datos=None, cabeceras=None, crudo=False, timeout=120):
        h = {"Authorization": f"Bearer {self._token()}", **(cabeceras or {})}
        cuerpo, resp = _peticion(url, datos, h, metodo, timeout=timeout)
        if crudo:
            return cuerpo, resp
        return json.loads(cuerpo) if cuerpo else {}

    # Drive
    def subir(self, ruta: str, nombre: str, tipo_archivo: str, tipo_google: str) -> dict:
        """Sube un archivo convirtiéndolo al tipo de Google indicado. Devuelve {id, name, webViewLink}."""
        meta = json.dumps({"name": nombre, "mimeType": tipo_google}).encode()
        _, resp = self._api(
            "POST", URL_SUBIDA + "?uploadType=resumable&fields=id,name,webViewLink", meta,
            {"Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": tipo_archivo},
            crudo=True,
        )
        destino = resp.get("Location")
        if not destino:
            raise ErrorGoogle("Google no ha aceptado la subida.")
        datos = Path(ruta).read_bytes()
        cuerpo, _ = self._api("PUT", destino, datos, {"Content-Type": tipo_archivo}, crudo=True, timeout=600)
        return json.loads(cuerpo)

    def subir_como_doc(self, ruta_docx: str, nombre: str) -> dict:
        """Un .docx convertido en Documento de Google."""
        return self.subir(ruta_docx, nombre, TIPO_DOCX, TIPO_DOC_GOOGLE)

    def subir_como_hoja(self, ruta_xlsx: str, nombre: str) -> dict:
        """Un .xlsx convertido en Hoja de cálculo de Google."""
        return self.subir(ruta_xlsx, nombre, TIPO_XLSX, TIPO_HOJA_GOOGLE)

    def documentos(self) -> list[dict]:
        """Documentos y hojas de cálculo de Google que ve la app (los que ha subido ella), del más reciente al más antiguo."""
        q = urllib.parse.urlencode({
            "q": f"(mimeType='{TIPO_DOC_GOOGLE}' or mimeType='{TIPO_HOJA_GOOGLE}') and trashed=false",
            "orderBy": "modifiedTime desc", "pageSize": "100",
            "fields": "files(id,name,mimeType,modifiedTime,webViewLink)",
        })
        return self._api("GET", f"{URL_DRIVE}/files?{q}").get("files", [])

    def descargar_pdf(self, id_doc: str) -> bytes:
        """El Documento u Hoja de cálculo de Google convertido a PDF por el propio Google."""
        q = urllib.parse.urlencode({"mimeType": "application/pdf"})
        cuerpo, _ = self._api("GET", f"{URL_DRIVE}/files/{id_doc}/export?{q}", crudo=True, timeout=300)
        return cuerpo

