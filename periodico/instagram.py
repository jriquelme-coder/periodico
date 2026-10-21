"""Publicación de carruseles con la API oficial de Instagram (Content Publishing API)."""
from __future__ import annotations

import logging
import os
import time

import requests

from .config import secreto

log = logging.getLogger(__name__)


class ErrorInstagram(RuntimeError):
    pass


class LimiteInstagram(ErrorInstagram):
    """Se ha alcanzado el límite de llamadas a la API: hay que esperar, no reintentar ya."""


CODIGOS_LIMITE = {4, 17, 32, 613, 80002}


class Instagram:
    def __init__(self) -> None:
        self.token = secreto("IG_ACCESS_TOKEN")
        host = os.getenv("IG_GRAPH_HOST") or "graph.instagram.com"  # o graph.facebook.com
        version = os.getenv("IG_API_VERSION") or "v26.0"
        self.base = f"https://{host}/{version}"
        self.usuario = secreto("IG_USER_ID", obligatorio=False) or ""
        if host == "graph.instagram.com":
            # El ID correcto se obtiene del propio token: así no hace falta copiarlo a mano.
            try:
                yo = self._peticion("GET", "me", fields="user_id,username")
                self.usuario = str(yo.get("user_id") or yo.get("id"))
                log.info("Cuenta de Instagram: @%s (ID %s)", yo.get("username"), self.usuario)
            except ErrorInstagram as e:
                log.warning("No se pudo leer la cuenta del token (%s); se usa IG_USER_ID", e)
        if not self.usuario:
            raise ErrorInstagram("No se pudo determinar el ID de la cuenta de Instagram. Revisa IG_ACCESS_TOKEN.")

    def _peticion(self, metodo: str, ruta: str, **params) -> dict:
        params["access_token"] = self.token
        url = f"{self.base}/{ruta}"
        for intento in range(4):
            if metodo == "GET":
                r = requests.get(url, params=params, timeout=60)
            else:
                r = requests.post(url, data=params, timeout=60)
            datos = r.json() if r.content else {}
            if r.ok and "error" not in datos:
                return datos
            err = datos.get("error", {})
            log.warning("Instagram %s %s → %s %s", metodo, ruta, r.status_code, err.get("message"))
            if err.get("code") in CODIGOS_LIMITE or "limit reached" in str(err.get("message", "")).lower():
                raise LimiteInstagram(f"Límite de la API de Instagram alcanzado: {err.get('message')}")
            transitorio = err.get("is_transient") or r.status_code >= 500 or err.get("code") in (1, 2, 341)
            if not transitorio:
                break
            time.sleep(10 * (intento + 1))
        raise ErrorInstagram(f"{err.get('message', r.text)} (código {err.get('code')}, subcódigo {err.get('error_subcode')})")

    def cuota(self) -> tuple[int, int]:
        try:
            d = self._peticion("GET", f"{self.usuario}/content_publishing_limit", fields="quota_usage,config")
        except LimiteInstagram:
            raise
        except ErrorInstagram as e:
            log.warning("No se pudo consultar la cuota (%s); se continúa", e)
            return 0, 100
        fila = (d.get("data") or [{}])[0]
        uso = int(fila.get("quota_usage", 0))
        total = int((fila.get("config") or {}).get("quota_total", 100))
        return uso, total

    def _esperar(self, contenedor: str, max_seg: int = 300, intervalo: int = 10) -> None:
        """Comprueba el estado con pocas llamadas para no gastar el límite de la API."""
        inicio = time.time()
        time.sleep(min(intervalo, 5))
        while time.time() - inicio < max_seg:
            d = self._peticion("GET", contenedor, fields="status_code,status")
            estado = d.get("status_code")
            if estado == "FINISHED":
                return
            if estado in ("ERROR", "EXPIRED"):
                raise ErrorInstagram(f"El contenedor {contenedor} terminó en estado {estado}: {d.get('status')}")
            time.sleep(intervalo)
        raise ErrorInstagram(f"Tiempo de espera agotado para el contenedor {contenedor}")

    def publicar_carrusel(self, urls_imagenes: list[str], caption: str) -> tuple[str, str]:
        if len(urls_imagenes) == 1:
            c = self._peticion("POST", f"{self.usuario}/media", image_url=urls_imagenes[0], caption=caption)["id"]
        else:
            hijos = []
            for u in urls_imagenes[:20]:
                hijos.append(self._peticion("POST", f"{self.usuario}/media", image_url=u, is_carousel_item="true")["id"])
            time.sleep(10)  # las imágenes suelen estar listas en segundos
            for h in hijos:
                self._esperar(h, intervalo=15)
            c = self._peticion("POST", f"{self.usuario}/media", media_type="CAROUSEL",
                               children=",".join(hijos), caption=caption)["id"]
        return _publicar_contenedor(self, c)

    def publicar(self, contenedor: str) -> str:
        """media_publish con reintentos. El error genérico de Meta (subcódigo 2207085)
        suele ser pasajero y, a veces, el post se publica aunque la API diga que no."""
        ultimo = None
        for intento in range(4):
            try:
                return self._peticion("POST", f"{self.usuario}/media_publish", creation_id=contenedor)["id"]
            except LimiteInstagram:
                raise
            except ErrorInstagram as e:
                ultimo = e
                log.warning("media_publish falló (intento %d): %s", intento + 1, e)
                time.sleep(20 * (intento + 1))
                try:
                    estado = self._peticion("GET", contenedor, fields="status_code").get("status_code")
                except ErrorInstagram:
                    estado = None
                if estado == "PUBLISHED":
                    log.info("El contenedor ya figura como publicado")
                    recientes = self._peticion("GET", f"{self.usuario}/media", fields="id", limit=1).get("data") or []
                    if recientes:
                        return recientes[0]["id"]
        raise ultimo


def _publicar_contenedor(ig: "Instagram", contenedor: str, max_seg: int = 600, intervalo: int = 10) -> tuple[str, str]:
    ig._esperar(contenedor, max_seg, intervalo)
    media_id = ig.publicar(contenedor)
    try:
        enlace = ig._peticion("GET", media_id, fields="permalink").get("permalink", "")
    except ErrorInstagram:
        enlace = ""
    return media_id, enlace


def publicar_reel(ig: "Instagram", url_video: str, caption: str, url_portada: str | None = None) -> tuple[str, str]:
    params = dict(media_type="REELS", video_url=url_video, caption=caption, share_to_feed="true")
    if url_portada:
        params["cover_url"] = url_portada
    c = ig._peticion("POST", f"{ig.usuario}/media", **params)["id"]
    return _publicar_contenedor(ig, c, 900, 20)


def publicar_story(ig: "Instagram", url_imagen: str) -> tuple[str, str]:
    c = ig._peticion("POST", f"{ig.usuario}/media", media_type="STORIES", image_url=url_imagen)["id"]
    return _publicar_contenedor(ig, c, 180)


def renovar_token_instagram(token: str) -> tuple[str, int]:
    """Renueva un token de larga duración de 'Instagram API with Instagram Login' (dura 60 días)."""
    r = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=30,
    )
    d = r.json()
    if "access_token" not in d:
        raise ErrorInstagram(f"No se pudo renovar el token: {d}")
    return d["access_token"], int(d.get("expires_in", 0))
