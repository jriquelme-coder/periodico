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


def _pausar_por_limite(almacen: Almacen, slot: str, e: Exception) -> int:
    """Instagram limita las llamadas por hora: se pausa 60 min sin dar error (y sin correos)."""
    from datetime import timedelta

    hasta = (datetime.now(timezone.utc) + timedelta(minutes=60)).isoformat()
    almacen.estado["pausa_hasta"] = hasta
    almacen.guardar(conservar_media=False)
    log.warning("%s → pausa automática de 60 minutos", e)
    _resumen_github(f"⏸️ {slot}: Instagram ha limitado las llamadas a la API. Pausa automática de 60 min.")
    return 0


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
    """Publica la noticia del hueco actual en Instagram y en Threads.

    Las dos redes son independientes: si Instagram está en pausa por su límite
    de llamadas o falla, la noticia se publica igualmente en Threads.
    """
    from . import threads, video
    try:  # Telegram es opcional: si falta telegram.py, el resto sigue funcionando
        from . import telegram
    except ImportError:
        telegram = None
    from .instagram import Instagram, LimiteInstagram, publicar_reel, publicar_story

    aj = config.cargar()
    tz = ZoneInfo(aj.zona_horaria)
    ahora = datetime.now(tz)
    slot, seccion, _ = programacion.seccion_para(aj, ahora)
    if args.seccion:
        seccion = aj.seccion(args.seccion)
    prueba = args.prueba or not os.getenv("IG_ACCESS_TOKEN")
    if prueba:
        log.info("MODO PRUEBA: no se publicará en ninguna red")

    almacen = Almacen()
    almacen.cargar()
    if almacen.slot_hecho(slot) and not args.forzar and not prueba:
        log.info("El hueco %s ya está publicado. Nada que hacer.", slot)
        return 0

    # ── ¿Está Instagram disponible en este hueco? ───────────────────────
    ig = None
    motivo_sin_ig = ""
    if not prueba:
        pausa = almacen.estado.get("pausa_hasta", "")
        if pausa and datetime.now(timezone.utc).isoformat() < pausa and not args.forzar:
            motivo_sin_ig = f"Instagram en pausa por su límite hasta {pausa}"
        else:
            try:
                ig = Instagram()
                uso, total = ig.cuota()
                log.info("Cuota de Instagram: %d/%d en las últimas 24 h", uso, total)
                if uso >= total - aj.margen_cuota:
                    ig, motivo_sin_ig = None, f"cuota diaria de Instagram agotada ({uso}/{total})"
            except LimiteInstagram as e:
                _pausar_por_limite(almacen, slot, e)
                ig, motivo_sin_ig = None, "Instagram ha alcanzado su límite de llamadas (pausa de 60 min)"
            except Exception as e:  # noqa: BLE001
                ig, motivo_sin_ig = None, f"Instagram no disponible: {e}"
        if motivo_sin_ig:
            log.info("%s.", motivo_sin_ig)
        if not ig and not threads.activo() and not (telegram and telegram.activo()):
            log.info("Ninguna red disponible: se salta este hueco.")
            return 0

    # ── Noticia y tarjetas ──────────────────────────────────────────────
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

    entrada = {
        "slot": slot,
        "fecha": datetime.now(timezone.utc).isoformat(),
        "seccion": post.seccion.id,
        "titular": post.titular,
        "noticia_id": post.noticia.id if post.noticia else "",
        "url_fuente": post.noticia.url if post.noticia else "",
        "medios": post.medios,
        "formato": tipo,
        "entradilla": post.entradilla,
        "hora": f"{ahora:%H:%M}",
    }
    resumen = [f"### {slot} · {post.seccion.nombre} · {tipo}", f"**{post.titular}**", ""]

    # ── Instagram ───────────────────────────────────────────────────────
    enlace = ""
    urls_imagenes: list[str] = []
    error_ig = None
    if ig:
        try:
            if tipo == "reel":
                mp4 = video.generar_reel(aj, post, rutas, carpeta / "reel")
                urls = almacen.subir_imagenes(slot, [mp4, rutas[0]])
                media_id, enlace = publicar_reel(ig, urls[0], post.caption)
            else:
                urls_imagenes = almacen.subir_imagenes(slot, rutas)
                media_id, enlace = ig.publicar_carrusel(urls_imagenes, post.caption)
            entrada.update(media_id=media_id, enlace=enlace)
            log.info("✅ Publicado en Instagram (%s) %s %s", tipo, media_id, enlace)
            resumen.append(f"✅ Instagram: {enlace}")
        except LimiteInstagram as e:
            _pausar_por_limite(almacen, slot, e)
            resumen.append("⏸️ Instagram: límite de llamadas, pausa de 60 min")
        except Exception as e:  # noqa: BLE001
            error_ig = e
            log.error("Fallo al publicar en Instagram: %s", e)
            resumen.append(f"❌ Instagram: `{e}`")
    else:
        resumen.append(f"⏸️ Instagram: {motivo_sin_ig}")

    # ── Threads (independiente de Instagram) ───────────────────────────
    if threads.activo():
        try:
            if not urls_imagenes:
                urls_imagenes = almacen.subir_imagenes(slot + "-threads", rutas)
            entrada["threads_id"] = threads.publicar(aj, post, urls_imagenes, enlace,
                                                     almacen.urls_cdn(urls_imagenes))
            resumen.append("✅ Threads: publicado")
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo publicar en Threads: %s", e)
            resumen.append(f"❌ Threads: `{e}`")

    # ── Telegram (independiente) ──────────────────────────────────────
    if telegram and telegram.activo():
        try:
            mp4 = carpeta / "reel" / "reel.mp4"
            entrada["telegram_id"] = telegram.publicar(aj, post, rutas, enlace, mp4 if tipo == "reel" else None)
            resumen.append("✅ Telegram: publicado")
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo publicar en Telegram: %s", e)
            resumen.append(f"❌ Telegram: `{e}`")

    publicado = bool(entrada.get("media_id") or entrada.get("threads_id") or entrada.get("telegram_id"))
    if publicado:
        almacen.registrar(entrada)
    elif error_ig:
        # Se apunta la noticia como fallida para no reintentar la misma en bucle
        almacen.registrar_fallo(entrada.get("noticia_id"), str(error_ig))
    almacen.guardar(conservar_media=False)

    # ── Página web «Las noticias de hoy» ───────────────────────────────
    if publicado:
        try:
            from . import web

            url_web = web.actualizar(aj, almacen.estado, rutas[0], slot)
            resumen.append(f"🌐 Página del día: {url_web}")
        except Exception as e:  # noqa: BLE001  (la web nunca hace fallar la publicación)
            log.warning("No se pudo actualizar la página del día: %s", e)
    _resumen_github("\n".join(resumen))

    # ── Story (solo si Instagram ha publicado un carrusel) ─────────────
    if ig and entrada.get("media_id") and tipo == "carrusel" and programacion.lleva_story(aj, int(slot.split("#")[1])):
        try:
            img = video.story(aj, post, rutas[0], carpeta)
            url = almacen.subir_imagenes(slot + "-story", [img])[0]
            publicar_story(ig, url)
            almacen.guardar(conservar_media=False)
            log.info("✅ Story publicada")
        except Exception as e:  # noqa: BLE001  (la story nunca hace fallar el post)
            log.warning("No se pudo publicar la story: %s", e)

    if error_ig and not publicado:
        raise error_ig
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


def _guardar_secreto(nombre: str, valor: str) -> bool:
    print(f"::add-mask::{valor}")
    if not os.getenv("GH_TOKEN"):
        print(f"Falta el secreto GH_PAT para guardar {nombre} automáticamente.")
        return False
    subprocess.run(["gh", "secret", "set", nombre, "--body", valor,
                    "--repo", os.environ["GITHUB_REPOSITORY"]], check=True)
    return True


def orden_renovar_token(args) -> int:
    from .instagram import renovar_token_instagram

    ok = True
    if (os.getenv("IG_GRAPH_HOST") or "graph.instagram.com") != "graph.instagram.com":
        print("Instagram: token de Facebook Login/usuario de sistema, no necesita renovación.")
    else:
        nuevo, segundos = renovar_token_instagram(config.secreto("IG_ACCESS_TOKEN"))
        ok &= _guardar_secreto("IG_ACCESS_TOKEN", nuevo)
        print(f"Instagram: token renovado. Caduca en {segundos // 86400} días.")

    if os.getenv("THREADS_ACCESS_TOKEN"):
        from .threads import renovar_token

        try:
            nuevo, segundos = renovar_token(os.environ["THREADS_ACCESS_TOKEN"])
            ok &= _guardar_secreto("THREADS_ACCESS_TOKEN", nuevo)
            print(f"Threads: token renovado. Caduca en {segundos // 86400} días.")
        except Exception as e:  # noqa: BLE001
            # Un token recién creado (menos de 24 h) aún no se puede renovar: no es grave.
            print(f"Threads: no se pudo renovar todavía ({e}).")
    return 0 if ok else 1


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
