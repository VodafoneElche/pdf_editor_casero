import os

import pytest

from pdfcasero import ocr

pytestmark = pytest.mark.skipif(ocr.buscar_tessdata() is None, reason="faltan los idiomas del OCR")


def test_autoprueba_del_programa(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from pdfcasero.autoprueba import ejecutar

    salida = tmp_path / "resultado.txt"
    assert ejecutar(str(salida)) == 0, salida.read_text(encoding="utf-8")
    texto = salida.read_text(encoding="utf-8")
    assert "Ventana ok" in texto and "OCR ok" in texto
