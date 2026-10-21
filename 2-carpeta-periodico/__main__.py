"""Punto de entrada.  Uso:  python -m periodico <orden>

  publicar        Publica el post que toca ahora (lo lanza GitHub Actions cada 15 min)
     --seccion X  fuerza una sección concreta
     --forzar     publica aunque este hueco ya esté hecho
     --prueba     genera imágenes y texto en ./salida sin publicar en Instagram
  demo            Genera tarjetas de ejemplo en ./ejemplos (no necesita claves)
  plan            Muestra el reparto de secciones de hoy
  fuentes         Comprueba qué fuentes RSS responden
  renovar-token   Renueva el token de Instagram (lo lanza GitHub Actions cada semana)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config, diseno, fuentes, programacion, redactor
from .almacen import Almacen

log = logging.getLogger("periodico")


def _resumen_github(texto: str) -> None:
    ruta = os.getenv("GITHUB_STEP_SUMMARY")
    if ruta:
        with open(ruta, "a", encoding="utf-8") as fh:
            fh.write(texto + "\n")


def crear_post(aj, seccion, almacen: Almacen, ahora):
    usados = almacen.ids_usados()
    recientes = almacen.titulos_recientes()
    candidatas = fuentes.recoger(seccion, aj.horas_maximas_noticia, usados, recientes)
    if not candidatas:
        log.warning("Sin noticias candidatas para %s", seccion.id)
        return None
    descartadas: set[int] = set()
    for _ in range(3):
        elegida = redactor.elegir(aj, seccion, candidatas, recientes, ahora, descartadas)
        if not elegida:
            return None
        principal, relacionadas = elegida
        try:
            post = redactor.redactar(aj, seccion, principal, relacionadas, ahora)
        except Exception as e:  # noqa: BLE001
            log.warning("Fallo al redactar «%s»: %s", principal.titulo, e)
            post = None
        if post:
            return post
        descartadas.add(candidatas.index(principal))
    return None


def orden_publicar(args) -> int:
    aj = config.cargar()
    tz = ZoneInfo(aj.zona_horaria)
    ahora = datetime.now(tz)
    slot, seccion, _ = programacion.seccion_para(aj, ahora)
    if args.seccion:
        seccion = aj.seccion(args.seccion)
    prueba = args.prueba or not os.getenv("IG_ACCESS_TOKEN")
    if prueba:
        log.info("MODO PRUEBA: no se publicará en Instagram")

    almacen = Almacen()
    almacen.cargar()
    if almacen.slot_hecho(slot) and not args.forzar and not prueba:
        log.info("El hueco %s ya está publicado. Nada que hacer.", slot)
        return 0

    ig = None
    if not prueba:
        from .instagram import Instagram

        ig = Instagram()
        uso, total = ig.cuota()
        log.info("Cuota de Instagram: %d/%d en las últimas 24 h", uso, total)
        if uso >= total - aj.margen_cuota:
            log.warning("Cuota diaria casi agotada; se salta este hueco.")
            _resumen_github(f"⏸️ {slot}: cuota de Instagram agotada ({uso}/{total})")
            return 0

    log.info("Hueco %s → sección %s", slot, seccion.nombre)
    post = crear_post(aj, seccion, almacen, ahora)
    if not post and seccion.id != "actualidad":
        log.info("Sin noticia válida en %s; se usa Actualidad como reserva", seccion.id)
        post = crear_post(aj, aj.seccion("actualidad"), almacen, ahora)
    if not post:
        log.error("No se encontró ninguna noticia publicable")
        _resumen_github(f"⚠️ {slot}: sin noticia publicable")
        return 0

    carpeta = Path("salida") / slot.replace("#", "-")
    rutas = diseno.generar(aj, post, ahora, carpeta)
    (carpeta / "caption.txt").write_text(post.caption, encoding="utf-8")
    log.info("Generadas %d tarjetas en %s", len(rutas), carpeta)

    entrada = {
        "slot": slot,
        "fecha": datetime.now(timezone.utc).isoformat(),
        "seccion": post.seccion.id,
        "titular": post.titular,
        "noticia_id": post.noticia.id if post.noticia else "",
        "url_fuente": post.noticia.url if post.noticia else "",
        "medios": post.medios,
    }

    from . import video
    from .instagram import publicar_reel, publicar_story

    tipo = programacion.formato(aj, int(slot.split("#")[1]))
    if args.formato in ("reel", "carrusel"):
        tipo = args.formato

    if prueba:
        if tipo == "reel":
            video.generar_reel(aj, post, rutas, carpeta / "reel")
        video.story(aj, post, rutas[0], carpeta)
        print("\n" + "─" * 60 + f"\n{post.caption}\n" + "─" * 60)
        _resumen_github(f"### 🧪 Prueba {slot} · {post.seccion.nombre}\n**{post.titular}**\n\n```\n{post.caption}\n```")
        return 0

    try:
        if tipo == "reel":
            mp4 = video.generar_reel(aj, post, rutas, carpeta / "reel")
            urls = almacen.subir_imagenes(slot, [mp4, rutas[0]])
            media_id, enlace = publicar_reel(ig, urls[0], post.caption)
        else:
            urls = almacen.subir_imagenes(slot, rutas)
            media_id, enlace = ig.publicar_carrusel(urls, post.caption)
    except Exception as e:
        # Se apunta la noticia como fallida para no reintentar la misma en bucle
        almacen.registrar_fallo(entrada.get("noticia_id"), str(e))
        almacen.guardar(conservar_media=False)
        _resumen_github(f"### ❌ {slot} · {post.seccion.nombre}\n**{post.titular}**\n\n```\n{e}\n```")
        raise
    entrada.update(media_id=media_id, enlace=enlace, formato=tipo)
    almacen.registrar(entrada)
    almacen.guardar(conservar_media=False)
    log.info("✅ Publicado (%s) %s %s", tipo, media_id, enlace)
    _resumen_github(f"### ✅ {slot} · {post.seccion.nombre} · {tipo}\n**{post.titular}**\n\n{enlace}")

    if tipo == "carrusel" and programacion.lleva_story(aj, int(slot.split("#")[1])):
        try:
            uso, total = ig.cuota()
            if uso < total - aj.margen_cuota:
                img = video.story(aj, post, rutas[0], carpeta)
                url = almacen.subir_imagenes(slot + "-story", [img])[0]
                publicar_story(ig, url)
                almacen.guardar(conservar_media=False)
                log.info("✅ Story publicada")
        except Exception as e:  # noqa: BLE001  (la story nunca hace fallar el post)
            log.warning("No se pudo publicar la story: %s", e)
    return 0


def orden_demo(args) -> int:
    from . import demo

    aj = config.cargar()
    ahora = datetime.now(ZoneInfo(aj.zona_horaria))
    for sid in demo.EJEMPLOS:
        p = demo.post_demo(aj, sid)
        rutas = diseno.generar(aj, p, ahora, Path("ejemplos") / sid)
        (Path("ejemplos") / sid / "caption.txt").write_text(p.caption, encoding="utf-8")
        print(f"{sid}: {len(rutas)} tarjetas → ejemplos/{sid}/")
    return 0


def orden_plan(args) -> int:
    aj = config.cargar()
    filas = programacion.tabla_del_dia(aj)
    for hora, nombre in filas:
        print(hora, nombre)
    cuenta: dict[str, int] = {}
    for _, n in filas:
        cuenta[n] = cuenta.get(n, 0) + 1
    print("\nPosts por sección:", json.dumps(cuenta, ensure_ascii=False, indent=1))
    return 0


def orden_fuentes(args) -> int:
    aj = config.cargar()
    filas = fuentes.comprobar(aj.secciones)
    malas = 0
    lineas = ["| Sección | Fuente | Noticias |", "|---|---|---|"]
    for sid, url, n in filas:
        marca = "✅" if n else "❌"
        malas += 0 if n else 1
        lineas.append(f"| {sid} | {url[:90]} | {marca} {n} |")
        print(f"{marca} {sid:13s} {n:3d}  {url}")
    _resumen_github("\n".join(lineas))
    print(f"\n{len(filas) - malas}/{len(filas)} fuentes funcionan")
    return 0


def orden_renovar_token(args) -> int:
    from .instagram import renovar_token_instagram

    if (os.getenv("IG_GRAPH_HOST") or "graph.instagram.com") != "graph.instagram.com":
        print("Token de Facebook Login/usuario de sistema: no necesita renovación.")
        return 0
    nuevo, segundos = renovar_token_instagram(config.secreto("IG_ACCESS_TOKEN"))
    print(f"::add-mask::{nuevo}")
    if os.getenv("GH_TOKEN"):
        subprocess.run(["gh", "secret", "set", "IG_ACCESS_TOKEN", "--body", nuevo,
                        "--repo", os.environ["GITHUB_REPOSITORY"]], check=True)
        print(f"Token renovado y guardado. Caduca en {segundos // 86400} días.")
    else:
        print("Token renovado, pero falta el secreto GH_PAT para guardarlo automáticamente.")
        return 1
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    ap = argparse.ArgumentParser(prog="periodico", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="orden", required=True)
    p = sub.add_parser("publicar")
    p.add_argument("--seccion")
    p.add_argument("--forzar", action="store_true")
    p.add_argument("--prueba", action="store_true")
    p.add_argument("--formato", choices=["auto", "carrusel", "reel"], default="auto")
    sub.add_parser("demo")
    sub.add_parser("plan")
    sub.add_parser("fuentes")
    sub.add_parser("renovar-token")
    args = ap.parse_args()
    return {
        "publicar": orden_publicar, "demo": orden_demo, "plan": orden_plan,
        "fuentes": orden_fuentes, "renovar-token": orden_renovar_token,
    }[args.orden](args)


if __name__ == "__main__":
    sys.exit(main())
