# PDF Casero

Lector y editor de PDF para uso familiar en Windows 10 y 11. Solo lo esencial: leer PDF, reconocer texto de documentos escaneados (OCR), editar el texto y convertir PDF no editables en editables.

Está hecho con herramientas gratuitas: [PySide6](https://doc.qt.io/qtforpython-6/) (Qt) para la interfaz y [PyMuPDF](https://pymupdf.readthedocs.io/) para leer y dibujar los PDF.

## Estado

| Paso | Qué incluye | Estado |
|---|---|---|
| 1. Visor | Abrir, guardar, miniaturas, pasar páginas, zoom, buscar, imprimir | Hecho |
| 2. OCR | Botón "Hacer editable" con Tesseract (español e inglés) | Pendiente |
| 3. Editar texto | Corregir texto dentro del PDF y exportar a Word | Pendiente |
| 4. Instalador | Un único `.exe` con todo incluido | Pendiente |

## Probarlo ahora (antes de tener el instalador)

1. Instala [Python 3.12](https://www.python.org/downloads/windows/) y marca la casilla **Add Python to PATH**.
2. Descarga este repositorio (botón verde **Code → Download ZIP**) y descomprímelo.
3. En esa carpeta, abre una terminal y ejecuta:
   ```
   pip install -r requirements.txt
   ```
4. Haz doble clic en `lanzar.pyw`, o ejecuta `python -m pdfcasero archivo.pdf`.

## Atajos de teclado

| Acción | Teclas |
|---|---|
| Abrir | Ctrl+O |
| Guardar / Guardar como | Ctrl+S / Ctrl+Mayús+S |
| Imprimir | Ctrl+P |
| Buscar | Ctrl+F, después Intro o F3 (siguiente) y Mayús+F3 (anterior) |
| Acercar / alejar | Ctrl + / Ctrl -, o Ctrl + rueda del ratón |
| Ajustar al ancho / página completa | Ctrl+0 / Ctrl+1 |
| Página siguiente / anterior | Ctrl+→ / Ctrl+←, o Av Pág / Re Pág |
| Pantalla completa | F11 |
| Cerrar PDF | Ctrl+W |

También se puede arrastrar un PDF a la ventana. La pantalla de inicio recuerda los últimos PDF abiertos.

## Para desarrollo

```
pip install -r requirements-dev.txt
python -m pytest
```

Estructura:

- `pdfcasero/documento.py`: acceso al PDF (abrir, dibujar páginas, buscar). No depende de la interfaz.
- `pdfcasero/visor.py`: vista continua de páginas con zoom; solo dibuja las páginas visibles.
- `pdfcasero/ventana.py`: ventana principal, barra de herramientas, miniaturas y búsqueda.
- `pdfcasero/impresion.py`: impresión.
- `pdfcasero/estilo.py`: colores y aspecto.

## Licencias

PyMuPDF se distribuye con licencia AGPL y PySide6 con LGPL. Para un uso privado en casa no hay ninguna restricción.
