"""Aspecto visual: claro, sobrio y con un acento rojo parecido al de Adobe Reader."""

ACENTO = "#c4302b"

# Colores de fondo que se eligen en la pantalla de inicio, como en un navegador:
# nombre -> (nombre a la vista, fondo de la ventana, fondo detrás de las páginas,
#            panel de miniaturas y pestañas, color del botón, barra de menú: un tono más oscuro)
TEMAS = {
    "gris": ("Gris (el de siempre)", "#f5f5f7", "#e4e4e8", "#f0f0f3", "#c9c9cf", "#ffffff"),
    "rosa": ("Rosa suave", "#fbe9f1", "#f2d3e1", "#f8e0eb", "#f2a7c9", "#f5c9dc"),
    "rojo": ("Rojo suave", "#fbe7e6", "#f1cfcd", "#f7dcda", "#e88f8b", "#f1bebb"),
    "naranja": ("Naranja suave", "#fdeedf", "#f5d9bd", "#fae4cd", "#f4b47a", "#f7cfa8"),
    "celeste": ("Azul celeste suave", "#e6f2fb", "#cbe2f3", "#d9eaf7", "#8ec8ef", "#bcdcf3"),
}


def hoja_estilo(tema: str = "gris", barra: str | None = None) -> str:
    """La hoja de estilo con el color de fondo `tema` y el de la barra de menú `barra`
    (si no se elige, la barra va del mismo color que el fondo, un tono más oscuro)."""
    _, fondo, visor, panel, _, _ = TEMAS.get(tema, TEMAS["gris"])
    barra = barra if barra in TEMAS else tema if tema in TEMAS else "gris"
    color_barra = TEMAS[barra][5]
    hoja = HOJA_ESTILO.replace("#f5f5f7", fondo).replace("#e4e4e8", visor).replace("#f0f0f3", panel)
    if barra != "gris":
        hoja += (
            f"QToolBar#barraPrincipal, QToolBar#barraDibujo, QToolBar#barraFormulario {{ background: {color_barra}; }}\n"
            "QToolBar QToolButton:hover { background: rgba(0, 0, 0, 0.07); }\n"
            "QToolBar QToolButton:pressed { background: rgba(0, 0, 0, 0.12); }\n"
        )
    return hoja


HOJA_ESTILO = f"""
QMainWindow, #bienvenida {{ background: #f5f5f7; }}
QToolBar#barraDibujo {{ background: #fafafb; border: none; border-bottom: 1px solid #dddde1; padding: 2px 8px; spacing: 4px; }}
QToolBar#barraPrincipal {{
    background: #ffffff; border: none; border-bottom: 1px solid #dddde1;
    padding: 4px 8px; spacing: 4px;
}}
QToolBar QToolButton {{ padding: 4px 8px; border-radius: 6px; color: #2b2b2e; }}
QToolBar QToolButton:hover {{ background: #ececf0; }}
QToolBar QToolButton:pressed {{ background: #e0e0e6; }}
QToolBar QToolButton:disabled {{ color: #a9a9b0; }}
QWidget {{ color: #1d1d1f; }}
QLineEdit, QComboBox {{
    border: 1px solid #cfcfd6; border-radius: 6px; padding: 4px 6px; background: #ffffff; color: #1d1d1f;
}}
QLineEdit:focus {{ border-color: {ACENTO}; }}
#fondoVisor, QScrollArea#visor {{ background: #e4e4e8; border: none; }}
QListWidget#miniaturas {{ background: #f0f0f3; border: none; border-right: 1px solid #dddde1; }}
#tituloBienvenida {{ font-size: 34px; font-weight: 600; color: {ACENTO}; margin-bottom: 4px; }}
#textoBienvenida {{ font-size: 15px; color: #55555c; margin: 8px; }}
QToolButton#botonPrincipal {{
    background: {ACENTO}; color: white; font-size: 15px; font-weight: 600;
    padding: 10px 28px; border-radius: 8px; margin: 12px;
}}
QToolButton#botonPrincipal:hover {{ background: #a82722; }}
QListWidget#recientes {{
    background: #ffffff; border: 1px solid #dddde1; border-radius: 8px; padding: 4px; font-size: 14px;
    min-width: 420px; max-height: 260px;
}}
QListWidget#recientes::item {{ padding: 6px 8px; border-radius: 6px; }}
QListWidget#recientes::item {{ color: #1d1d1f; }}
QListWidget#recientes::item:hover {{ background: #f3f3f6; }}
QListWidget#recientes::item:selected {{ background: #f6d9d7; color: #1d1d1f; }}
QToolButton#muestraTema {{ border: 2px solid #ffffff; border-radius: 15px; min-width: 26px; min-height: 26px; }}
QToolButton#muestraTema:hover {{ border-color: #9a9aa2; }}
QToolButton#muestraTema:checked {{ border: 3px solid {ACENTO}; }}
QFrame#avisoEscaneado {{ background: #fff4d6; border-bottom: 1px solid #f0d68a; color: #5a4500; }}
QFrame#avisoEscaneado[editable="true"] {{ background: #e3f4e6; border-bottom: 1px solid #a9d8b2; color: #1f5a2b; }}
QToolButton#botonAviso {{
    background: {ACENTO}; color: white; font-weight: 600; padding: 5px 14px; border-radius: 6px;
}}
QToolButton#botonAviso:hover {{ background: #a82722; }}
QLineEdit#editorEnLinea {{
    border: 2px solid {ACENTO}; border-radius: 3px; padding: 0 2px; background: #ffffff; color: #111111;
}}
QToolBar QToolButton:checked {{ background: #f6d9d7; color: {ACENTO}; }}
QToolButton#botonPaginas {{
    background: #f0f0f3; border: none; border-right: 1px solid #dddde1; border-bottom: 1px solid #dddde1;
    padding: 6px; font-weight: 600; color: #2b2b2e;
}}
QToolButton#botonPaginas:hover {{ background: #e6e6ea; }}
QTabBar#pestanas {{ background: #f0f0f3; border-bottom: 1px solid #dddde1; }}
QTabBar#pestanas::tab {{
    background: #e6e6ea; color: #44444a; padding: 6px 10px 6px 14px; margin: 4px 0 0 4px;
    border: 1px solid #dddde1; border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px;
    min-width: 90px; max-width: 260px;
}}
QTabBar#pestanas::tab:selected {{ background: #ffffff; color: #1d1d1f; border-top: 2px solid {ACENTO}; }}
QTabBar#pestanas::tab:hover:!selected {{ background: #ededf1; }}
QStatusBar {{ background: #ffffff; border-top: 1px solid #dddde1; color: #55555c; }}
"""
