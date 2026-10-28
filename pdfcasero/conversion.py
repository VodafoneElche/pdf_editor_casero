"""Pasar de PDF a Word (.docx) y de Word a PDF.

- PDF → Word: con pdf2docx, que reconstruye párrafos, tablas e imágenes. El
  .docx se puede subir a Google Drive y abrir con Documentos de Google.
- Word → PDF: si el ordenador tiene Microsoft Word, se usa Word (resultado
  idéntico). Si no, se convierte con mammoth (texto, tablas, listas e
  imágenes) y PyMuPDF; el diseño puede variar un poco.
"""

from __future__ import annotations

import io
import multiprocessing
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf

EXTENSIONES_WORD = (".docx",)


# --- PDF → Word ------------------------------------------------------------------
# Fuentes de código de barras: su "texto" no son letras, así que se pasan como imagen
_FUENTE_CODIGO = re.compile(r"code ?128|code ?39|3 ?of ?9|ean ?13|upc|barcode|bar ?code|interleaved|i2of5|postnet|datamatrix", re.I)
# Fuentes que Google Docs y Word tienen siempre; el resto se cambia por una parecida
_FUENTES_COMUNES = {
    "arial", "times new roman", "courier new", "calibri", "cambria", "verdana", "georgia",
    "trebuchet ms", "tahoma", "comic sans ms", "roboto", "open sans", "garamond",
}


def _clave_fuente(nombre: str) -> str:
    """"VodafoneRg-Bold", "ABCDEF+VodafoneRg" y "Vodafone Rg" → "vodafonerg"."""
    nombre = nombre.split("+")[-1]
    nombre = re.sub(r"[-,](regular|roman|bold|italic|oblique|light|medium|semibold|black|boldmt|mt|italicmt|bolditalic|bolditalicmt)$", "", nombre, flags=re.I)
    return re.sub(r"[^a-z0-9]", "", nombre.lower())


def _sustituta(nombre: str) -> str:
    n = nombre.lower()
    if any(k in n for k in ("cour", "mono", "consol")):
        return "Courier New"
    if any(k in n for k in ("times", "serif", "roman", "garamond", "georgia", "book", "minion")) and "sans" not in n:
        return "Times New Roman"
    return "Arial"


def preparar_para_word(datos_pdf: bytes) -> tuple[bytes, dict]:
    """Retoca el PDF para que el Word salga mejor y mide las fuentes.

    - Los códigos de barras (fuentes especiales) y el texto girado se cambian por
      su imagen: convertidos a texto salían letras sin sentido.
    - Devuelve, por cada fuente poco común, la sustituta y cuánto hay que
      reducir el tamaño para que el texto ocupe lo mismo que en el PDF (Arial es
      más ancha que muchas fuentes de empresa, y si no los recuadros se desbordan).
    """
    doc = pymupdf.open(stream=datos_pdf, filetype="pdf")
    referencia = {"Arial": pymupdf.Font("helv"), "Times New Roman": pymupdf.Font("tiro"), "Courier New": pymupdf.Font("cour")}
    medidas: dict[str, list] = {}
    for pagina in doc:
        zonas = []
        for bloque in pagina.get_text("dict")["blocks"]:
            for linea in bloque.get("lines", []):
                girada = abs(linea["dir"][0] - 1) > 0.01
                for span in linea["spans"]:
                    if not span["text"].strip():
                        continue
                    if girada or _FUENTE_CODIGO.search(span["font"]):
                        zonas.append(pymupdf.Rect(span["bbox"]) + (-1, -1, 1, 1))
                        continue
                    if len(span["text"].strip()) < 3:
                        continue
                    clave = _clave_fuente(span["font"])
                    sustituta = _sustituta(span["font"])
                    ancho_pdf = span["bbox"][2] - span["bbox"][0]
                    ancho_sustituta = referencia[sustituta].text_length(span["text"], span["size"])
                    m = medidas.setdefault(clave, [sustituta, 0.0, 0.0])
                    m[1] += ancho_pdf
                    m[2] += ancho_sustituta
        if zonas:
            fotos = [(r, pagina.get_pixmap(clip=r, dpi=200)) for r in zonas]
            for r in zonas:
                pagina.add_redact_annot(r)
            pagina.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
            for r, foto in fotos:
                pagina.insert_image(r, pixmap=foto)
    fuentes = {
        clave: (sustituta, max(0.6, min(1.0, 0.95 * pdf / otra)))  # 5 % de margen
        for clave, (sustituta, pdf, otra) in medidas.items()
        if otra > 0 and clave not in {_clave_fuente(f) for f in _FUENTES_COMUNES}
    }
    return doc.tobytes(garbage=3, deflate=True), fuentes


def ajustar_docx(ruta: str, fuentes: dict) -> None:
    """Retoca el .docx para que se vea bien en Google Docs y Word.

    - Cambia las fuentes poco comunes por su sustituta, con el tamaño corregido.
    - El interlineado fijo pasa a "como mínimo": con una fuente algo distinta,
      los renglones se montaban unos encima de otros.
    """
    import zipfile

    from lxml import etree

    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    q = lambda n: f"{{{w}}}{n}"  # noqa: E731
    with zipfile.ZipFile(ruta) as z:
        partes = {n: z.read(n) for n in z.namelist()}
    for nombre in [n for n in partes if re.match(r"word/(document|header\d*|footer\d*|styles)\.xml$", n)]:
        raiz = etree.fromstring(partes[nombre])
        cambios = 0
        for rpr in raiz.iter(q("rPr")):
            letra = rpr.find(q("rFonts"))
            if letra is None:
                continue
            original = letra.get(q("ascii")) or letra.get(q("hAnsi")) or ""
            ajuste = fuentes.get(_clave_fuente(original))
            if not ajuste:
                continue
            sustituta, factor = ajuste
            for atributo in ("ascii", "hAnsi", "eastAsia", "cs"):
                letra.set(q(atributo), sustituta)
            for etiqueta in ("sz", "szCs"):
                tam = rpr.find(q(etiqueta))
                if tam is not None and tam.get(q("val"), "").replace(".", "").isdigit():
                    tam.set(q("val"), str(max(8, round(float(tam.get(q("val"))) * factor))))
            cambios += 1
        for nodo in raiz.iter(q("spacing")):
            if nodo.get(q("lineRule")) == "exact":
                nodo.set(q("lineRule"), "atLeast")
                cambios += 1
        if cambios:
            partes[nombre] = etree.tostring(raiz, xml_declaration=True, encoding="UTF-8", standalone=True)
    temporal = ruta + ".tmp"
    with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, datos in partes.items():
            z.writestr(nombre, datos)
    os.replace(temporal, ruta)


class _Avance:
    """Lee las líneas "(3/88) Page 3" del registro de pdf2docx para enseñar el progreso."""

    def __init__(self, aviso):
        import logging

        class Manejador(logging.Handler):
            fase = 0

            def emit(self, registro):
                texto = registro.getMessage()
                if "Parsing pages" in texto:
                    Manejador.fase = 1
                elif "Creating pages" in texto:
                    Manejador.fase = 2
                m = re.match(r"\((\d+)/(\d+)\)", texto)
                if m and Manejador.fase:
                    aviso(Manejador.fase, int(m.group(1)), int(m.group(2)))

        self.manejador = Manejador(logging.INFO)
        raiz = logging.getLogger()
        raiz.handlers = [self.manejador]
        raiz.setLevel(logging.INFO)


def pdf_a_word(origen: str, destino: str, paginas: list[int] | None = None, aviso=None) -> None:
    """Convierte el PDF `origen` en el .docx `destino` (puede tardar en PDF largos).

    `paginas`: solo esas páginas (empezando en 0). `aviso(fase, i, total)`: progreso.
    """
    import logging

    from pdf2docx import Converter

    datos = Path(origen).read_bytes()
    if paginas is not None:
        completo = pymupdf.open(stream=datos, filetype="pdf")
        parte = pymupdf.open()
        for n in paginas:
            parte.insert_pdf(completo, from_page=n, to_page=n)
        datos = parte.tobytes()
    datos, fuentes = preparar_para_word(datos)
    preparado = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    preparado.write(datos)
    preparado.close()
    if aviso:
        _Avance(aviso)
    else:
        logging.getLogger().setLevel(logging.WARNING)  # pdf2docx escribe mucho en el registro
    try:
        conversor = Converter(preparado.name)
        try:
            conversor.convert(destino)
        finally:
            conversor.close()
    finally:
        os.remove(preparado.name)
    ajustar_docx(destino, fuentes)


def _proceso_pdf_a_word(origen: str, destino: str, cola, paginas=None, sencillo=True) -> None:
    try:
        if sencillo:
            from .word_sencillo import pdf_a_word_sencillo

            with open(origen, "rb") as f:
                datos = f.read()
            pdf_a_word_sencillo(datos, destino, paginas, avance=lambda i, total: cola.put(("avance", 0, i, total)))
        else:
            pdf_a_word(origen, destino, paginas, aviso=lambda fase, i, total: cola.put(("avance", fase, i, total)))
        cola.put(("ok", destino))
    except Exception as e:  # el mensaje lo enseña la ventana
        cola.put(("error", f"{type(e).__name__}: {e}"))


class ExportacionWord:
    """Exportación en un proceso aparte, para que la ventana no se congele y se pueda cancelar."""

    def __init__(self, datos_pdf: bytes, destino: str, paginas: list[int] | None = None, sencillo: bool = True):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        self._tmp.write(datos_pdf)
        self._tmp.close()
        # (fase, página, total): fase 1 = analizando, 2 = creando; 0 = conversor sencillo (una sola fase)
        self.avance = None
        contexto = multiprocessing.get_context("spawn")
        self._cola = contexto.Queue()
        self._proceso = contexto.Process(
            target=_proceso_pdf_a_word, args=(self._tmp.name, destino, self._cola, paginas, sencillo), daemon=True
        )
        self._proceso.start()

    def resultado(self):
        """None mientras trabaja (ver `avance`); luego ("ok", ruta) o ("error", mensaje)."""
        while not self._cola.empty():
            r = self._cola.get()
            if r[0] == "avance":
                self.avance = r[1:]
                continue
            self._limpiar()
            return r
        if not self._proceso.is_alive():
            if not self._cola.empty():
                return self.resultado()
            self._limpiar()
            return ("error", "La conversión se ha detenido sin terminar.")
        return None

    def cancelar(self):
        if self._proceso.is_alive():
            self._proceso.terminate()
        self._limpiar()

    def _limpiar(self):
        try:
            os.remove(self._tmp.name)
        except OSError:
            pass


# --- PDF → hoja de cálculo ---------------------------------------------------------
_NUMERO = re.compile(r"^-?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?\s*(€|%)?$")


def _valor(texto: str):
    """Convierte "1.028,26 €" en el número 1028.26 (formato español); el resto queda como texto."""
    t = " ".join(texto.split())
    if not _NUMERO.match(t):
        return t or None
    simbolo = t[-1] if t[-1] in "€%" else ""
    numero = float(t.rstrip("€% ").replace(".", "").replace(",", "."))
    return (numero / 100 if simbolo == "%" else numero), simbolo


def pdf_a_excel(datos_pdf: bytes, destino: str, cancelado=lambda: False, avance=lambda n, total: None) -> int:
    """Pasa el PDF a un .xlsx como iLovePDF: una pestaña por página, cada dato en su casilla
    y las imágenes encima (ver hoja_sencilla). Devuelve cuántas casillas tienen datos."""
    from .hoja_sencilla import pdf_a_hoja

    return pdf_a_hoja(datos_pdf, destino, cancelado, avance)


# --- Word → PDF ------------------------------------------------------------------
_SCRIPT_WORD = r"""
$ErrorActionPreference = 'Stop'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($args[0], $false, $true)
    $doc.ExportAsFixedFormat($args[1], 17)
    $doc.Close($false)
} finally {
    $word.Quit()
}
"""


def _con_microsoft_word(origen: str, destino: str) -> bool:
    """Convierte con Word si está instalado (solo Windows). True si ha funcionado."""
    if sys.platform != "win32":
        return False
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-Command", _SCRIPT_WORD, origen, destino],
            capture_output=True, timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return r.returncode == 0 and Path(destino).is_file() and Path(destino).stat().st_size > 0
    except Exception:
        return False


CSS_WORD = """
body { font-family: sans-serif; font-size: 11pt; line-height: 1.3; }
h1 { font-size: 20pt; } h2 { font-size: 16pt; } h3 { font-size: 13pt; }
p { margin: 0 0 6pt 0; }
table { border-collapse: collapse; margin: 4pt 0; }
td, th { border: 0.5pt solid #999; padding: 2pt 4pt; vertical-align: top; }
img { max-width: 100%; }
"""


def _con_mammoth(origen: str) -> bytes:
    import mammoth

    with open(origen, "rb") as f:
        html = mammoth.convert_to_html(f).value
    historia = pymupdf.Story(html=html or "<p></p>", user_css=CSS_WORD)
    salida = io.BytesIO()
    escritor = pymupdf.DocumentWriter(salida)
    hoja = pymupdf.paper_rect("a4")
    zona = hoja + (56, 56, -56, -56)  # márgenes de 2 cm
    quedan = True
    while quedan:
        dispositivo = escritor.begin_page(hoja)
        quedan, _ = historia.place(zona)
        historia.draw(dispositivo)
        escritor.end_page()
    escritor.close()
    return salida.getvalue()


def word_a_pdf(origen: str, destino: str) -> str:
    """Convierte el .docx `origen` en el PDF `destino`. Devuelve qué se usó: "Word" o "mammoth"."""
    if _con_microsoft_word(str(Path(origen).resolve()), str(Path(destino).resolve())):
        return "Word"
    Path(destino).write_bytes(_con_mammoth(origen))
    return "mammoth"
