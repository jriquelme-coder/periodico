"""Página web «Las noticias de hoy», agrupadas por sección.

Cada vez que se publica una noticia se regenera la página con todas las de HOY
(hora de España). Al cambiar de día empieza vacía: lo del día anterior se borra
solo. Se aloja gratis en GitHub Pages (rama `web` del repositorio).
"""
from __future__ import annotations

import html
import logging
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

from .config import Ajustes

log = logging.getLogger(__name__)
RAMA = "web"
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def _fecha_larga(d: datetime) -> str:
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]} de {d.year}"


def _texto_sobre(hexa: str) -> str:
    h = hexa.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#111111" if lum > 0.55 else "#ffffff"


def _legible(hexa: str) -> str:
    from .diseno import acento_legible, rgb

    r, g, b = acento_legible(rgb(hexa), (255, 255, 255), 4.5)
    return f"#{r:02x}{g:02x}{b:02x}"


def generar_html(aj: Ajustes, entradas: list[dict], ahora: datetime, aviso: str = "") -> str:
    e = html.escape
    usuario = aj.usuario.lstrip("@")
    por_seccion: dict[str, list[dict]] = {}
    for x in entradas:
        por_seccion.setdefault(x.get("seccion", ""), []).append(x)
    secciones = [s for s in aj.secciones if por_seccion.get(s.id)]

    chips = "".join(
        f'<a class="chip" href="#{s.id}" style="--c:{s.color}">{e(s.nombre)}'
        f'<span>{len(por_seccion[s.id])}</span></a>' for s in secciones)

    bloques = []
    for s in secciones:
        tarjetas = []
        for x in sorted(por_seccion[s.id], key=lambda y: y.get("hora", ""), reverse=True):
            mini = (f'<img src="{e(x["miniatura"])}" alt="" loading="lazy">' if x.get("miniatura")
                    else f'<div class="sinimg" style="background:{s.color}"></div>')
            enlace = x.get("enlace") or ""
            boton = (f'<a class="ver" href="{e(enlace)}" target="_blank" rel="noopener">Ver en Instagram →</a>'
                     if enlace else "")
            medios = ", ".join(x.get("medios") or [])
            tarjetas.append(f"""
      <article class="noticia">
        {mini}
        <div class="txt">
          <div class="meta"><time>{e(x.get("hora", ""))}</time>{' · ' + e(medios) if medios else ''}</div>
          <h3>{e(x.get("titular", ""))}</h3>
          {f'<p>{e(x["entradilla"])}</p>' if x.get("entradilla") else ''}
          {boton}
        </div>
      </article>""")
        bloques.append(f"""
    <section id="{s.id}" style="--c:{s.color};--t:{_texto_sobre(s.color)};--v:{_legible(s.color)}">
      <h2><span class="barra"></span>{e(s.nombre)} <small>{len(por_seccion[s.id])}</small></h2>
      {''.join(tarjetas)}
    </section>""")

    vacio = "" if entradas else """
    <div class="vacio">Todavía no hay noticias hoy. Vuelve en un rato.</div>"""

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(aj.nombre.title())} · Noticias de hoy</title>
<meta name="description" content="Todas las noticias de hoy de {e(aj.usuario)}, por sección.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>
:root{{--fondo:#f6f3ee;--tarjeta:#ffffff;--tinta:#141414;--suave:#5f5f5f;--linea:#e4dfd6}}
@media (prefers-color-scheme:dark){{:root{{--fondo:#0f1115;--tarjeta:#181b21;--tinta:#f2f2f2;--suave:#a3a3a3;--linea:#2a2e36}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--fondo);color:var(--tinta);font-family:Inter,system-ui,-apple-system,sans-serif;line-height:1.45}}
header{{background:#0e1014;color:#fff;padding:28px 16px 22px;text-align:center}}
.marca{{font-weight:900;letter-spacing:.12em;font-size:15px}}
.marca::before{{content:"";display:inline-block;width:10px;height:10px;border-radius:50%;background:#ff3b30;margin-right:8px;vertical-align:1px}}
header h1{{font-size:clamp(26px,6vw,40px);font-weight:900;margin:10px 0 4px;letter-spacing:-.02em}}
header p{{margin:0;color:#b9b9b9;font-size:15px}}
.aviso{{background:#ffe9a8;color:#3d3000;text-align:center;font-size:13px;padding:8px 16px}}
nav{{position:sticky;top:0;z-index:5;background:var(--fondo);border-bottom:1px solid var(--linea);padding:10px 16px;
 display:flex;gap:8px;overflow-x:auto;scrollbar-width:none}}
nav::-webkit-scrollbar{{display:none}}
.chip{{flex:none;display:flex;align-items:center;gap:6px;text-decoration:none;color:var(--tinta);font-size:13px;font-weight:700;
 border:1px solid var(--linea);background:var(--tarjeta);border-radius:999px;padding:6px 8px 6px 12px}}
.chip span{{background:var(--c);color:#fff;border-radius:999px;font-size:11px;padding:1px 7px}}
main{{max-width:760px;margin:0 auto;padding:8px 16px 40px}}
section{{scroll-margin-top:64px;margin-top:26px}}
h2{{display:flex;align-items:center;gap:10px;font-size:20px;font-weight:900;margin:0 0 12px}}
h2 small{{font-size:12px;font-weight:700;color:var(--suave)}}
.barra{{width:6px;height:22px;border-radius:3px;background:var(--c)}}
.noticia{{display:flex;gap:14px;background:var(--tarjeta);border:1px solid var(--linea);border-left:4px solid var(--c);
 border-radius:14px;padding:12px;margin-bottom:10px}}
.noticia img,.sinimg{{width:88px;height:110px;object-fit:cover;border-radius:8px;flex:none}}
.txt{{min-width:0}}
.meta{{font-size:12px;color:var(--suave);margin-bottom:2px}}
.meta time{{font-weight:700;color:var(--tinta)}}
h3{{font-size:16px;line-height:1.3;margin:2px 0 6px}}
.txt p{{margin:0 0 8px;font-size:14px;color:var(--suave)}}
.ver{{font-size:13px;font-weight:700;color:var(--v);text-decoration:none}}
@media (prefers-color-scheme:dark){{.ver{{color:var(--c);filter:brightness(1.3)}}}}
.vacio{{text-align:center;color:var(--suave);padding:60px 0}}
footer{{text-align:center;font-size:13px;color:var(--suave);padding:0 16px 40px}}
footer a{{color:inherit;font-weight:700}}
@media (max-width:420px){{.noticia img,.sinimg{{width:72px;height:90px}}h3{{font-size:15px}}}}
</style>
</head>
<body>
{f'<div class="aviso">{e(aviso)}</div>' if aviso else ''}
<header>
  <div class="marca">{e(aj.nombre.upper())}</div>
  <h1>Las noticias de hoy</h1>
  <p>{e(_fecha_larga(ahora).capitalize())} · {len(entradas)} noticias · actualizado a las {ahora:%H:%M}</p>
</header>
{f'<nav>{chips}</nav>' if chips else ''}
<main>{vacio}{''.join(bloques)}
</main>
<footer>Cada día empieza de cero a medianoche · Síguenos en
<a href="https://www.instagram.com/{e(usuario)}/" target="_blank" rel="noopener">{e(aj.usuario)}</a></footer>
</body>
</html>
"""


def entradas_de_hoy(aj: Ajustes, estado: dict, ahora: datetime) -> list[dict]:
    tz = ZoneInfo(aj.zona_horaria)
    hoy = ahora.astimezone(tz).date()
    salida = []
    for p in estado.get("publicaciones", []):
        try:
            f = datetime.fromisoformat(p["fecha"]).astimezone(tz)
        except (KeyError, ValueError):
            continue
        if f.date() == hoy:
            salida.append({**p, "hora": p.get("hora") or f"{f:%H:%M}"})
    return salida


def miniatura(portada: Path, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(portada).convert("RGB")
    im.thumbnail((264, 330))
    im.save(destino, "JPEG", quality=78, optimize=True)


def actualizar(aj: Ajustes, estado: dict, portada: Path | None, slot: str) -> str:
    """Regenera y publica la página en la rama `web`. Devuelve la URL pública."""
    tz = ZoneInfo(aj.zona_horaria)
    ahora = datetime.now(tz)
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    usuario, _, nombre_repo = repo.partition("/")
    url = f"https://{usuario.lower()}.github.io/{nombre_repo}/" if repo else ""

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        en_github = bool(os.getenv("GITHUB_ACTIONS") and repo)
        if en_github:
            from .almacen import _git, _remoto

            _git("init", "-q", cwd=t)
            if _git("fetch", "-q", "--depth", "1", _remoto(), RAMA, cwd=t, check=False).returncode == 0:
                _git("checkout", "-q", "FETCH_HEAD", "--", ".", cwd=t, check=False)
            shutil.rmtree(t / ".git", ignore_errors=True)
        else:
            t = Path("web_local")
            t.mkdir(exist_ok=True)

        # Borrar miniaturas de otros días
        hoy = f"{ahora:%Y-%m-%d}"
        carpeta = t / "img"
        if carpeta.exists():
            for f in carpeta.iterdir():
                if not f.name.startswith(hoy):
                    f.unlink()
        if portada and portada.exists():
            miniatura(portada, carpeta / f"{slot.replace('#', '-')}.jpg")

        entradas = entradas_de_hoy(aj, estado, ahora)
        for x in entradas:
            nombre = f"img/{x['slot'].replace('#', '-')}.jpg"
            if (t / nombre).exists():
                x["miniatura"] = nombre
        (t / "index.html").write_text(generar_html(aj, entradas, ahora), encoding="utf-8")
        (t / ".nojekyll").write_text("")

        if en_github:
            _git("init", "-q", "-b", RAMA, cwd=t)
            _git("config", "user.name", "periodico-bot", cwd=t)
            _git("config", "user.email", "periodico-bot@users.noreply.github.com", cwd=t)
            _git("add", "-A", cwd=t)
            _git("commit", "-q", "-m", f"web {ahora:%Y-%m-%d %H:%M}", cwd=t)
            for _ in range(3):
                if _git("push", "-q", "--force", _remoto(), f"{RAMA}:{RAMA}", cwd=t, check=False).returncode == 0:
                    break
                time.sleep(5)
    log.info("🌐 Página del día actualizada (%d noticias) %s", len(entradas), url)
    return url
