# PDF Casero

Lector y editor de PDF para uso familiar en Windows 10 y 11. Solo lo esencial: leer PDF, reconocer texto de documentos escaneados (OCR), editar el texto y convertir PDF no editables en editables, además de dibujar esquemas (flechas, globos, líneas…).

Está hecho con herramientas gratuitas: [PySide6](https://doc.qt.io/qtforpython-6/) (Qt) para la interfaz y [PyMuPDF](https://pymupdf.readthedocs.io/) para leer y dibujar los PDF.

## Estado

| Paso | Qué incluye | Estado |
|---|---|---|
| 1. Visor | Abrir, guardar, miniaturas, pasar páginas, zoom, buscar, imprimir | Hecho |
| 2. OCR | Botón "Hacer editable" con Tesseract (español e inglés), seleccionar y copiar texto | Hecho |
| 3. Editar texto | Cambiar, borrar y escribir texto dentro del PDF, con deshacer | Hecho |
| 4. Dibujo y esquemas | Flechas, globos, líneas, formas, texto y lápiz, editables después | Hecho |
| 5. Organizar páginas | Añadir (en blanco, de otro PDF o una imagen), quitar, girar, duplicar y reordenar arrastrando | Hecho |
| 6. Formularios | Crear casillas rellenables y rellenar formularios recibidos | Pendiente |
| 7. Instalador | Un único `.exe` con todo incluido | Pendiente |

## Probarlo ahora (antes de tener el instalador)

1. Instala [Python 3.12](https://www.python.org/downloads/windows/) y marca la casilla **Add Python to PATH**.
2. Descarga este repositorio (botón verde **Code → Download ZIP**) y descomprímelo.
3. En esa carpeta, abre una terminal y ejecuta:
   ```
   pip install -r requirements.txt
   ```
4. Haz doble clic en `lanzar.pyw`, o ejecuta `python -m pdfcasero archivo.pdf`.

## Hacer editable (OCR)

Cuando abres un PDF escaneado aparece un aviso amarillo con el botón **Hacer editable**. El programa reconoce el texto (en español e inglés) y lo añade como una capa invisible: la página se ve igual, pero ya puedes buscar, seleccionar y copiar el texto. Después pulsa **Guardar**.

La primera vez descarga los idiomas (unos 6 MB) y los guarda en `%LOCALAPPDATA%\PDFCasero\tessdata`. No hace falta instalar Tesseract aparte: PyMuPDF ya lo incluye.

## Editar texto

Pulsa **Editar texto** (Ctrl+T) y:

- **Cambiar una línea:** haz clic sobre ella, escribe y pulsa Intro. Se mantiene el tamaño, el color y un tipo de letra parecido.
- **Borrar una línea:** haz clic, borra todo y pulsa Intro.
- **Escribir texto nuevo:** haz clic en un hueco, escribe y pulsa Intro.
- **Borrar palabras sueltas:** sin el modo de edición, selecciónalas con el ratón y pulsa Supr.
- **Deshacer / rehacer:** ↶ ↷ o Ctrl+Z / Ctrl+Y.

Funciona también en PDF escaneados después de "Hacer editable": la línea original se tapa con el color del papel y se escribe encima con el color de la tinta.

Los PDF guardan letras sueltas, no párrafos, por eso se edita línea a línea y el texto no se recoloca solo si la línea nueva es más larga.

## Dibujar y hacer esquemas

Pulsa **Dibujar** (Ctrl+D) y aparece una segunda barra con las herramientas:

- **Flecha, Línea, Rectángulo, Círculo:** arrastra sobre la página.
- **Globo:** arrastra desde lo que quieres señalar hasta donde irá el globo y escribe el texto.
- **Texto:** haz clic y escribe.
- **Lápiz:** dibuja a mano alzada.
- **Color, grosor y relleno:** se aplican a lo que dibujes y al dibujo seleccionado.
- **Seleccionar:** clic en un dibujo para seleccionarlo. Arrástralo para moverlo, o tira de sus cuadraditos para estirarlo. Doble clic en un globo o texto para cambiar lo que pone. Supr lo borra.

Los dibujos se guardan como anotaciones PDF estándar, así que se ven en cualquier lector (Adobe, Edge, Chrome…).

## Organizar páginas

En la columna de miniaturas:

- **Reordenar:** arrastra una miniatura arriba o abajo y suéltala donde quieras.
- **Botón "Páginas"** (encima de las miniaturas, también con clic derecho o en "Más"):
  - Insertar una página en blanco antes o después de la actual (por ejemplo, para hacer un esquema con Dibujar).
  - Insertar las páginas de otro PDF o una imagen (foto, escaneo) después de la actual, como anexo.
  - Duplicar, girar a la derecha o a la izquierda.
  - Borrar las páginas seleccionadas (también con Supr). Con Ctrl o Mayús puedes elegir varias.

Todo se puede deshacer con Ctrl+Z.

## Atajos de teclado

| Acción | Teclas |
|---|---|
| Abrir | Ctrl+O |
| Guardar / Guardar como | Ctrl+S / Ctrl+Mayús+S |
| Imprimir (también en "Más") | Ctrl+P |
| Hacer editable (OCR) | Ctrl+E |
| Editar texto | Ctrl+T |
| Dibujar | Ctrl+D |
| Deshacer / rehacer | Ctrl+Z / Ctrl+Y |
| Borrar el texto seleccionado | Supr |
| Copiar el texto seleccionado | Ctrl+C (Ctrl+A selecciona toda la página) |
| Buscar | Ctrl+F, después Intro o F3 (siguiente) y Mayús+F3 (anterior) |
| Acercar / alejar | Ctrl + / Ctrl -, o Ctrl + rueda del ratón |
| Ajustar al ancho / página completa (también en "Más") | Ctrl+0 / Ctrl+1 |
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
- `pdfcasero/ocr.py`: reconocimiento de texto y capa de texto invisible.
- `pdfcasero/dialogo_ocr.py`: el OCR en segundo plano, con barra de progreso.
- `pdfcasero/edicion.py`: cambiar, borrar y escribir texto en la página.
- `pdfcasero/dibujo.py`: los dibujos como anotaciones PDF, con su receta para poder retocarlos.
- `pdfcasero/herramientas_dibujo.py`: ratón y teclado del modo Dibujo.
- `pdfcasero/impresion.py`: impresión.
- `pdfcasero/estilo.py`: colores y aspecto.

## Licencias

PyMuPDF se distribuye con licencia AGPL y PySide6 con LGPL. Para un uso privado en casa no hay ninguna restricción.
