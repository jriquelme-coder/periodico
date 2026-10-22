"""Publicación automática en Threads (API oficial de Meta).

Se activa sola si existe el secreto THREADS_ACCESS_TOKEN. Cada noticia que se
publica en Instagram se publica también en Threads como carrusel de imágenes,
con un texto corto y el enlace al post de Instagram. Si Threads falla, el
post de Instagram no se ve afectado.
"""
from __future__ import annotations

import logging
import os
import time

import requests

from .config import Ajustes
from .redactor import Post

log = logging.getLogger(__name__)
BASE = "https://graph.threads.net/v1.0"
LIMITE_TEXTO = 480  # Threads admite 500; se deja margen (los emojis cuentan más)


class ErrorThreads(RuntimeError):
    pass


def activo() -> bool:
    return bool(os.getenv("THREADS_ACCESS_TOKEN"))


def _peticion(metodo: str, ruta: str, **params) -> dict:
    params["access_token"] = os.environ["THREADS_ACCESS_TOKEN"]
    url = f"{BASE}/{ruta}"
    r = requests.get(url, params=params, timeout=60) if metodo == "GET" else requests.post(url, data=params, timeout=60)
    datos = r.json() if r.content else {}
    if not r.ok or "error" in datos:
        err = datos.get("error", {})
        raise ErrorThreads(f"{err.get('message', r.text)} (código {err.get('code')}, subcódigo {err.get('error_subcode')})")
    return datos


def _esperar(contenedor: str, max_seg: int = 180) -> None:
    inicio = time.time()
    time.sleep(15)
    while time.time() - inicio < max_seg:
        d = _peticion("GET", contenedor, fields="status,error_message")
        if d.get("status") in ("FINISHED", "PUBLISHED"):
            return
        if d.get("status") in ("ERROR", "EXPIRED"):
            raise ErrorThreads(f"Contenedor de Threads en estado {d.get('status')}: {d.get('error_message')}")
        time.sleep(15)
    raise ErrorThreads("Tiempo de espera agotado en Threads")


def _corta(t: str, n: int) -> str:
    t = (t or "").strip()
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def texto(aj: Ajustes, p: Post, enlace_instagram: str) -> str:
    etiqueta = "#" + p.seccion.nombre.split(" ")[0].replace(",", "")
    cola = f"\n\n📲 Más en Instagram: {enlace_instagram}" if enlace_instagram else f"\n\n📲 Más en Instagram: {aj.usuario}"
    cola += f"\n{etiqueta}"
    cuerpo_max = LIMITE_TEXTO - len(cola)
    partes = [p.titular, p.entradilla, f"👉 {p.por_que_importa}" if p.por_que_importa else ""]
    cuerpo = "\n\n".join(x for x in partes if x)
    return _corta(cuerpo, cuerpo_max) + cola


def _crear(uid: str, urls: list[str], **params) -> str:
    """Crea un contenedor de imagen probando varias direcciones de la misma imagen.

    El error 2207052 («Media download has failed») significa que el robot de
    Threads no pudo descargar la imagen. Suele ser pasajero o depender del
    servidor, así que se reintenta y se prueba con otra dirección (CDN).
    """
    ultimo: Exception | None = None
    for intento in range(3):
        for url in urls:
            try:
                return _peticion("POST", f"{uid}/threads", image_url=url, **params)["id"]
            except ErrorThreads as e:
                ultimo = e
                log.warning("Threads no pudo descargar %s (intento %d): %s", url, intento + 1, e)
        time.sleep(15 * (intento + 1))
    raise ultimo or ErrorThreads("No se pudo crear el contenedor")


def publicar(aj: Ajustes, p: Post, urls_imagenes: list[str], enlace_instagram: str,
             urls_alternativas: list[str] | None = None) -> str:
    usuario = _peticion("GET", "me", fields="id,username")
    uid = usuario["id"]
    t = texto(aj, p, enlace_instagram)
    alt = urls_alternativas or []
    # Primero el CDN (más fiable para el robot de Threads) y luego la dirección directa
    opciones = [[a, u] if i < len(alt) and (a := alt[i]) else [u] for i, u in enumerate(urls_imagenes[:20])]
    contenedor = None
    try:
        if len(opciones) >= 2:
            hijos = [_crear(uid, o, media_type="IMAGE", is_carousel_item="true") for o in opciones]
            contenedor = _peticion("POST", f"{uid}/threads", media_type="CAROUSEL", children=",".join(hijos), text=t)["id"]
        elif opciones:
            contenedor = _crear(uid, opciones[0], media_type="IMAGE", text=t)
        if contenedor:
            _esperar(contenedor)
    except ErrorThreads as e:
        # Si las imágenes no se pueden subir, al menos se publica la noticia como texto
        log.warning("Imágenes no disponibles para Threads (%s); se publica solo el texto", e)
        contenedor = None
    if not contenedor:
        contenedor = _peticion("POST", f"{uid}/threads", media_type="TEXT", text=t)["id"]
        _esperar(contenedor)
    media_id = _peticion("POST", f"{uid}/threads_publish", creation_id=contenedor)["id"]
    log.info("✅ Publicado en Threads (@%s): %s", usuario.get("username"), media_id)
    return media_id


def renovar_token(token: str) -> tuple[str, int]:
    r = requests.get("https://graph.threads.net/refresh_access_token",
                     params={"grant_type": "th_refresh_token", "access_token": token}, timeout=30)
    d = r.json()
    if "access_token" not in d:
        raise ErrorThreads(f"No se pudo renovar el token de Threads: {d}")
    return d["access_token"], int(d.get("expires_in", 0))
