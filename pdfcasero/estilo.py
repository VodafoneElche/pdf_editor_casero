"""Aspecto visual: claro, sobrio y con un acento rojo parecido al de Adobe Reader."""

ACENTO = "#c4302b"

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
QListWidget#recientes::item:hover {{ background: #f3f3f6; }}
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
QStatusBar {{ background: #ffffff; border-top: 1px solid #dddde1; color: #55555c; }}
"""
