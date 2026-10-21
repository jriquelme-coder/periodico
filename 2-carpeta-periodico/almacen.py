"""Estado (qué se ha publicado) y alojamiento público de las imágenes.

En GitHub Actions se usa una rama aparte llamada `datos`, que se reescribe en
cada ejecución (commit huérfano), así el repositorio no engorda nunca:
  · datos/estado.json        → historial de publicaciones
  · datos/media/<slot>/*.jpg → imágenes del post en curso (Instagram las
                               descarga desde raw.githubusercontent.com)
Fuera de GitHub (pruebas en tu ordenador) se usa la carpeta local `.datos/`.

Alternativa: si defines CLOUDINARY_URL, las imágenes se suben a Cloudinary
(útil si prefieres que el repositorio sea privado).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from .config import RAIZ

log = logging.getLogger(__name__)
RAMA = "datos"
DIAS_HISTORIAL = 7


def _en_github() -> bool:
    return bool(os.getenv("GITHUB_ACTIONS") and os.getenv("GITHUB_REPOSITORY"))


def _git(*args: str, cwd: Path | str | None = None, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd or RAIZ, check=check, capture_output=True, text=True)


def _remoto() -> str:
    if os.getenv("DATOS_REMOTO"):  # solo para pruebas
        return os.environ["DATOS_REMOTO"]
    token = os.environ["GITHUB_TOKEN"]
    return f"https://x-access-token:{token}@github.com/{os.environ['GITHUB_REPOSITORY']}.git"


class Almacen:
    def __init__(self) -> None:
        self.github = _en_github()
        self.local = RAIZ / ".datos"
        self.estado: dict = {"publicaciones": []}
        self._media: dict[str, Path] = {}  # ruta_publicada -> fichero local
        self.sha = ""

    # ── estado ──────────────────────────────────────────────────────────
    def cargar(self) -> dict:
        texto = None
        if self.github:
            with tempfile.TemporaryDirectory() as tmp:
                _git("init", "-q", cwd=tmp)
                r = _git("fetch", "-q", "--depth", "1", _remoto(), RAMA, cwd=tmp, check=False)
                if r.returncode == 0:
                    s = _git("show", "FETCH_HEAD:estado.json", cwd=tmp, check=False)
                    texto = s.stdout if s.returncode == 0 else None
                elif "couldn't find remote ref" not in r.stderr:
                    raise RuntimeError("No se pudo leer la rama 'datos'")
        else:
            f = self.local / "estado.json"
            texto = f.read_text(encoding="utf-8") if f.exists() else None
        if texto:
            self.estado = json.loads(texto)
        self.estado.setdefault("publicaciones", [])
        return self.estado

    def slot_hecho(self, slot: str) -> bool:
        return any(p.get("slot") == slot for p in self.estado["publicaciones"])

    def registrar(self, entrada: dict) -> None:
        pubs = self.estado["publicaciones"]
        pubs.append(entrada)
        limite = (datetime.now(timezone.utc) - timedelta(days=DIAS_HISTORIAL)).isoformat()
        self.estado["publicaciones"] = [p for p in pubs if p.get("fecha", "") >= limite]

    def registrar_fallo(self, noticia_id: str | None, error: str) -> None:
        fallos = self.estado.setdefault("fallidas", [])
        if noticia_id:
            fallos.append({"id": noticia_id, "error": error[:300],
                           "fecha": datetime.now(timezone.utc).isoformat()})
        self.estado["fallidas"] = fallos[-300:]

    def ids_usados(self) -> set[str]:
        s = {f["id"] for f in self.estado.get("fallidas", []) if f.get("id")}
        for p in self.estado["publicaciones"]:
            s.update(x for x in (p.get("noticia_id"), p.get("url_fuente")) if x)
        return s

    def titulos_recientes(self, horas: int = 30) -> list[str]:
        limite = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()
        return [p["titular"] for p in reversed(self.estado["publicaciones"])
                if p.get("fecha", "") >= limite and p.get("titular")]

    # ── imágenes ────────────────────────────────────────────────────────
    def subir_imagenes(self, slot: str, rutas: list[Path]) -> list[str]:
        if os.getenv("CLOUDINARY_URL"):
            return [self._cloudinary(slot, r) for r in rutas]
        carpeta = "media/" + slot.replace("#", "-")
        self._media = {f"{carpeta}/{r.name}": r for r in rutas}
        self.guardar()
        if not self.github:
            return [str(r.resolve()) for r in rutas]
        repo = os.environ["GITHUB_REPOSITORY"]
        urls = []
        for k in self._media:
            raw = f"https://raw.githubusercontent.com/{repo}/{RAMA}/{k}"
            if k.endswith(".mp4") and self.sha:
                # Los vídeos se sirven por jsDelivr (CDN gratuito) con el tipo correcto video/mp4
                cdn = f"https://cdn.jsdelivr.net/gh/{repo}@{self.sha}/{k}"
                try:
                    self._esperar_publicas([cdn])
                    urls.append(cdn)
                    continue
                except RuntimeError:
                    log.warning("jsDelivr no respondió; se usa raw.githubusercontent")
            self._esperar_publicas([raw])
            urls.append(raw)
        return urls

    def _esperar_publicas(self, urls: list[str]) -> None:
        for u in urls:
            for intento in range(20):
                try:
                    r = requests.head(u, timeout=10, allow_redirects=True)
                    if r.status_code == 200:
                        break
                except requests.RequestException:
                    pass
                time.sleep(3)
            else:
                raise RuntimeError(
                    f"La imagen {u} no es accesible públicamente. ¿El repositorio es público? "
                    "Si quieres un repositorio privado, configura CLOUDINARY_URL."
                )

    def _cloudinary(self, slot: str, ruta: Path) -> str:
        # CLOUDINARY_URL = cloudinary://API_KEY:API_SECRET@CLOUD_NAME
        url = os.environ["CLOUDINARY_URL"].removeprefix("cloudinary://")
        cred, nube = url.split("@", 1)
        clave, secreto = cred.split(":", 1)
        ts = str(int(time.time()))
        public_id = f"{slot.replace('#', '-')}-{ruta.stem}"
        firma_base = f"folder=periodico&public_id={public_id}&timestamp={ts}{secreto}"
        firma = hashlib.sha1(firma_base.encode()).hexdigest()
        with ruta.open("rb") as fh:
            r = requests.post(
                f"https://api.cloudinary.com/v1_1/{nube}/{'video' if ruta.suffix == '.mp4' else 'image'}/upload",
                data={"api_key": clave, "timestamp": ts, "public_id": public_id,
                      "folder": "periodico", "signature": firma},
                files={"file": fh}, timeout=60,
            )
        r.raise_for_status()
        return r.json()["secure_url"]

    # ── persistencia ────────────────────────────────────────────────────
    def guardar(self, conservar_media: bool = True) -> None:
        if not conservar_media:
            self._media = {}
        datos = json.dumps(self.estado, ensure_ascii=False, indent=1)
        if not self.github:
            self.local.mkdir(exist_ok=True)
            (self.local / "estado.json").write_text(datos, encoding="utf-8")
            return
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "estado.json").write_text(datos, encoding="utf-8")
            for destino, origen in self._media.items():
                (t / destino).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(origen, t / destino)
            _git("init", "-q", "-b", RAMA, cwd=t)
            _git("config", "user.name", "periodico-bot", cwd=t)
            _git("config", "user.email", "periodico-bot@users.noreply.github.com", cwd=t)
            _git("add", "-A", cwd=t)
            _git("commit", "-q", "-m", f"estado {datetime.now(timezone.utc):%Y-%m-%d %H:%M}", cwd=t)
            self.sha = _git("rev-parse", "HEAD", cwd=t).stdout.strip()
            for intento in range(3):
                r = _git("push", "-q", "--force", _remoto(), f"{RAMA}:{RAMA}", cwd=t, check=False)
                if r.returncode == 0:
                    return
                time.sleep(5)
            raise RuntimeError("No se pudo guardar en la rama 'datos': " + r.stderr.replace(os.environ.get("GITHUB_TOKEN", "x"), "***"))
