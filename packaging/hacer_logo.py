"""Dibuja el logotipo (las iniciales PF dentro de un corazón) en PNG e ICO.

Se ejecuta a mano cuando cambia el diseño: python packaging/hacer_logo.py
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

RAIZ = Path(__file__).resolve().parent.parent
LADO = 1024
FUENTE = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"


def corazon(lado):
    puntos = []
    for k in range(720):
        t = 2 * math.pi * k / 720
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        puntos.append((lado / 2 + x * lado / 36, lado * 0.47 - y * lado / 36))
    return puntos


def dibujar():
    img = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    # Sombra suave
    sombra = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    ImageDraw.Draw(sombra).polygon([(x, y + 18) for x, y in corazon(LADO)], fill=(120, 20, 30, 90))
    img.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(18)))
    # Corazón con degradado de coral a rojo
    mascara = Image.new("L", (LADO, LADO), 0)
    ImageDraw.Draw(mascara).polygon(corazon(LADO), fill=255)
    degradado = Image.new("RGBA", (LADO, LADO))
    d = ImageDraw.Draw(degradado)
    arriba, abajo = (240, 98, 98), (196, 48, 43)
    for y in range(LADO):
        f = y / LADO
        d.line([(0, y), (LADO, y), ], fill=tuple(int(a + (b - a) * f) for a, b in zip(arriba, abajo)) + (255,))
    img.paste(degradado, (0, 0), mascara)
    # Brillo arriba a la izquierda
    brillo = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    ImageDraw.Draw(brillo).ellipse((230, 200, 420, 330), fill=(255, 255, 255, 45))
    brillo = brillo.filter(ImageFilter.GaussianBlur(25))
    img.alpha_composite(Image.composite(brillo, Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0)), mascara))
    # Iniciales
    texto = ImageDraw.Draw(img)
    fuente = ImageFont.truetype(FUENTE, 360)
    caja = texto.textbbox((0, 0), "PF", font=fuente)
    ancho, alto = caja[2] - caja[0], caja[3] - caja[1]
    texto.text(((LADO - ancho) / 2 - caja[0], LADO * 0.43 - alto / 2 - caja[1]), "PF", font=fuente, fill="white")
    return img


if __name__ == "__main__":
    logo = dibujar()
    logo.resize((256, 256), Image.LANCZOS).save(RAIZ / "pdfcasero" / "recursos" / "icono.png")
    logo.resize((256, 256), Image.LANCZOS).save(
        RAIZ / "packaging" / "icono.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    )
    logo.save(Path(__file__).resolve().parent / "logo_1024.png")
