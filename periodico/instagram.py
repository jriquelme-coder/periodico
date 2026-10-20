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
            transitorio = err.get("is_transient") or r.status_code >= 500 or err.get("code") in (1, 2, 4, 17, 341)
            log.warning("Instagram %s %s → %s %s", metodo, ruta, r.status_code, err.get("message"))
            if not transitorio:
                break
            time.sleep(10 * (intento + 1))
        raise ErrorInstagram(f"{err.get('message', r.text)} (código {err.get('code')}, subcódigo {err.get('error_subcode')})")

    def cuota(self) -> tuple[int, int]:
        try:
            d = self._peticion("GET", f"{self.usuario}/content_publishing_limit", fields="quota_usage,config")
        except ErrorInstagram as e:
            log.warning("No se pudo consultar la cuota (%s); se continúa", e)
            return 0, 100
        fila = (d.get("data") or [{}])[0]
        uso = int(fila.get("quota_usage", 0))
        total = int((fila.get("config") or {}).get("quota_total", 100))
        return uso, total

    def _esperar(self, contenedor: str, max_seg: int = 300) -> None:
        inicio = time.time()
        while time.time() - inicio < max_seg:
            estado = self._peticion("GET", contenedor, fields="status_code").get("status_code")
            if estado == "FINISHED":
                return
            if estado in ("ERROR", "EXPIRED"):
                raise ErrorInstagram(f"El contenedor {contenedor} terminó en estado {estado}")
            time.sleep(5)
        raise ErrorInstagram(f"Tiempo de espera agotado para el contenedor {contenedor}")

    def publicar_carrusel(self, urls_imagenes: list[str], caption: str) -> tuple[str, str]:
        if len(urls_imagenes) == 1:
            c = self._peticion("POST", f"{self.usuario}/media", image_url=urls_imagenes[0], caption=caption)["id"]
        else:
            hijos = []
            for u in urls_imagenes[:20]:
                hijos.append(self._peticion("POST", f"{self.usuario}/media", image_url=u, is_carousel_item="true")["id"])
            for h in hijos:
                self._esperar(h)
            c = self._peticion("POST", f"{self.usuario}/media", media_type="CAROUSEL",
                               children=",".join(hijos), caption=caption)["id"]
        self._esperar(c)
        media_id = self._peticion("POST", f"{self.usuario}/media_publish", creation_id=c)["id"]
        try:
            enlace = self._peticion("GET", media_id, fields="permalink").get("permalink", "")
        except ErrorInstagram:
            enlace = ""
        return media_id, enlace


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
