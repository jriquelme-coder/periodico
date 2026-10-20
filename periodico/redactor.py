"""Selección y redacción de la noticia con Claude (API de Anthropic)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

import anthropic

from .config import Ajustes, Seccion, secreto
from .fuentes import Noticia, texto_completo

log = logging.getLogger(__name__)

# ── Esquemas de salida ──────────────────────────────────────────────────────

HERRAMIENTA_ELEGIR = {
    "name": "elegir_noticia",
    "description": "Devuelve la noticia elegida para publicar.",
    "input_schema": {
        "type": "object",
        "properties": {
            "indice": {"type": "integer", "description": "Número [n] de la noticia elegida, o -1 si ninguna sirve."},
            "relacionadas": {"type": "array", "items": {"type": "integer"},
                             "description": "Hasta 3 números de otras noticias que cuentan la MISMA historia (para contrastar)."},
            "motivo": {"type": "string"},
        },
        "required": ["indice", "relacionadas", "motivo"],
    },
}


def _herramienta_carrusel(aj: Ajustes) -> dict:
    n_tags = max(1, aj.max_hashtags - 1)
    return {
        "name": "publicar_carrusel",
        "description": "Devuelve el contenido completo del post de Instagram.",
        "input_schema": {
            "type": "object",
            "properties": {
                "apto": {"type": "boolean", "description": "false si la información no basta para publicar con rigor o es un tema que no debe publicarse."},
                "motivo_no_apto": {"type": "string"},
                "antetitulo": {"type": "string", "description": "2-4 palabras en mayúsculas sobre el tema (p. ej. 'ÚLTIMA HORA', 'EURÍBOR', 'LALIGA'). Máx. 28 caracteres."},
                "titular": {"type": "string", "description": "Titular de portada. Claro, informativo, con gancho pero sin sensacionalismo. 45-95 caracteres."},
                "entradilla": {"type": "string", "description": "Una frase que complementa el titular con el dato clave. Máx. 150 caracteres."},
                "diapositivas": {
                    "type": "array",
                    "minItems": aj.diapositivas_min,
                    "maxItems": aj.diapositivas_max,
                    "description": "Tarjetas que se pasan con el dedo, en orden narrativo: qué ha pasado, claves/datos, contexto, qué viene ahora / cómo te afecta.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "titulo": {"type": "string", "description": "Máx. 55 caracteres."},
                            "texto": {"type": "string", "description": "Máx. 300 caracteres. Frases cortas."},
                        },
                        "required": ["titulo", "texto"],
                    },
                },
                "dato_clave": {
                    "type": "object",
                    "description": "Cifra destacada SOLO si aparece literalmente en las fuentes. Si no hay, deja cifra vacía.",
                    "properties": {
                        "cifra": {"type": "string", "description": "Máx. 10 caracteres, p. ej. '3,2%', '1.200 €', '45.000'."},
                        "explicacion": {"type": "string", "description": "Máx. 110 caracteres."},
                    },
                    "required": ["cifra", "explicacion"],
                },
                "en_una_frase": {"type": "string", "description": "Resumen de toda la noticia en una frase para la tarjeta final. Máx. 160 caracteres."},
                "resumen_post": {"type": "string", "description": "Texto explicativo para el pie del post (caption): 3-5 párrafos breves separados por línea en blanco, 600-1200 caracteres. Incluye de forma natural las palabras clave que la gente buscaría. Puede llevar 2-4 emojis como viñetas."},
                "por_que_importa": {"type": "string", "description": "Una o dos frases: cómo afecta al lector en España. Máx. 220 caracteres."},
                "pregunta": {"type": "string", "description": "Pregunta abierta para fomentar comentarios. Máx. 120 caracteres."},
                "hashtags": {"type": "array", "minItems": n_tags, "maxItems": n_tags, "items": {"type": "string"},
                             "description": f"Exactamente {n_tags} hashtags SIN '#', en minúsculas, sin tildes ni espacios."},
                "medios": {"type": "array", "items": {"type": "string"}, "description": "Nombres de los medios usados como fuente."},
            },
            "required": ["apto", "antetitulo", "titular", "entradilla", "diapositivas", "dato_clave",
                         "en_una_frase", "resumen_post", "por_que_importa", "pregunta", "hashtags", "medios"],
        },
    }


REGLAS = """Eres el equipo de redacción de {nombre}, un periódico español que publica solo en Instagram.

REGLAS PERIODÍSTICAS (obligatorias):
1. Usa ÚNICAMENTE hechos que aparezcan en el material proporcionado. No inventes cifras, fechas, citas, nombres ni causas. Si dudas, no lo pongas.
2. Redacta con tus propias palabras; nunca copies frases del original. Las citas textuales, solo si son breves y atribuidas.
3. Atribuye siempre: "según…", "informa…", "denuncia…". Para delitos no juzgados usa "presunto/a". Nunca afirmes culpabilidad sin sentencia.
4. Tono neutral e informativo, especialmente en política: sin adjetivos valorativos y recogiendo las posiciones de las partes cuando las haya.
5. No identifiques a menores ni a víctimas. En suicidios, sin métodos ni detalles. Nada de bulos, rumores ni fichajes no confirmados.
6. Marca apto=false si: el material es insuficiente o contradictorio, es contenido patrocinado/publicitario, es una opinión y no una noticia, o publicar podría causar daño.
7. Español de España, frases cortas, lenguaje claro para cualquier persona. Las tarjetas sin emojis.
8. Hashtags: mezcla 1 amplio de la sección y el resto específicos de la historia (personas, lugares, entidades, palabras clave que la gente busca). Sin tildes.
Fecha y hora actual en España: {ahora}."""


@dataclass
class Post:
    seccion: Seccion
    antetitulo: str
    titular: str
    entradilla: str
    diapositivas: list[dict]
    dato_cifra: str
    dato_explicacion: str
    en_una_frase: str
    resumen_post: str
    por_que_importa: str
    pregunta: str
    hashtags: list[str]
    medios: list[str]
    noticia: Noticia | None = None
    caption: str = ""
    extra: dict = field(default_factory=dict)


def _cliente() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=secreto("ANTHROPIC_API_KEY"), max_retries=4)


def _llamar(cli, modelo: str, sistema: str, usuario: str, herramienta: dict, max_tokens: int) -> dict:
    r = cli.messages.create(
        model=modelo,
        max_tokens=max_tokens,
        system=sistema,
        tools=[herramienta],
        tool_choice={"type": "tool", "name": herramienta["name"]},
        messages=[{"role": "user", "content": usuario}],
    )
    for bloque in r.content:
        if bloque.type == "tool_use":
            return bloque.input
    raise RuntimeError("La IA no devolvió el formato esperado")


def elegir(aj: Ajustes, seccion: Seccion, candidatas: list[Noticia], recientes: list[str], ahora: datetime,
           descartadas: set[int] | None = None) -> tuple[Noticia, list[Noticia]] | None:
    descartadas = descartadas or set()
    lista = "\n".join(c.ficha(i) for i, c in enumerate(candidatas) if i not in descartadas)
    if not lista:
        return None
    sistema = REGLAS.format(nombre=aj.nombre, ahora=f"{ahora:%A %d/%m/%Y %H:%M}")
    usuario = f"""Sección: {seccion.nombre}
Enfoque de la sección: {seccion.enfoque}

Ya hemos publicado hoy estas historias (NO repitas ninguna ni una variante de ellas):
{chr(10).join('- ' + t for t in recientes[:60]) or '- (ninguna)'}

Noticias candidatas:
{lista}

Elige la MEJOR noticia para publicar ahora en esta sección: la más relevante e interesante para el público español, reciente, cubierta por varios medios si es posible, que encaje en la sección y que no sea publicidad ni opinión. Devuelve -1 si ninguna encaja."""
    cli = _cliente()
    res = _llamar(cli, aj.modelo_seleccion, sistema, usuario, HERRAMIENTA_ELEGIR, 600)
    i = int(res.get("indice", -1))
    if i < 0 or i >= len(candidatas) or i in descartadas:
        log.info("La IA no encontró noticia adecuada: %s", res.get("motivo"))
        return None
    rel = [candidatas[j] for j in res.get("relacionadas", []) if 0 <= j < len(candidatas) and j != i]
    principal = candidatas[i]
    rel = (principal.relacionadas + rel)[:4]
    log.info("Elegida [%d] %s — %s", i, principal.titulo, res.get("motivo"))
    return principal, rel


def redactar(aj: Ajustes, seccion: Seccion, principal: Noticia, relacionadas: list[Noticia], ahora: datetime) -> Post | None:
    material = [f"NOTICIA PRINCIPAL ({principal.fuente}): {principal.titulo}\n{principal.resumen}"]
    cuerpo = texto_completo(principal.url)
    if cuerpo:
        material.append(f"TEXTO DEL ARTÍCULO PRINCIPAL (solo como referencia, no copiar):\n{cuerpo}")
    for r in relacionadas:
        material.append(f"OTRO MEDIO ({r.fuente}): {r.titulo}\n{r.resumen}")
        if len("\n".join(material)) < 9000:
            extra = texto_completo(r.url, 3000)
            if extra:
                material.append(f"TEXTO ({r.fuente}, referencia):\n{extra}")

    sistema = REGLAS.format(nombre=aj.nombre, ahora=f"{ahora:%A %d/%m/%Y %H:%M}")
    usuario = f"""Sección: {seccion.nombre}
Hashtags habituales de la sección (inspiración): {', '.join(seccion.hashtags_base)}

MATERIAL:
{chr(10).join(material)}

Crea el post-carrusel de Instagram sobre esta noticia: portada con titular, {aj.diapositivas_min}-{aj.diapositivas_max} tarjetas que se pasan con el dedo, y el texto explicativo del pie."""
    cli = _cliente()
    d = _llamar(cli, aj.modelo_redaccion, sistema, usuario, _herramienta_carrusel(aj), 3500)
    if not d.get("apto", False):
        log.info("Noticia descartada por la IA: %s", d.get("motivo_no_apto"))
        return None

    dato = d.get("dato_clave") or {}
    post = Post(
        seccion=seccion,
        antetitulo=_corta(d["antetitulo"].upper(), 28),
        titular=_corta(d["titular"], 110),
        entradilla=_corta(d["entradilla"], 170),
        diapositivas=[{"titulo": _corta(x["titulo"], 60), "texto": _corta(x["texto"], 330)}
                      for x in d["diapositivas"]][: aj.diapositivas_max],
        dato_cifra=_corta(dato.get("cifra", ""), 12),
        dato_explicacion=_corta(dato.get("explicacion", ""), 120),
        en_una_frase=_corta(d["en_una_frase"], 180),
        resumen_post=d["resumen_post"].strip(),
        por_que_importa=d["por_que_importa"].strip(),
        pregunta=d["pregunta"].strip(),
        hashtags=[_limpia_tag(h) for h in d["hashtags"] if _limpia_tag(h)],
        medios=[m for m in d.get("medios", []) if m] or [principal.fuente],
        noticia=principal,
    )
    post.caption = componer_caption(aj, post)
    return post


def _corta(t: str, n: int) -> str:
    t = re.sub(r"\s+", " ", (t or "").strip())
    if len(t) <= n:
        return t
    return t[: n - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _limpia_tag(h: str) -> str:
    import unicodedata

    h = unicodedata.normalize("NFKD", h.lower().lstrip("#"))
    h = "".join(c for c in h if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9_ñ]", "", h)


def componer_caption(aj: Ajustes, p: Post) -> str:
    tags = [aj.hashtag_marca] + [h for h in p.hashtags if h != aj.hashtag_marca]
    tags = list(dict.fromkeys(tags))[: aj.max_hashtags]
    partes = [
        f"{p.titular}",
        p.resumen_post,
        f"📌 Por qué importa: {p.por_que_importa}",
        f"💬 {p.pregunta}",
        f"Fuentes: {', '.join(dict.fromkeys(p.medios))}.",
        f"Síguenos en {aj.usuario} para estar al día · {p.seccion.nombre}",
        " ".join("#" + t for t in tags),
    ]
    caption = "\n\n".join(x for x in partes if x)
    if len(caption) > 2150:  # límite de Instagram: 2.200 caracteres
        exceso = len(caption) - 2150
        nuevo = max(200, len(p.resumen_post) - exceso - 5)
        p.resumen_post = p.resumen_post[:nuevo].rsplit(" ", 1)[0].rstrip(",;:") + "…"
        return componer_caption(aj, p)
    return caption
