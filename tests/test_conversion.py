import pymupdf

from pdfcasero import conversion


def test_pdf_a_word_y_vuelta(tmp_path):
    pdf = tmp_path / "carta.pdf"
    doc = pymupdf.open()
    pagina = doc.new_page()
    pagina.insert_text((72, 80), "Carta para la familia", fontsize=18)
    pagina.insert_htmlbox(pymupdf.Rect(72, 110, 400, 140), "<p>Precio: 25 € al mes</p>")
    doc.save(pdf)

    docx = tmp_path / "carta.docx"
    conversion.pdf_a_word(str(pdf), str(docx))
    assert docx.stat().st_size > 1000

    vuelta = tmp_path / "vuelta.pdf"
    metodo = conversion.word_a_pdf(str(docx), str(vuelta))
    assert metodo in ("Word", "mammoth")
    texto = pymupdf.open(vuelta)[0].get_text()
    assert "Carta para la familia" in texto and "25 €" in texto


def test_exportacion_en_proceso_aparte(tmp_path):
    import time

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 80), "Hola", fontsize=12)
    destino = tmp_path / "hola.docx"
    trabajo = conversion.ExportacionWord(doc.tobytes(), str(destino))
    limite = time.time() + 120
    resultado = None
    while resultado is None and time.time() < limite:
        time.sleep(0.2)
        resultado = trabajo.resultado()
    assert resultado == ("ok", str(destino)), resultado
    assert destino.stat().st_size > 1000


def test_tablas_del_pdf_a_hoja_de_calculo(tmp_path):
    from openpyxl import load_workbook

    from pdfcasero.conversion import _valor, pdf_a_excel

    assert _valor("1.028,26 €") == (1028.26, "€")
    assert _valor("21%") == (0.21, "%")
    assert _valor("Total: 5,00€") == "Total: 5,00€"
    doc = pymupdf.open()
    pagina = doc.new_page()
    filas = [("Concepto", "Importe"), ("Base imponible", "824,10"), ("Total a pagar", "1.028,26 €")]
    for x in (50, 250, 450):  # rejilla de la tabla
        pagina.draw_line((x, 50), (x, 50 + 30 * len(filas)))
    for i in range(len(filas) + 1):
        pagina.draw_line((50, 50 + 30 * i), (450, 50 + 30 * i))
    for i, (a, b) in enumerate(filas):
        pagina.insert_htmlbox(pymupdf.Rect(55, 55 + 30 * i, 245, 78 + 30 * i), a)
        pagina.insert_htmlbox(pymupdf.Rect(255, 55 + 30 * i, 445, 78 + 30 * i), b)
    destino = tmp_path / "tablas.xlsx"
    assert pdf_a_excel(doc.tobytes(), str(destino)) == 1
    hoja = load_workbook(destino)["Página 1"]
    filas = [f for f in hoja.iter_rows(values_only=True) if any(f)]
    assert filas == [("Concepto", "Importe"), ("Base imponible", 824.1), ("Total a pagar", 1028.26)]


def test_sin_tablas_cada_linea_en_una_fila(tmp_path):
    from openpyxl import load_workbook

    from pdfcasero.conversion import pdf_a_excel

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Hola\nAdiós")
    destino = tmp_path / "texto.xlsx"
    assert pdf_a_excel(doc.tobytes(), str(destino)) == 0
    assert [f[0] for f in load_workbook(destino)["Página 1"].iter_rows(values_only=True)] == ["Hola", "Adiós"]
