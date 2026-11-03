import pymupdf
import pytest

from pdfcasero.documento import ContrasenaNecesaria, Documento


@pytest.fixture
def pdf_ejemplo(tmp_path):
    ruta = tmp_path / "ejemplo.pdf"
    doc = pymupdf.open()
    for n in range(3):
        p = doc.new_page()
        p.insert_text((72, 72), f"Página {n + 1}: factura de la luz")
        if n == 2:
            p.insert_text((72, 120), "Hello world, factura en inglés")
    doc.new_page()  # página en blanco, como si fuera escaneada
    doc.save(ruta)
    return ruta


def test_abrir_y_paginas(pdf_ejemplo):
    d = Documento(pdf_ejemplo)
    assert d.num_paginas == 4
    assert d.titulo == "ejemplo.pdf"
    assert d.tamano_pagina(0) == pytest.approx((595, 842), abs=1)


def test_renderizar(pdf_ejemplo):
    d = Documento(pdf_ejemplo)
    datos, an, al, paso = d.renderizar(0, 1.0)
    assert (an, al) == (595, 842)
    assert len(datos) == paso * al


def test_buscar_sin_mayusculas(pdf_ejemplo):
    d = Documento(pdf_ejemplo)
    res = d.buscar("FACTURA")
    assert [r.pagina for r in res] == [0, 1, 2, 2]
    assert d.buscar("   ") == []
    assert d.buscar("no existe") == []


def test_detecta_pagina_sin_texto(pdf_ejemplo):
    d = Documento(pdf_ejemplo)
    assert d.tiene_texto(0)
    assert not d.tiene_texto(3)


def test_contrasena(tmp_path):
    ruta = tmp_path / "secreto.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secreto")
    doc.save(ruta, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="1234", owner_pw="1234")
    with pytest.raises(ContrasenaNecesaria):
        Documento(ruta)
    with pytest.raises(ContrasenaNecesaria):
        Documento(ruta, "mal")
    assert Documento(ruta, "1234").num_paginas == 1


def test_guardar_como_y_guardar(pdf_ejemplo, tmp_path):
    d = Documento(pdf_ejemplo)
    copia = d.guardar(tmp_path / "copia.pdf")
    assert copia.exists() and d.ruta == copia and not d.modificado
    assert Documento(copia).num_paginas == 4
    # Guardar encima del mismo archivo y seguir usándolo
    d.modificado = True
    d.guardar()
    assert not d.modificado
    assert d.buscar("factura")
    assert [p.name for p in tmp_path.glob("tmp*.pdf")] == []


def test_guardar_pdf_con_contrasena(tmp_path):
    ruta = tmp_path / "secreto.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secreto")
    doc.save(ruta, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="1234", owner_pw="1234")
    d = Documento(ruta, "1234")
    d.guardar()
    assert d.num_paginas == 1 and d.buscar("secreto")


@pytest.fixture
def pdf_texto(tmp_path):
    ruta = tmp_path / "texto.pdf"
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((72, 72), "Querida familia", fontsize=14, color=(0.8, 0, 0), fontname="tiro")
    p.insert_text((72, 100), "Hoy cenamos paella a las nueve", fontsize=12)
    p.draw_rect(pymupdf.Rect(60, 50, 400, 120), color=(0, 0, 1))
    doc.save(ruta)
    return ruta


def test_cambiar_linea_conserva_estilo_y_lo_demas(pdf_texto):
    d = Documento(pdf_texto)
    linea = d.linea_en(0, 100, 68)
    assert linea.texto == "Querida familia"
    d.cambiar_linea(0, linea, "Queridos abuelos")
    assert d.modificado
    assert d.buscar("Queridos abuelos") and not d.buscar("Querida familia")
    assert d.buscar("paella")  # la otra línea sigue igual
    nueva = d.linea_en(0, 100, 68)
    assert nueva.fuente == "tiro" and nueva.color == (0.8, 0, 0) and round(nueva.tamano) == 14
    assert len(d._doc[0].get_drawings()) == 1  # el recuadro no se toca


def test_borrar_linea_y_palabras(pdf_texto):
    d = Documento(pdf_texto)
    d.cambiar_linea(0, d.linea_en(0, 100, 68), "")
    assert not d.buscar("Querida")
    palabras = [w[4] for w in d.palabras(0)]
    i = palabras.index("paella")
    d.borrar_palabras(0, i, i + 1)  # "paella a"
    assert [w[4] for w in d.palabras(0)] == ["Hoy", "cenamos", "las", "nueve"]


def test_escribir_deshacer_rehacer(pdf_texto):
    d = Documento(pdf_texto)
    assert not d.puede_deshacer
    d.escribir(0, 72, 200, "Nota añadida: llevar pan")
    assert d.buscar("llevar pan")
    assert d.deshacer() and not d.buscar("llevar pan")
    assert d.puede_rehacer
    assert d.rehacer() and d.buscar("llevar pan")
    d.escribir(0, 72, 250, "otra")
    assert not d.puede_rehacer  # un cambio nuevo borra lo que se podía rehacer


def _formulario_impreso(ruta):
    """Como un PDF de "Imprimir a PDF": la página es una imagen y el contenido cambia las coordenadas."""
    origen = pymupdf.open()
    p = origen.new_page(width=600, height=300)
    p.insert_text((50, 100), "Mes:", fontsize=11)
    p.insert_text((100, 98), "JULIO", fontsize=10)
    p.draw_line((95, 101), (300, 101), width=0.8)
    p.insert_text((50, 200), "Fdo.:", fontsize=11)
    p.draw_line((95, 202), (400, 202), width=0.8)
    foto = p.get_pixmap(dpi=200)
    doc = pymupdf.open()
    pagina = doc.new_page(width=600, height=300)
    pagina.insert_image(pagina.rect, pixmap=foto)
    # Cambio de coordenadas sin cerrar (volteado), como hace Microsoft Print to PDF
    xref = pagina.get_contents()[0]
    doc.update_stream(xref, b"1 0 0 -1 0 300 cm\nq\n600 0 0 -300 0 300 cm\n/fzImg0 Do\nQ\n")
    doc.save(ruta)


def test_cambiar_palabra_de_imagen_y_firmar_sobre_la_raya(tmp_path):
    ruta = tmp_path / "impreso.pdf"
    _formulario_impreso(ruta)
    d = Documento(str(ruta))
    linea = d.linea_en(0, 115, 95)
    assert linea is not None and linea.exacta
    assert 98 <= linea.rect.x0 <= 102 and 96.5 <= linea.rect.y1 <= 99.5  # sin bajar al subrayado
    d.cambiar_linea(0, linea, "agosto")
    x, y = d.donde_escribir(0, 200, 196, 12)
    assert 186 <= y + 12 * 0.8 <= 201  # la línea base queda justo encima de la raya
    d.escribir(0, x, y, "Jose", 12)
    pagina = d._doc[0]
    palabras = {w[4]: w for w in pagina.get_text("words")}
    assert palabras["agosto"][1] > 80 and palabras["agosto"][3] < 103  # en su sitio, no volteado
    assert 180 < palabras["Jose"][1] and palabras["Jose"][3] < 205
    # El subrayado sigue ahí debajo de "agosto"
    pix = pagina.get_pixmap(clip=pymupdf.Rect(150, 100.6, 151, 101.4), dpi=144, colorspace=pymupdf.csGRAY)
    assert min(pix.samples) < 120


def test_simbolo_euro_no_se_pierde(tmp_path):
    ruta = tmp_path / "precio.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 100), "Total: 10 EUR", fontname="helv", fontsize=12)
    doc.save(ruta)
    d = Documento(str(ruta))
    d.cambiar_linea(0, d.linea_en(0, 90, 96), "Total: 1.028,20 €")
    d.escribir(0, 72, 200, "Nuevo: 5 €")
    destino = tmp_path / "precio2.pdf"
    d.guardar(destino)
    pagina = pymupdf.open(destino)[0]
    # Con Arial (Windows) los espacios salen como espacio duro al extraer; da igual
    texto = pagina.get_text().replace("\xa0", " ")
    assert "1.028,20 €" in texto and "5 €" in texto
    assert pagina.search_for("1.028,20 €")
    assert destino.stat().st_size < 200_000  # la fuente añadida se guarda recortada


def test_seleccionar_solo_un_trozo_de_palabra(tmp_path):
    """Como en la factura de Jose: copiar solo «2027» de «600840454-2027»."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication

    from pdfcasero.documento import Documento
    from pdfcasero.visor import VisorPDF

    origen = pymupdf.open()
    pagina = origen.new_page()
    pagina.insert_text((72, 100), "Resumen: 600840454-2027 Red Infinity", fontsize=12)
    pagina.insert_text((72, 130), "Total: 10,9844", fontsize=12)
    ruta = tmp_path / "factura.pdf"
    origen.save(ruta)

    app = QApplication.instance() or QApplication([])
    doc = Documento(str(ruta))
    visor = VisorPDF()
    visor.cargar(doc)
    palabras = doc.palabras(0)
    k = next(i for i, w in enumerate(palabras) if w[4] == "600840454-2027")
    bordes = doc.bordes_letras(0, k)
    assert len(bordes) == len("600840454-2027")
    y = (palabras[k][1] + palabras[k][3]) / 2
    guion = "600840454-2027".index("-")

    def entre(a, b):  # punto entre las letras a y b
        return (bordes[a][1] + bordes[b][0]) / 2

    # Desde justo después del guion hasta el final de la palabra
    visor.empezar_seleccion(0, QPointF(entre(guion, guion + 1), y))
    visor.extender_seleccion(0, QPointF(bordes[-1][1] + 0.5, y))
    assert visor.texto_seleccionado() == "2027"
    (x0, _, x1, _), = visor.rects_seleccion(0)
    assert abs(x0 - bordes[guion + 1][0]) < 0.6 and abs(x1 - bordes[-1][1]) < 0.6
    # Al revés (arrastrando hacia la izquierda) y solo la primera parte
    visor.empezar_seleccion(0, QPointF(entre(guion - 1, guion), y))
    visor.extender_seleccion(0, QPointF(bordes[0][0] - 0.5, y))
    assert visor.texto_seleccionado() == "600840454"
    # Cruzando palabras: «2027 Red Inf»
    inf = next(i for i, w in enumerate(palabras) if w[4] == "Infinity")
    b_inf = doc.bordes_letras(0, inf)
    visor.empezar_seleccion(0, QPointF(entre(guion, guion + 1), y))
    visor.extender_seleccion(0, QPointF((b_inf[2][1] + b_inf[3][0]) / 2, y))
    assert visor.texto_seleccionado() == "2027 Red Inf"
    # Doble clic sigue cogiendo la palabra entera
    visor.fijar_seleccion(0, k, k)
    assert visor.texto_seleccionado() == "600840454-2027"
    # Borrar solo el trozo elegido deja el resto
    visor.empezar_seleccion(0, QPointF(entre(guion, guion + 1), y))
    visor.extender_seleccion(0, QPointF(bordes[-1][1] + 0.5, y))
    visor.borrar_seleccion()
    texto = doc._doc[0].get_text()
    assert "600840454-" in texto and "2027" not in texto and "Red Infinity" in texto
    visor.deleteLater()
    app.processEvents()
