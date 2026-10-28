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
| 6. Formularios | Rellenar formularios recibidos (crear formularios se quitó a petición de Jose) | Hecho |
| Extra | Exportar a Word (.docx) para Google Docs e importar .docx como PDF | Hecho |
| Extra | Cuenta de Google: enviar a Google Docs u Hojas de cálculo y traer de vuelta como PDF | Hecho |
| Extra | Varios PDF abiertos a la vez, cada uno en su pestaña (como en Adobe) | Hecho |
| Extra | Logotipo (PF en un corazón) y color de fondo a elegir en la pantalla de inicio: gris, rosa, rojo, naranja o celeste suaves | Hecho |
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

## Formularios recibidos

Si te llega un PDF con casillas para rellenar, haz clic en un campo de texto para escribir (Intro acepta) o en una casilla para marcarla o desmarcarla. Después guarda.

## Google (Docs y Hojas de cálculo) y Word

Botón **Google** de la barra:

- **Conectar cuenta de Google:** la primera vez se abre el navegador, entras con tu Gmail y pulsas **Permitir**. Cada ordenador (y cada usuario de Windows) usa su propia cuenta; la sesión se guarda cifrada solo en ese ordenador. Desde el mismo menú se puede **cambiar de cuenta** o **desconectarla**.
- **Enviar a Google Docs:** convierte el PDF a Word (facturas incluidas: datos, tablas y gráfica en su sitio), lo sube a tu Google Drive como Documento de Google y lo abre en el navegador para editarlo.
- **Enviar a Hojas de cálculo de Google:** como iLovePDF, cada página va en su pestaña con cada dato en su casilla, en el mismo sitio que en el PDF, los fondos grises pintados y los logotipos, códigos de barras, QR y gráficas como imágenes encima de las casillas. Los importes van como números para poder sumarlos.
- **Traer de Google como PDF:** enseña los documentos y hojas de cálculo enviados desde PDF Casero y abre el elegido como PDF (lo convierte el propio Google). Pulsa **Guardar** para guardarlo.
- PDF Casero solo puede ver los archivos que él mismo ha subido, no el resto de tu Drive.
- **Guardar copia en Word (.docx)** y **Abrir** un `.docx` siguen funcionando sin cuenta. Funciona muy bien con PDF de texto (facturas, cartas); con formularios impresos como imagen el resultado es más pobre.

### Registrar la app en Google (una sola vez, lo hace el administrador)

1. En [console.cloud.google.com](https://console.cloud.google.com) crea el proyecto «PDF Casero» y habilita **Google Drive API**.
2. En **Google Auth Platform**: tipo **Externo**, nombre «PDF Casero», y en **Público** pulsa **Publicar aplicación** (si se queda en modo prueba, solo entran los usuarios de prueba y la sesión caduca cada 7 días).
3. En **Clientes** crea uno de tipo **Aplicación de escritorio** y descarga el JSON.
4. Guarda su contenido como secreto del repositorio `GOOGLE_CLIENTE_JSON`: el instalador lo incluye. Sin él, la app pide elegir ese archivo la primera vez.

## Atajos de teclado

| Acción | Teclas |
|---|---|
| Abrir | Ctrl+O |
| Guardar / Guardar como | Ctrl+S / Ctrl+Mayús+S |
| Imprimir (también en "Más") | Ctrl+P |
| Hacer editable (OCR) | Ctrl+E |
| Editar texto | Ctrl+T |
| Dibujar | Ctrl+D |
| Guardar copia en Word | Ctrl+Mayús+W |
| Girar la página a la izquierda / derecha | Ctrl+Mayús+- / Ctrl+Mayús++ (o los botones ↺ ↻ junto al zoom) |
| Deshacer / rehacer | Ctrl+Z / Ctrl+Y |
| Borrar el texto seleccionado | Supr |
| Mover la página con la mano | Arrastrar fuera del texto, o con la rueda del ratón pulsada |
| Copiar el texto seleccionado | Ctrl+C (Ctrl+A selecciona toda la página) |
| Seleccionar solo el texto de un recuadro | Alt + arrastrar el ratón |
| Buscar | Ctrl+F, después Intro o F3 (siguiente) y Mayús+F3 (anterior) |
| Acercar / alejar | Ctrl + / Ctrl -, o Ctrl + rueda del ratón |
| Ajustar al ancho / página completa (también en "Más") | Ctrl+0 / Ctrl+1 |
| Página siguiente / anterior | Ctrl+→ / Ctrl+←, o Av Pág / Re Pág |
| Pantalla completa | F11 |
| Cerrar PDF (su pestaña) | Ctrl+W |
| Pestaña siguiente / anterior | Ctrl+Tab / Ctrl+Mayús+Tab |

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
- `pdfcasero/formularios.py` y `herramientas_formulario.py`: campos rellenables.
- `pdfcasero/word_sencillo.py`: PDF a Word pensado para Google Docs, como iLovePDF: el contenido fluye (columnas en tablas invisibles, renglones con tabuladores, tablas de verdad con su fondo gris, gráficas como imagen).
- `pdfcasero/hoja_sencilla.py`: PDF a hoja de cálculo como iLovePDF (cada dato en su casilla, imágenes encima).
- `pdfcasero/conversion.py`: proceso aparte para exportar a Word, PDF a Word con pdf2docx (método antiguo), PDF a .xlsx (ver `hoja_sencilla.py`) y Word a PDF (Microsoft Word si está, si no mammoth).
- `pdfcasero/google.py`: cuenta de Google (OAuth de escritorio con PKCE, permiso `drive.file`) y Drive (subir como Documento de Google, listar, exportar a PDF); `ventana_google.py`: su menú.
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

PyMuPDF se distribuye con licencia AGPL, PySide6 con LGPL y pdf2docx con GPL. Para un uso privado en casa no hay ninguna restricción.
