# PDF Casero

Lector y editor de PDF para uso familiar en Windows 10 y 11. Solo lo esencial: leer PDF, reconocer texto de documentos escaneados (OCR), editar el texto y convertir PDF no editables en editables, dibujar esquemas (flechas, globos, líneas…), organizar páginas y crear o rellenar formularios.

Está hecho con herramientas gratuitas: [PySide6](https://doc.qt.io/qtforpython-6/) (Qt) para la interfaz y [PyMuPDF](https://pymupdf.readthedocs.io/) para leer y dibujar los PDF.

## Estado

| Paso | Qué incluye | Estado |
|---|---|---|
| 1. Visor | Abrir, guardar, miniaturas, pasar páginas, zoom, buscar, imprimir | Hecho |
| 2. OCR | Botón "Hacer editable" con Tesseract (español e inglés), seleccionar y copiar texto | Hecho |
| 3. Editar texto | Cambiar, borrar y escribir texto dentro del PDF, con deshacer | Hecho |
| 4. Dibujo y esquemas | Flechas, globos, líneas, formas, texto y lápiz, editables después | Hecho |
| 5. Organizar páginas | Añadir (en blanco, de otro PDF o una imagen), quitar, girar, duplicar y reordenar arrastrando | Hecho |
| 6. Formularios | Crear casillas rellenables y rellenar formularios recibidos | Hecho |
| 7. Instalador | Un único `.exe` con todo incluido | Hecho |

## Instalar en Windows

1. Entra en la pestaña **Actions** del repositorio, abre la última ejecución verde de **Instalador** y descarga el archivo **PDFCasero-Instalador** de la parte de abajo (es un .zip; dentro está el instalador). Cuando haya versiones publicadas, también estará en **Releases**.
2. Haz doble clic en `PDFCasero-Instalador-x.y.z.exe` y sigue los pasos. No pide contraseña de administrador: se instala para tu usuario (si quieres, puedes elegir instalarlo para todos).
3. Como el instalador no está firmado, Windows puede mostrar "Windows protegió su PC". Pulsa **Más información → Ejecutar de todas formas**.

Lleva todo dentro, también los idiomas del OCR, así que funciona sin Internet. Durante la instalación puedes elegir crear un icono en el escritorio y usar PDF Casero para abrir los PDF; en cualquier caso aparece en **Abrir con** y en **Configuración → Aplicaciones → Aplicaciones predeterminadas**. Se desinstala desde **Configuración → Aplicaciones**, como cualquier otro programa.

## Probarlo sin instalar (con Python)

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
- **Cambiar palabras que son parte de una imagen** (formularios impresos a PDF, escaneos sin "Hacer editable"): haz clic encima de la palabra; se tapa con el color del papel, sin borrar el subrayado, y se escribe la nueva en el mismo sitio.
- **Escribir texto nuevo:** haz clic en un hueco, escribe y pulsa Intro. Si hay una raya para escribir (por ejemplo "Fdo.: ______"), el texto se apoya encima de ella.
- **Borrar palabras sueltas:** sin el modo de edición, selecciónalas con el ratón y pulsa Supr. Con **Alt + arrastrar** se eligen solo las palabras que quedan dentro del recuadro.
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

- **Reordenar:** arrastra una miniatura arriba o abajo y suéltala donde quieras; una raya roja marca dónde quedará.
- **Botón "Páginas"** (encima de las miniaturas, también con clic derecho o en "Más"):
  - Insertar una página en blanco antes o después de la actual (por ejemplo, para hacer un esquema con Dibujar).
  - Insertar las páginas de otro PDF o una imagen (foto, escaneo) después de la actual, como anexo.
  - Duplicar, girar a la derecha o a la izquierda.
  - Borrar las páginas seleccionadas (también con Supr). Con Ctrl o Mayús puedes elegir varias.

Todo se puede deshacer con Ctrl+Z.

## Formularios rellenables

**Crear un formulario** (para que quien lo reciba escriba en las casillas): pulsa **Formulario** y elige en la segunda barra:

- **Campo de texto:** arrastra donde irá una respuesta corta (nombre, fecha…). Un clic sin arrastrar crea uno de tamaño normal.
- **Texto largo:** arrastra una zona de varias líneas (observaciones…).
- **Casilla:** haz clic donde irá una casilla para marcar ✓.
- **Seleccionar:** mueve un campo arrastrándolo, cambia su tamaño con el cuadradito de la esquina, doble clic para cambiarle el nombre y Supr para borrarlo.

Son campos de formulario PDF estándar: quien reciba el PDF los puede rellenar con Adobe Reader, Edge, Chrome o el móvil.

**Rellenar un formulario** (uno recibido o uno propio): fuera de los modos de edición, haz clic en un campo de texto para escribir (Intro acepta) o en una casilla para marcarla o desmarcarla. Después guarda.

## Atajos de teclado

| Acción | Teclas |
|---|---|
| Abrir | Ctrl+O |
| Guardar / Guardar como | Ctrl+S / Ctrl+Mayús+S |
| Imprimir (también en "Más") | Ctrl+P |
| Hacer editable (OCR) | Ctrl+E |
| Editar texto | Ctrl+T |
| Dibujar | Ctrl+D |
| Formulario (crear campos) | Ctrl+Mayús+F |
| Deshacer / rehacer | Ctrl+Z / Ctrl+Y |
| Borrar el texto seleccionado | Supr |
| Copiar el texto seleccionado | Ctrl+C (Ctrl+A selecciona toda la página) |
| Seleccionar solo el texto de un recuadro | Alt + arrastrar el ratón |
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
- `pdfcasero/formularios.py` y `herramientas_formulario.py`: campos rellenables y el modo Formulario.
- `pdfcasero/impresion.py`: impresión.
- `pdfcasero/autoprueba.py`: comprobación del programa ya empaquetado (`PDFCasero.exe --autoprueba resultado.txt`).
- `packaging/`: receta de PyInstaller (`pdfcasero.spec`), instalador de Inno Setup (`instalador.iss`) e icono.
- `pdfcasero/estilo.py`: colores y aspecto.

### Crear el instalador a mano (en Windows)

Lo hace solo GitHub Actions (`.github/workflows/instalador.yml`), que además lo instala, lo prueba y lo desinstala. A mano:

```
pip install -r requirements.txt pyinstaller
python -c "from pathlib import Path; from pdfcasero.ocr import descargar_idiomas; descargar_idiomas(Path('packaging/tessdata'))"
pyinstaller --noconfirm packaging/pdfcasero.spec
iscc packaging\instalador.iss
```

El instalador queda en `packaging\salida\`. Hace falta [Inno Setup 6](https://jrsoftware.org/isinfo.php). Para publicar una versión: cambia `__version__` en `pdfcasero/__init__.py` y crea una etiqueta `v0.1.0`.

## Licencias

PyMuPDF se distribuye con licencia AGPL y PySide6 con LGPL. Para un uso privado en casa no hay ninguna restricción.
