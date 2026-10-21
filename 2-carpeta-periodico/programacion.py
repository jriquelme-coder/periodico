"""Reparto de secciones en los huecos (slots) del día.

Con 96 posts/día hay un hueco cada 15 minutos. El reparto usa un "round robin
ponderado suave": cada sección aparece en proporción a su peso y nunca dos
veces seguidas. Además, el orden se desplaza cada día para que todas las
secciones pasen por las horas de más audiencia a lo largo de la semana.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .config import Ajustes, Seccion


def plan_del_dia(aj: Ajustes, dia_del_anio: int = 0) -> list[Seccion]:
    secciones = list(aj.secciones)
    if not secciones:
        raise ValueError("No hay secciones configuradas")
    desplazamiento = dia_del_anio % len(secciones)
    secciones = secciones[desplazamiento:] + secciones[:desplazamiento]

    total = sum(s.peso for s in secciones)
    actual = {s.id: 0.0 for s in secciones}
    plan: list[Seccion] = []
    for _ in range(aj.posts_por_dia):
        for s in secciones:
            actual[s.id] += s.peso
        elegido = max(secciones, key=lambda s: actual[s.id])
        actual[elegido.id] -= total
        plan.append(elegido)
    return plan


def slot_actual(aj: Ajustes, ahora: datetime | None = None) -> tuple[str, int, datetime]:
    """Devuelve (id_slot, índice, hora_local). id_slot = 'AAAA-MM-DD#NN'."""
    tz = ZoneInfo(aj.zona_horaria)
    ahora = (ahora or datetime.now(tz)).astimezone(tz)
    minutos = ahora.hour * 60 + ahora.minute
    indice = minutos // aj.minutos_intervalo
    indice = min(indice, aj.posts_por_dia - 1)
    return f"{ahora:%Y-%m-%d}#{indice:03d}", indice, ahora


def seccion_para(aj: Ajustes, ahora: datetime | None = None) -> tuple[str, Seccion, datetime]:
    sid, indice, local = slot_actual(aj, ahora)
    plan = plan_del_dia(aj, local.timetuple().tm_yday)
    return sid, plan[indice], local


def tabla_del_dia(aj: Ajustes, fecha: datetime | None = None) -> list[tuple[str, str]]:
    tz = ZoneInfo(aj.zona_horaria)
    fecha = (fecha or datetime.now(tz)).astimezone(tz)
    plan = plan_del_dia(aj, fecha.timetuple().tm_yday)
    filas = []
    for i, s in enumerate(plan):
        m = i * aj.minutos_intervalo
        extra = " [REEL]" if formato(aj, i) == "reel" else (" [+story]" if lleva_story(aj, i) else "")
        filas.append((f"{m // 60:02d}:{m % 60:02d}", s.nombre + extra))
    return filas


def formato(aj: Ajustes, indice: int) -> str:
    """'reel' si el hueco coincide con una de las horas de reels; si no, 'carrusel'."""
    for h in aj.horas_reels:
        hh, mm = (int(x) for x in str(h).split(":"))
        if (hh * 60 + mm) // aj.minutos_intervalo == indice:
            return "reel"
    return "carrusel"


def lleva_story(aj: Ajustes, indice: int) -> bool:
    if aj.stories_por_dia <= 0:
        return False
    paso = max(1, aj.posts_por_dia // aj.stories_por_dia)
    # desplazado medio paso para no coincidir con medianoche
    return indice % paso == paso // 2 and formato(aj, indice) == "carrusel"
