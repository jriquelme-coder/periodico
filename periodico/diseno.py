"""Generación de las tarjetas del carrusel (JPEG 1080×1350, formato 4:5)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import DIR_FUENTES_TIPO, Ajustes
from .redactor import Post

W, H = 1080, 1350
M = 84  # margen lateral
PAPEL = (246, 243, 238)
TINTA = (17, 17, 17)
GRIS = (88, 88, 88)
NEGRO = (14, 16, 20)
MESES = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]

_cache: dict = {}


def fuente(nombre: str, tam: int, variacion: str | None = None) -> ImageFont.FreeTypeFont:
    clave = (nombre, tam, variacion)
    if clave not in _cache:
        f = ImageFont.truetype(str(DIR_FUENTES_TIPO / nombre), tam)
        if variacion:
            f.set_variation_by_name(variacion)
        _cache[clave] = f
    return _cache[clave]


TITULAR = lambda t: fuente("InterDisplay-Black.otf", t)  # noqa: E731
NEGRITA = lambda t: fuente("Inter-Bold.otf", t)  # noqa: E731
SEMI = lambda t: fuente("Inter-SemiBold.otf", t)  # noqa: E731
MEDIA = lambda t: fuente("Inter-Medium.otf", t)  # noqa: E731
NORMAL = lambda t: fuente("Inter-Regular.otf", t)  # noqa: E731
SERIF = lambda t: fuente("Lora-Variable.ttf", t, b"Regular")  # noqa: E731
SERIF_N = lambda t: fuente("Lora-Variable.ttf", t, b"Bold")  # noqa: E731
SERIF_I = lambda t: fuente("Lora-Italic-Variable.ttf", t, b"Medium")  # noqa: E731


# ── utilidades de color ─────────────────────────────────────────────────────

def rgb(hexa: str) -> tuple[int, int, int]:
    h = hexa.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def mezcla(a, b, t: float):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def luminancia(c) -> float:
    def canal(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(x) for x in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a, b) -> float:
    la, lb = sorted([luminancia(a), luminancia(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def acento_legible(color, fondo=PAPEL, minimo=4.5):
    c = color
    t = 0.0
    while contraste(c, fondo) < minimo and t < 0.9:
        t += 0.08
        c = mezcla(color, (0, 0, 0), t)
    return c


def texto_sobre(color):
    return TINTA if contraste(TINTA, color) > contraste((255, 255, 255), color) else (255, 255, 255)


# ── utilidades de texto ─────────────────────────────────────────────────────

def envolver(texto: str, f: ImageFont.FreeTypeFont, ancho: int) -> list[str]:
    lineas: list[str] = []
    for parrafo in texto.split("\n"):
        actual = ""
        for palabra in parrafo.split():
            prueba = f"{actual} {palabra}".strip()
            if f.getlength(prueba) <= ancho:
                actual = prueba
            else:
                if actual:
                    lineas.append(actual)
                actual = palabra
        lineas.append(actual)
    return lineas


def ajustar(texto: str, fabrica, ancho: int, alto: int, maximo: int, minimo: int, interlineado: float):
    """Busca el mayor tamaño de letra con el que el texto cabe en la caja."""
    tam = maximo
    while tam >= minimo:
        f = fabrica(tam)
        lineas = envolver(texto, f, ancho)
        if len(lineas) * tam * interlineado <= alto:
            return f, lineas, tam
        tam -= 2
    f = fabrica(minimo)
    lineas = envolver(texto, f, ancho)
    cab = max(1, int(alto // (minimo * interlineado)))
    if len(lineas) > cab:
        lineas = lineas[:cab]
        lineas[-1] = lineas[-1].rstrip(".,;:") + "…"
    return f, lineas, minimo


def pintar_lineas(d: ImageDraw.ImageDraw, x: int, y: int, lineas, f, tam, interlineado, color) -> int:
    for ln in lineas:
        d.text((x, y), ln, font=f, fill=color)
        y += int(tam * interlineado)
    return y


def espaciado(d, xy, texto, f, color, sep=4):
    x, y = xy
    for ch in texto:
        d.text((x, y), ch, font=f, fill=color)
        x += f.getlength(ch) + sep
    return x


def ancho_espaciado(texto, f, sep=4):
    return sum(f.getlength(c) + sep for c in texto) - sep


def fecha_corta(dt: datetime) -> str:
    return f"{dt.day} {MESES[dt.month - 1]} {dt.year} · {dt:%H:%M}"


# ── elementos comunes ───────────────────────────────────────────────────────

def degradado(c1, c2) -> Image.Image:
    """Degradado diagonal suave de c1 (arriba-izquierda) a c2 (abajo-derecha)."""
    import numpy as np

    y, x = np.mgrid[0:H, 0:W]
    t = ((x / W) * 0.35 + (y / H) * 0.65)[..., None]
    a, b = np.array(c1, float), np.array(c2, float)
    return Image.fromarray((a + (b - a) * t).astype("uint8"), "RGB")


def decoracion(img: Image.Image, color, alfa=38):
    """Anillos concéntricos suaves arriba a la derecha (identidad visual sin fotos)."""
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    cx, cy = W - 60, 250
    for i, r in enumerate(range(140, 900, 110)):
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(*color, max(8, alfa - i * 4)), width=3)
    img.paste(capa, (0, 0), capa)


def cabecera(d, aj: Ajustes, color_txt, color_punto, derecha: str):
    f = NEGRITA(30)
    d.ellipse((M, 78, M + 18, 96), fill=color_punto)
    espaciado(d, (M + 32, 70), aj.nombre.upper(), f, color_txt, 3)
    f2 = MEDIA(26)
    d.text((W - M - f2.getlength(derecha), 73), derecha, font=f2, fill=color_txt)


def puntos(d, total: int, actual: int, color_on, color_off, y=H - 92):
    r, sep = 7, 26
    x0 = W - M - (total - 1) * sep - r
    for i in range(total):
        c = color_on if i == actual else color_off
        rr = r if i == actual else 5
        x = x0 + i * sep
        d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=c)


# ── tarjetas ────────────────────────────────────────────────────────────────

def portada(aj: Ajustes, p: Post, ahora: datetime, total: int) -> Image.Image:
    base = rgb(p.seccion.color)
    oscuro = mezcla(base, (0, 0, 0), 0.35)
    img = degradado(base, oscuro)
    txt = texto_sobre(mezcla(base, oscuro, 0.5))
    claro = txt == (255, 255, 255)
    decoracion(img, (255, 255, 255) if claro else (0, 0, 0), 40)
    d = ImageDraw.Draw(img, "RGBA")
    suave = (*txt, 200)

    cabecera(d, aj, txt, txt, fecha_corta(ahora))

    # Etiqueta de sección
    f = NEGRITA(28)
    etiqueta = p.seccion.nombre.upper()
    aw = ancho_espaciado(etiqueta, f, 2)
    y = 170
    d.rounded_rectangle((M, y, M + aw + 48, y + 58), radius=29, fill=txt)
    espaciado(d, (M + 24, y + 12), etiqueta, f, mezcla(base, (0, 0, 0), 0.25) if claro else base, 2)

    # Bloque de titular, anclado abajo
    ancho = W - 2 * M
    fe, lin_e, te = ajustar(p.entradilla, MEDIA, ancho, 170, 38, 30, 1.32)
    alto_e = len(lin_e) * te * 1.32
    zona_tit_inf = H - 190 - alto_e - 40
    ft, lin_t, tt = ajustar(p.titular, TITULAR, ancho, zona_tit_inf - 420, 112, 62, 1.04)
    alto_t = len(lin_t) * tt * 1.04
    y_t = int(zona_tit_inf - alto_t)

    fa = NEGRITA(30)
    espaciado(d, (M, y_t - 64), p.antetitulo, fa, suave, 4)
    d.rectangle((M, y_t - 20, M + 90, y_t - 12), fill=txt)
    y = pintar_lineas(d, M - 3, y_t, lin_t, ft, tt, 1.04, txt)
    pintar_lineas(d, M, y + 44, lin_e, fe, te, 1.32, suave)

    d.line((M, H - 140, W - M, H - 140), fill=(*txt, 90), width=2)
    d.text((M, H - 112), "Desliza para leer  →", font=SEMI(30), fill=txt)
    puntos(d, total, 0, txt, (*txt, 90))
    return img


def tarjeta(aj: Ajustes, p: Post, n: int, total: int, titulo: str, texto: str, orden: int) -> Image.Image:
    base = rgb(p.seccion.color)
    acento = acento_legible(base)
    img = Image.new("RGB", (W, H), PAPEL)
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle((0, 0, 18, H), fill=base)

    cabecera(d, aj, TINTA, base, f"{n + 1}/{total}")
    f = NEGRITA(26)
    espaciado(d, (M, 140), p.seccion.nombre.upper(), f, acento, 3)

    numero = f"{orden:02d}"
    fn = TITULAR(150)
    d.text((M - 6, 210), numero, font=fn, fill=(*base, 70))

    ancho = W - 2 * M
    ft, lin_t, tt = ajustar(titulo, NEGRITA, ancho, 230, 68, 46, 1.12)
    y = pintar_lineas(d, M, 400, lin_t, ft, tt, 1.12, TINTA)
    d.rectangle((M, y + 26, M + 70, y + 32), fill=acento)
    y += 70
    fx, lin_x, tx = ajustar(texto, SERIF, ancho, H - 200 - y, 54, 34, 1.45)
    pintar_lineas(d, M, y, lin_x, fx, tx, 1.45, (40, 40, 40))

    d.line((M, H - 140, W - M, H - 140), fill=(0, 0, 0, 40), width=2)
    d.text((M, H - 112), aj.usuario, font=SEMI(28), fill=GRIS)
    puntos(d, total, n, acento, (0, 0, 0, 50))
    return img


def dato(aj: Ajustes, p: Post, n: int, total: int) -> Image.Image:
    base = rgb(p.seccion.color)
    img = degradado(mezcla(base, (0, 0, 0), 0.15), mezcla(base, (0, 0, 0), 0.45))
    txt = texto_sobre(mezcla(base, (0, 0, 0), 0.3))
    d = ImageDraw.Draw(img, "RGBA")
    cabecera(d, aj, txt, txt, f"{n + 1}/{total}")
    espaciado(d, (M, 300), "EL DATO", NEGRITA(34), (*txt, 210), 6)
    d.rectangle((M, 356, M + 90, 364), fill=txt)

    ancho = W - 2 * M
    tam = 300
    while tam > 90 and TITULAR(tam).getlength(p.dato_cifra) > ancho:
        tam -= 6
    d.text((M - 8, 420), p.dato_cifra, font=TITULAR(tam), fill=txt)
    y = 420 + int(tam * 1.15) + 30
    fx, lin, tx = ajustar(p.dato_explicacion, SEMI, ancho, 330, 52, 36, 1.3)
    pintar_lineas(d, M, y, lin, fx, tx, 1.3, txt)

    d.line((M, H - 140, W - M, H - 140), fill=(*txt, 90), width=2)
    d.text((M, H - 112), aj.usuario, font=SEMI(28), fill=txt)
    puntos(d, total, n, txt, (*txt, 90))
    return img


def cierre(aj: Ajustes, p: Post, n: int, total: int) -> Image.Image:
    base = rgb(p.seccion.color)
    img = Image.new("RGB", (W, H), NEGRO)
    decoracion(img, base, 50)
    d = ImageDraw.Draw(img, "RGBA")
    blanco = (255, 255, 255)
    acento = base if contraste(base, NEGRO) >= 3 else mezcla(base, blanco, 0.45)
    cabecera(d, aj, blanco, acento, f"{n + 1}/{total}")

    espaciado(d, (M, 250), "EN UNA FRASE", NEGRITA(32), acento, 6)
    ancho = W - 2 * M
    ff, lin, tf = ajustar(p.en_una_frase, SERIF_N, ancho, 420, 68, 44, 1.3)
    y = pintar_lineas(d, M, 320, lin, ff, tf, 1.3, blanco)

    fuentes = "Fuentes: " + ", ".join(dict.fromkeys(p.medios))
    fs, lin_s, ts = ajustar(fuentes, NORMAL, ancho, 80, 28, 22, 1.35)
    pintar_lineas(d, M, y + 40, lin_s, fs, ts, 1.35, (255, 255, 255, 150))

    # Llamada a la acción
    caja_y = H - 430
    d.rounded_rectangle((M, caja_y, W - M, caja_y + 230), radius=28, fill=(255, 255, 255, 18),
                        outline=(255, 255, 255, 50), width=2)
    d.text((M + 44, caja_y + 42), "¿Te ha sido útil?", font=NEGRITA(44), fill=blanco)
    d.text((M + 44, caja_y + 112), "Guárdalo, compártelo y síguenos en", font=MEDIA(34), fill=(255, 255, 255, 200))
    d.text((M + 44, caja_y + 158), aj.usuario, font=NEGRITA(36), fill=acento)

    d.line((M, H - 140, W - M, H - 140), fill=(255, 255, 255, 60), width=2)
    d.text((M, H - 112), aj.eslogan, font=SEMI(28), fill=(255, 255, 255, 170))
    puntos(d, total, n, acento, (255, 255, 255, 70))
    return img


def generar(aj: Ajustes, p: Post, ahora: datetime, carpeta: Path) -> list[Path]:
    carpeta.mkdir(parents=True, exist_ok=True)
    hay_dato = bool(p.dato_cifra.strip()) and len(p.dato_cifra) <= 12
    total = 1 + len(p.diapositivas) + (1 if hay_dato else 0) + 1
    imagenes = [portada(aj, p, ahora, total)]
    n = 1
    for i, s in enumerate(p.diapositivas):
        imagenes.append(tarjeta(aj, p, n, total, s["titulo"], s["texto"], i + 1))
        n += 1
        if hay_dato and i == 0:  # el dato va justo después de la primera tarjeta
            imagenes.append(dato(aj, p, n, total))
            n += 1
    imagenes.append(cierre(aj, p, n, total))

    rutas = []
    for i, im in enumerate(imagenes, 1):
        ruta = carpeta / f"{i:02d}.jpg"
        im.convert("RGB").save(ruta, "JPEG", quality=90, optimize=True, progressive=False)
        rutas.append(ruta)
    return rutas
