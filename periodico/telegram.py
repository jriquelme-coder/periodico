"""Publicación automática en un canal de Telegram (Bot API, gratuita).

Se activa sola si existen los secretos TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID.
Las imágenes se envían directamente desde GitHub Actions (no hace falta
alojarlas en ningún sitio). Si Telegram falla, las demás redes no se ven
afectadas.
"""
from __future__ import annotations

import html
import json
import logging
import os
from pathlib import Path

import requests

from .config import Ajustes
from .redactor import Post

log = logging.getLogger(__name__)
LIMITE_PIE = 1000  # Telegram admite 1024 caracteres en el pie de foto


class ErrorTelegram(RuntimeError):
    pass


def activo() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def _api(metodo: str, datos: dict, archivos: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/{metodo}"
    r = requests.post(url, data=datos, files=archivos, timeout=120)
    try:
        res = r.json()
    except ValueError:
        res = {"ok": False, "description": r.text[:200]}
    if not res.get("ok"):
        raise ErrorTelegram(res.get("description", "error desconocido"))
    return res["result"]


def texto(aj: Ajustes, p: Post, enlace_instagram: str) -> str:
    e = html.escape
    etiqueta = "#" + p.seccion.nombre.split(" ")[0].replace(",", "")
    partes = [f"<b>{e(p.titular)}</b>", e(p.entradilla)]
    if p.por_que_importa:
        partes.append(f"👉 {e(p.por_que_importa)}")
    if p.resumen_post:
        partes.append(e(p.resumen_post))
    cola = [f"Fuentes: {e(', '.join(dict.fromkeys(p.medios)))}"]
    if enlace_instagram:
        cola.append(f'📲 <a href="{e(enlace_instagram)}">Ver en Instagram</a> · {e(aj.usuario)}')
    else:
        cola.append(f"📲 Síguenos en Instagram: {e(aj.usuario)}")
    cola.append(etiqueta)
    pie = "\n".join(cola)
    cuerpo = ""
    for parte in partes:  # se añaden párrafos mientras quepan
        prueba = (cuerpo + "\n\n" + parte).strip()
        if len(prueba) + len(pie) + 2 > LIMITE_PIE:
            break
        cuerpo = prueba
    return f"{cuerpo}\n\n{pie}"


def publicar(aj: Ajustes, p: Post, imagenes: list[Path], enlace_instagram: str, video: Path | None = None) -> str:
    chat = os.environ["TELEGRAM_CHAT_ID"]
    pie = texto(aj, p, enlace_instagram)
    if video and video.exists():
        with video.open("rb") as fh:
            r = _api("sendVideo", {"chat_id": chat, "caption": pie, "parse_mode": "HTML",
                                   "supports_streaming": "true"}, {"video": fh})
        return str(r["message_id"])
    imagenes = imagenes[:10]  # máximo de Telegram por álbum
    if len(imagenes) == 1:
        with imagenes[0].open("rb") as fh:
            r = _api("sendPhoto", {"chat_id": chat, "caption": pie, "parse_mode": "HTML"}, {"photo": fh})
        return str(r["message_id"])
    media, archivos = [], {}
    for i, ruta in enumerate(imagenes):
        item = {"type": "photo", "media": f"attach://foto{i}"}
        if i == 0:
            item.update(caption=pie, parse_mode="HTML")
        media.append(item)
        archivos[f"foto{i}"] = ruta.open("rb")
    try:
        r = _api("sendMediaGroup", {"chat_id": chat, "media": json.dumps(media)}, archivos)
    finally:
        for fh in archivos.values():
            fh.close()
    log.info("✅ Publicado en Telegram (%s)", chat)
    return str(r[0]["message_id"])
