# Doble clic en Windows para abrir PDF Casero sin ventana de consola.
import multiprocessing
import sys

if __name__ == "__main__":
    # Necesario en el .exe: el OCR usa procesos aparte que arrancan este mismo programa
    multiprocessing.freeze_support()
    from pdfcasero.__main__ import main

    sys.exit(main())
