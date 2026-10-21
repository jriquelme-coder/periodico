"""Carga de ajustes (config/*.yaml) y variables de entorno (secretos)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
DIR_CONFIG = RAIZ / "config"
DIR_FUENTES_TIPO = RAIZ / "fonts"


@dataclass
class Seccion:
    id: str
    nombre: str
    color: str
    enfoque: str
    feeds: list[str] = field(default_factory=list)
    google_news: list[str] = field(default_factory=list)
    hashtags_base: list[str] = field(default_factory=list)
    peso: float = 1.0


@dataclass
class Ajustes:
    nombre: str
    usuario: str
    hashtag_marca: str
    eslogan: str
    posts_por_dia: int
    stories_por_dia: int
    horas_reels: list[str]
    zona_horaria: str
    max_hashtags: int
    diapositivas_min: int
    diapositivas_max: int
    horas_maximas_noticia: int
    margen_cuota: int
    modelo_seleccion: str
    modelo_redaccion: str
    secciones: list[Seccion]

    @property
    def minutos_intervalo(self) -> int:
        return (24 * 60) // self.posts_por_dia

    def seccion(self, sid: str) -> Seccion:
        for s in self.secciones:
            if s.id == sid:
                return s
        raise KeyError(f"Sección desconocida: {sid}. Opciones: {[s.id for s in self.secciones]}")


def cargar() -> Ajustes:
    a = yaml.safe_load((DIR_CONFIG / "ajustes.yaml").read_text(encoding="utf-8"))
    s = yaml.safe_load((DIR_CONFIG / "secciones.yaml").read_text(encoding="utf-8"))
    p, pub, ia = a["periodico"], a["publicacion"], a["ia"]
    secciones = [
        Seccion(
            id=x["id"], nombre=x["nombre"], color=x["color"], enfoque=x.get("enfoque", ""),
            feeds=x.get("feeds") or [], google_news=x.get("google_news") or [],
            hashtags_base=x.get("hashtags_base") or [], peso=float(x.get("peso", 1)),
        )
        for x in s["secciones"]
    ]
    return Ajustes(
        nombre=os.getenv("NOMBRE_PERIODICO") or p["nombre"],
        usuario=os.getenv("USUARIO_INSTAGRAM") or p["usuario_instagram"],
        hashtag_marca=(os.getenv("HASHTAG_MARCA") or p["hashtag_marca"]).lstrip("#"),
        eslogan=p.get("eslogan", ""),
        posts_por_dia=int(os.getenv("POSTS_POR_DIA") or pub["posts_por_dia"]),
        stories_por_dia=int(os.getenv("STORIES_POR_DIA") or pub.get("stories_por_dia", 0)),
        horas_reels=list(pub.get("horas_reels") or []),
        zona_horaria=pub["zona_horaria"],
        max_hashtags=int(pub["max_hashtags"]),
        diapositivas_min=int(pub["diapositivas_min"]),
        diapositivas_max=int(pub["diapositivas_max"]),
        horas_maximas_noticia=int(pub["horas_maximas_noticia"]),
        margen_cuota=int(pub["margen_cuota"]),
        modelo_seleccion=os.getenv("MODELO_SELECCION") or ia["modelo_seleccion"],
        modelo_redaccion=os.getenv("MODELO_REDACCION") or ia["modelo_redaccion"],
        secciones=secciones,
    )


def secreto(nombre: str, obligatorio: bool = True) -> str | None:
    v = os.getenv(nombre)
    if obligatorio and not v:
        raise RuntimeError(
            f"Falta la variable {nombre}. Añádela en GitHub → Settings → Secrets and variables → Actions."
        )
    return v
