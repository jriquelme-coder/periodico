"""Recogida de noticias desde RSS de medios españoles y Google Noticias."""
from __future__ import annotations

import hashlib
import html
import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import feedparser
import requests

from .config import Seccion

log = logging.getLogger(__name__)
logging.getLogger("trafilatura").setLevel(logging.CRITICAL)
logging.getLogger("htmldate").setLevel(logging.CRITICAL)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
TIMEOUT = 15

STOPWORDS = set(
    "el la los las un una unos unas de del al a en y o u que se su sus por para con sin "
    "es son ha han lo le les como más mas pero sobre tras ante este esta estos estas ese esa "
    "ya no si sí muy hasta desde entre cuando donde quien qué que cómo como nuevo nueva".split()
)


@dataclass
class Noticia:
    id: str
    titulo: str
    resumen: str
    fuente: str
    url: str
    fecha: datetime
    cobertura: int = 1                     # nº de medios distintos que cuentan lo mismo
    relacionadas: list["Noticia"] = field(default_factory=list)

    def ficha(self, n: int) -> str:
        hace = int((datetime.now(timezone.utc) - self.fecha).total_seconds() // 60)
        cob = f" · cubierta por {self.cobertura} medios" if self.cobertura > 1 else ""
        return f"[{n}] ({self.fuente}, hace {hace} min{cob}) {self.titulo}\n    {self.resumen[:350]}"


def _limpiar(texto: str) -> str:
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    texto = html.unescape(texto)
    return re.sub(r"\s+", " ", texto).strip()


def _normalizar(texto: str) -> set[str]:
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    palabras = re.findall(r"[a-z0-9]{3,}", t)
    return {p for p in palabras if p not in STOPWORDS}


def similitud(a: str, b: str) -> float:
    A, B = _normalizar(a), _normalizar(b)
    if not A or not B:
        return 0.0
    return len(A & B) / min(len(A), len(B))


def url_google_news(consulta: str) -> str:
    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(f"{consulta} when:1d")
        + "&hl=es&gl=ES&ceid=ES:es"
    )


def _descargar(url: str) -> list[Noticia]:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        log.warning("Fuente caída %s: %s", url, e)
        return []
    feed = feedparser.parse(r.content)
    medio = _limpiar(feed.feed.get("title", "")) or url.split("/")[2]
    es_gnews = "news.google.com" in url
    salida = []
    for e in feed.entries[:60]:
        titulo = _limpiar(e.get("title", ""))
        if not titulo:
            continue
        fuente = medio
        if es_gnews:
            src = e.get("source") or {}
            fuente = src.get("title") or fuente
            # Google Noticias añade " - Medio" al final del titular
            if " - " in titulo:
                titulo, _, posible = titulo.rpartition(" - ")
                fuente = src.get("title") or posible
        resumen = _limpiar(e.get("summary", "") or e.get("description", ""))
        if es_gnews:
            resumen = ""  # el resumen de Google Noticias es solo una lista de enlaces
        fecha = None
        for k in ("published_parsed", "updated_parsed"):
            if e.get(k):
                fecha = datetime(*e[k][:6], tzinfo=timezone.utc)
                break
        if not fecha:
            fecha = datetime.now(timezone.utc)
        link = e.get("link", "")
        nid = hashlib.sha1((link or titulo).encode()).hexdigest()[:16]
        salida.append(Noticia(nid, titulo, resumen, fuente, link, fecha))
    return salida


def recoger(seccion: Seccion, horas_max: int, ya_publicadas: set[str], titulos_recientes: list[str]) -> list[Noticia]:
    urls = list(seccion.feeds) + [url_google_news(q) for q in seccion.google_news]
    with ThreadPoolExecutor(max_workers=8) as ex:
        bruto = [n for lote in ex.map(_descargar, urls) for n in lote]

    vistos: set[str] = set()
    bruto = [n for n in bruto if not (n.id in vistos or vistos.add(n.id))]

    limite = datetime.now(timezone.utc) - timedelta(hours=horas_max)
    futuro = datetime.now(timezone.utc) + timedelta(hours=1)
    candidatas = [
        n for n in bruto
        if limite <= n.fecha <= futuro
        and n.id not in ya_publicadas
        and n.url not in ya_publicadas
        and not any(similitud(n.titulo, t) >= 0.6 for t in titulos_recientes)
    ]

    # Agrupar la misma historia contada por varios medios
    candidatas.sort(key=lambda n: n.fecha, reverse=True)
    grupos: list[Noticia] = []
    for n in candidatas:
        for g in grupos:
            if similitud(n.titulo, g.titulo) >= 0.5:
                if n.fuente not in {g.fuente, *[r.fuente for r in g.relacionadas]}:
                    g.cobertura += 1
                g.relacionadas.append(n)
                # preferimos como principal la que tenga resumen y enlace directo
                if not g.resumen and n.resumen:
                    g.titulo, g.resumen, g.fuente, g.url, g.id = n.titulo, n.resumen, n.fuente, n.url, n.id
                break
        else:
            grupos.append(n)

    grupos.sort(key=lambda g: (g.cobertura, g.fecha), reverse=True)
    log.info("Sección %s: %d noticias en bruto → %d historias candidatas", seccion.id, len(bruto), len(grupos))
    return grupos[:40]


def texto_completo(url: str, max_chars: int = 7000) -> str:
    """Intenta leer el cuerpo del artículo para dar contexto a la IA (no se copia)."""
    if not url or "news.google.com" in url:
        return ""
    try:
        import trafilatura

        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        if r.status_code != 200:
            return ""
        texto = trafilatura.extract(r.text, include_comments=False, include_tables=False) or ""
        return texto[:max_chars]
    except Exception as e:  # noqa: BLE001
        log.info("No se pudo leer el artículo %s: %s", url, e)
        return ""


def comprobar(secciones: list[Seccion]) -> list[tuple[str, str, int]]:
    """Informe de salud de todas las fuentes: (sección, url, nº noticias)."""
    filas = []
    for s in secciones:
        for u in list(s.feeds) + [url_google_news(q) for q in s.google_news]:
            filas.append((s.id, u, len(_descargar(u))))
    return filas
