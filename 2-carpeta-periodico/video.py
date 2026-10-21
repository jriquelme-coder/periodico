"""Reels (vídeo 9:16 con las tarjetas del carrusel) y Stories (imagen 9:16).

La música de fondo se genera por código (sin derechos de autor). Si quieres
usar tus propias pistas libres de derechos, deja archivos .mp3/.wav en la
carpeta `musica/` del repositorio y se elegirá una al azar.
"""
from __future__ import annotations

import logging
import math
import random
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .config import RAIZ, Ajustes
from .diseno import (NEGRITA, SEMI, TITULAR, MEDIA, ancho_espaciado, degradado, espaciado, mezcla, rgb,
                     texto_sobre)
from .redactor import Post

log = logging.getLogger(__name__)
VW, VH = 1080, 1920
FPS = 30
TRANSICION = 0.45


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return "ffmpeg"


# ── lienzo vertical ─────────────────────────────────────────────────────────

def _lienzo(aj: Ajustes, p: Post) -> Image.Image:
    base = rgb(p.seccion.color)
    return degradado(mezcla(base, (0, 0, 0), 0.55), mezcla(base, (0, 0, 0), 0.8)).resize((VW, VH))


def _cabecera_vertical(d: ImageDraw.ImageDraw, aj: Ajustes, p: Post, txt) -> None:
    f = NEGRITA(40)
    nombre = aj.nombre.upper()
    w = ancho_espaciado(nombre, f, 4) + 40
    x = (VW - w) / 2
    d.ellipse((x, 128, x + 22, 150), fill=(255, 59, 48))
    espaciado(d, (x + 40, 116), nombre, f, txt, 4)
    f2 = SEMI(30)
    sec = p.seccion.nombre.upper()
    w2 = ancho_espaciado(sec, f2, 3)
    espaciado(d, ((VW - w2) / 2, 186), sec, f2, (*txt, 190), 3)


def fotograma(aj: Ajustes, p: Post, tarjeta: Path) -> Image.Image:
    img = _lienzo(aj, p)
    d = ImageDraw.Draw(img, "RGBA")
    txt = (255, 255, 255)
    _cabecera_vertical(d, aj, p, txt)
    card = Image.open(tarjeta).convert("RGB").resize((972, 1215), Image.LANCZOS)
    sombra = Image.new("RGBA", (972 + 40, 1215 + 40), (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle((20, 26, 992, 1255), radius=36, fill=(0, 0, 0, 110))
    img.paste(sombra, (34, 270), sombra)
    mascara = Image.new("L", card.size, 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, *card.size), radius=32, fill=255)
    img.paste(card, (54, 290), mascara)
    f = MEDIA(34)
    t = f"Más noticias cada día en {aj.usuario}"
    d.text(((VW - f.getlength(t)) / 2, 1560), t, font=f, fill=(255, 255, 255, 210))
    return img


def story(aj: Ajustes, p: Post, portada: Path, carpeta: Path) -> Path:
    img = _lienzo(aj, p)
    d = ImageDraw.Draw(img, "RGBA")
    txt = (255, 255, 255)
    _cabecera_vertical(d, aj, p, txt)
    base = rgb(p.seccion.color)
    f = NEGRITA(34)
    etiqueta = "NUEVO POST"
    w = ancho_espaciado(etiqueta, f, 4) + 60
    d.rounded_rectangle(((VW - w) / 2, 270, (VW + w) / 2, 336), radius=33, fill=base)
    espaciado(d, ((VW - w) / 2 + 30, 283), etiqueta, f, texto_sobre(base), 4)
    card = Image.open(portada).convert("RGB").resize((864, 1080), Image.LANCZOS)
    mascara = Image.new("L", card.size, 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, *card.size), radius=32, fill=255)
    img.paste(card, (108, 380), mascara)
    f2 = TITULAR(52)
    t = "Léelo completo en el perfil"
    d.text(((VW - f2.getlength(t)) / 2, 1520), t, font=f2, fill=txt)
    f3 = MEDIA(36)
    t2 = f"Toca {aj.usuario} arriba ↑"
    d.text(((VW - f3.getlength(t2)) / 2, 1600), t2, font=f3, fill=(255, 255, 255, 200))
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / "story.jpg"
    img.convert("RGB").save(ruta, "JPEG", quality=90)
    return ruta


# ── música generada (sin derechos) ──────────────────────────────────────────

def _musica(segundos: float, ruta: Path, semilla: int) -> Path:
    propias = sorted((RAIZ / "musica").glob("*.mp3")) + sorted((RAIZ / "musica").glob("*.wav"))
    if propias:
        return random.Random(semilla).choice(propias)
    sr = 44100
    n = int(segundos * sr)
    t = np.arange(n) / sr
    rnd = random.Random(semilla)
    bpm = rnd.choice([92, 100, 108])
    compas = 4 * 60 / bpm
    progresiones = [
        [57, 53, 48, 55],  # Am F C G
        [48, 55, 57, 53],  # C G Am F
        [50, 55, 48, 57],  # Dm G C Am
    ]
    prog = rnd.choice(progresiones)
    menor = {57, 50, 52}
    audio = np.zeros(n)
    for i in range(int(math.ceil(segundos / compas)) + 1):
        raiz = prog[i % 4]
        tercera = 3 if raiz in menor else 4
        notas = [raiz, raiz + tercera, raiz + 7, raiz + 12]
        ini = int(i * compas * sr)
        fin = min(n, int((i + 1) * compas * sr) + int(0.3 * sr))
        if ini >= n:
            break
        tt = t[ini:fin] - t[ini]
        env = np.minimum(1, tt / 0.35) * np.exp(-tt * 0.35)
        pad = sum(np.sin(2 * np.pi * 440 * 2 ** ((m - 69) / 12) * tt * (1 + det)) for m in notas for det in (0, 0.003))
        bajo = np.sin(2 * np.pi * 440 * 2 ** ((raiz - 12 - 69) / 12) * tt)
        audio[ini:fin] += (pad / 8 * 0.5 + bajo * 0.25) * env
    # pulso suave en cada tiempo
    golpe = 60 / bpm
    for k in range(int(segundos / golpe) + 1):
        ini = int(k * golpe * sr)
        if ini >= n:
            break
        largo = min(n - ini, int(0.12 * sr))
        tt = np.arange(largo) / sr
        frec = 110 * np.exp(-tt * 25) + 45
        audio[ini:ini + largo] += 0.35 * np.sin(2 * np.pi * np.cumsum(frec) / sr) * np.exp(-tt * 30)
        off = ini + int(golpe / 2 * sr)
        if off + 2000 < n:
            ruido = np.random.default_rng(k).standard_normal(2000) * np.exp(-np.arange(2000) / 300)
            audio[off:off + 2000] += 0.04 * ruido
    fade = int(1.2 * sr)
    audio[:fade] *= np.linspace(0, 1, fade)
    audio[-fade:] *= np.linspace(1, 0, fade)
    audio = audio / (np.max(np.abs(audio)) + 1e-9) * 0.5
    datos = (audio * 32767).astype(np.int16)
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(datos.tobytes())
    return ruta


# ── montaje del vídeo ───────────────────────────────────────────────────────

def _duracion(i: int, total: int, p: Post) -> float:
    if i == 0 or i == total - 1:
        return 3.2
    textos = [s["texto"] for s in p.diapositivas]
    largo = max((len(x) for x in textos), default=200)
    return min(7.0, 2.6 + largo / 55)


def generar_reel(aj: Ajustes, p: Post, tarjetas: list[Path], carpeta: Path) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    fotos = []
    for i, t in enumerate(tarjetas):
        ruta = carpeta / f"v{i:02d}.jpg"
        fotograma(aj, p, t).convert("RGB").save(ruta, "JPEG", quality=92)
        fotos.append(ruta)
    dur = [_duracion(i, len(fotos), p) for i in range(len(fotos))]
    total = sum(dur) - TRANSICION * (len(fotos) - 1)
    musica = _musica(total + 0.5, carpeta / "musica.wav", hash(p.titular) & 0xFFFF)

    args = [_ffmpeg(), "-y", "-loglevel", "error"]
    for f, dd in zip(fotos, dur):
        args += ["-loop", "1", "-t", f"{dd:.2f}", "-i", str(f)]
    args += ["-i", str(musica)]
    filtros = [f"[{i}:v]scale={VW}:{VH},fps={FPS},format=yuv420p,settb=AVTB[v{i}]" for i in range(len(fotos))]
    previo, offset = "v0", 0.0
    efectos = ["slideleft", "smoothleft", "slideleft", "fade"]
    for i in range(1, len(fotos)):
        offset += dur[i - 1] - TRANSICION
        salida = f"x{i}"
        filtros.append(f"[{previo}][v{i}]xfade=transition={efectos[i % len(efectos)]}:"
                       f"duration={TRANSICION}:offset={offset:.2f}[{salida}]")
        previo = salida
    filtros.append(f"[{len(fotos)}:a]afade=t=out:st={max(0, total - 1.2):.2f}:d=1.2[a]")
    salida_mp4 = carpeta / "reel.mp4"
    args += ["-filter_complex", ";".join(filtros), "-map", f"[{previo}]", "-map", "[a]",
             "-t", f"{total:.2f}", "-c:v", "libx264", "-profile:v", "high", "-preset", "medium",
             "-crf", "21", "-pix_fmt", "yuv420p", "-r", str(FPS),
             "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", str(salida_mp4)]
    subprocess.run(args, check=True)
    log.info("Reel generado: %s (%.1f s)", salida_mp4, total)
    return salida_mp4
