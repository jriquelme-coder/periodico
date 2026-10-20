"""Contenido de EJEMPLO para ver el diseño sin claves de API (no son noticias reales)."""
from __future__ import annotations

from .config import Ajustes
from .redactor import Post, componer_caption

EJEMPLOS = {
    "vivienda": dict(
        antetitulo="ALQUILER",
        titular="El alquiler vuelve a subir en las grandes ciudades y marca un nuevo máximo",
        entradilla="[EJEMPLO] Madrid y Barcelona encabezan la subida, según el último informe del sector.",
        diapositivas=[
            {"titulo": "Qué ha pasado", "texto": "El precio medio del alquiler ha subido de nuevo este trimestre. Es la cifra más alta desde que hay registros, según el informe publicado hoy."},
            {"titulo": "Dónde sube más", "texto": "Las mayores subidas se concentran en las capitales y en las zonas turísticas de la costa. En algunas ciudades medianas el precio se ha estabilizado."},
            {"titulo": "Por qué ocurre", "texto": "Los expertos apuntan a la falta de oferta: hay muchas más personas buscando piso que viviendas disponibles para alquilar."},
            {"titulo": "Qué viene ahora", "texto": "El Gobierno estudia nuevas medidas. Mientras tanto, se recomienda comparar precios por zona y revisar los límites de actualización del contrato."},
        ],
        dato_cifra="+8,4%",
        dato_explicacion="Subida interanual del precio medio del alquiler (cifra de ejemplo).",
        en_una_frase="Alquilar es más caro que nunca y la falta de pisos disponibles explica gran parte de la subida.",
        resumen_post="🏠 [Contenido de ejemplo] El precio del alquiler vuelve a marcar máximos en España.\n\n📊 Las grandes ciudades lideran la subida, mientras que algunas ciudades medianas se estabilizan.\n\n🔎 La causa principal es la falta de oferta frente a una demanda que no deja de crecer.",
        por_que_importa="Si vives de alquiler o buscas piso, la renovación de tu contrato puede encarecerse.",
        pregunta="¿Cuánto ha subido tu alquiler este año?",
        hashtags=["vivienda", "alquiler", "precioalquiler", "madrid"],
        medios=["Fuente de ejemplo"],
    ),
    "deportes": dict(
        antetitulo="LALIGA",
        titular="Remontada en el descuento para seguir líderes una jornada más",
        entradilla="[EJEMPLO] Dos goles en los últimos diez minutos cambian el partido.",
        diapositivas=[
            {"titulo": "El partido", "texto": "El equipo local iba perdiendo al descanso y parecía condenado. Los cambios de la segunda parte le dieron la vuelta al encuentro."},
            {"titulo": "La clave", "texto": "La presión alta en los últimos minutos provocó dos errores del rival que acabaron en gol."},
            {"titulo": "La clasificación", "texto": "Con esta victoria mantiene el liderato con tres puntos de ventaja sobre el segundo."},
        ],
        dato_cifra="", dato_explicacion="",
        en_una_frase="Una remontada en el descuento mantiene al líder en lo más alto.",
        resumen_post="⚽ [Contenido de ejemplo] Remontada de infarto en LaLiga.",
        por_que_importa="La lucha por el título sigue abierta.",
        pregunta="¿Quién crees que ganará la liga?",
        hashtags=["deportes", "laliga", "futbol", "futbolespañol"],
        medios=["Fuente de ejemplo"],
    ),
    "tecnologia": dict(
        antetitulo="INTELIGENCIA ARTIFICIAL",
        titular="Europa aprueba nuevas normas para la IA: qué cambia para ti",
        entradilla="[EJEMPLO] Las apps deberán avisar cuando un contenido esté generado por IA.",
        diapositivas=[
            {"titulo": "Qué se ha aprobado", "texto": "Nuevas obligaciones de transparencia para las empresas que usan inteligencia artificial en sus productos."},
            {"titulo": "Qué cambia para ti", "texto": "Verás etiquetas en imágenes y vídeos creados con IA y podrás saber cuándo hablas con un asistente automático."},
            {"titulo": "Cuándo", "texto": "Las empresas tendrán un periodo de adaptación antes de que las sanciones empiecen a aplicarse."},
        ],
        dato_cifra="2 años", dato_explicacion="Plazo de adaptación para las empresas (dato de ejemplo).",
        en_una_frase="La IA tendrá que identificarse: más transparencia para los usuarios europeos.",
        resumen_post="🤖 [Contenido de ejemplo] Nuevas normas europeas para la IA.",
        por_que_importa="Afecta a las apps que usas a diario.",
        pregunta="¿Te fías de los contenidos hechos con IA?",
        hashtags=["tecnologia", "inteligenciaartificial", "ia", "europa"],
        medios=["Fuente de ejemplo"],
    ),
}


def post_demo(aj: Ajustes, seccion_id: str) -> Post:
    datos = EJEMPLOS.get(seccion_id, EJEMPLOS["vivienda"]).copy()
    s = aj.seccion(seccion_id)
    p = Post(seccion=s, **datos)
    p.caption = componer_caption(aj, p)
    return p
