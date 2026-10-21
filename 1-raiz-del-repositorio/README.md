# AL MINUTO — periódico automático para Instagram

Publica **96 carruseles al día (uno cada 15 minutos)** sobre las 16 secciones, repartidas por igual (6 posts por sección al día). No tienes que hacer nada una vez configurado.

Cada post lleva:

- **Portada** con el color de la sección, el antetítulo, el titular grande y una entradilla.
- **3 a 5 tarjetas** que se pasan con el dedo (qué ha pasado, claves, contexto, qué viene ahora).
- **Tarjeta «El dato»** con la cifra clave, solo si aparece en las fuentes.
- **Tarjeta de cierre**: la noticia en una frase, las fuentes y una llamada a seguir la cuenta.
- **Texto del post**: explicación resumida, por qué importa, una pregunta para que la gente comente, las fuentes y **5 hashtags** (el máximo que permite Instagram desde diciembre de 2025: 1 de tu marca + 4 elegidos para cada noticia). El texto incluye además palabras clave para que el post salga en el buscador de Instagram.

## Cómo funciona

```
Cada 15 min (GitHub Actions, gratis)
 └─ ¿Qué sección toca?  → reparto equilibrado; cada día rota el orden
 └─ Recoge noticias      → RSS de El País, El Mundo, La Vanguardia, Expansión, Marca, AS,
                           Xataka, idealista… + Google Noticias como reserva
 └─ Agrupa duplicados    → da prioridad a historias que cuentan varios medios
 └─ Claude (IA) elige    → la mejor noticia que no se haya publicado ya
 └─ Claude redacta       → reglas periodísticas: solo hechos de las fuentes, cita los medios, tono neutral
 └─ Dibuja las tarjetas  → JPEG 1080×1350
 └─ Publica en Instagram → API oficial de Meta (sin bots ni trucos)
```

---

## Puesta en marcha (unos 30 minutos, solo una vez)

### 1. Cuenta de Instagram profesional
En la app: **Configuración → Tipo de cuenta y herramientas → Cambiar a cuenta profesional** (Empresa o Creador). Pon en la biografía algo como *«Noticias elaboradas con ayuda de IA a partir de medios españoles»*: la transparencia evita problemas.

### 2. App de Meta para publicar (gratis)
1. Entra en <https://developers.facebook.com> → **Mis apps → Crear app** → tipo **Empresa**.
2. Añade el producto **Instagram** → **Configuración de la API con inicio de sesión de Instagram**.
3. En **Generar identificadores de acceso**, añade tu cuenta de Instagram y acepta los permisos `instagram_business_basic` e `instagram_business_content_publish`.
4. Copia el **token de acceso** y el **ID de usuario de Instagram** (el número que aparece junto a tu cuenta).

> La app puede quedarse en modo **Desarrollo**: para publicar en tu propia cuenta no hace falta la revisión de Meta.

### 3. Clave de Claude (la IA que redacta)
En <https://platform.claude.com> → **API Keys → Create Key**. Añade saldo en **Billing**.

### 4. Repositorio en GitHub (gratis)
1. Crea una cuenta en <https://github.com> y un repositorio **público** nuevo (por ejemplo `periodico`). Tiene que ser público para que Instagram pueda descargar las imágenes y para que GitHub Actions sea gratis sin límite. Tus claves siguen siendo secretas.
2. Sube **todo** el contenido de esta carpeta. ⚠️ La carpeta `.github` está oculta en Mac: pulsa **Cmd + Mayús + .** en el Finder para verla. También puedes usar **GitHub Desktop**.
3. **Settings → Actions → General → Workflow permissions** → marca **Read and write permissions** → Save.

### 5. Guardar las claves
**Settings → Secrets and variables → Actions → New repository secret**:

| Nombre | Valor |
|---|---|
| `ANTHROPIC_API_KEY` | la clave del paso 3 |
| `IG_ACCESS_TOKEN` | el token del paso 2 |
| `IG_USER_ID` | el ID del paso 2 |
| `GH_PAT` | un token de GitHub para renovar solo el de Instagram (ver abajo) |

**`GH_PAT`**: en GitHub, haz clic en tu foto → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**. Elige *Only select repositories* → tu repositorio; en *Permissions* → **Secrets: Read and write**. Sin vencimiento o con 1 año. El token de Instagram caduca a los 60 días; con esto se renueva solo cada lunes.

### 6. Probar antes de publicar
**Actions → Publicar en Instagram → Run workflow**, con «Modo prueba» marcado. Cuando acabe, abre la ejecución: verás el texto en el resumen y podrás descargar las tarjetas en **Artifacts**.

Si te gusta el resultado, lánzalo otra vez **sin** marcar «Modo prueba»: se publicará de verdad. A partir de ahí funciona solo cada 15 minutos.

---

## Día a día

| Quiero… | Cómo |
|---|---|
| Pausar las publicaciones | Settings → Secrets and variables → Actions → pestaña **Variables** → `PAUSADO` = `si` (bórrala para reanudar) |
| Cambiar el nombre, el @ o el eslogan | `config/ajustes.yaml` |
| Cambiar colores, fuentes o el peso de una sección | `config/secciones.yaml` (`peso: 2` = sale el doble) |
| Publicar una sección ahora | Run workflow → escribe la sección (p. ej. `deportes`) y desmarca «Modo prueba» |
| Ver qué se ha publicado | Pestaña **Actions**: cada ejecución muestra el titular y el enlace al post |
| Ver si alguna fuente falla | Actions → **Comprobar fuentes RSS** (se ejecuta solo cada día) |
| Gastar menos en IA | Variable `MODELO_REDACCION` = `claude-haiku-5-5` |

Si algo falla, GitHub te avisa por correo.

## Reels y Stories
- **Reels:** a las horas de `horas_reels` (en `config/ajustes.yaml`) la noticia se publica como vídeo vertical de 15–30 s, con las mismas tarjetas, transiciones y música. La música se genera por código, sin derechos de autor; si prefieres tus propias pistas libres de derechos, crea la carpeta `musica/` y sube ahí archivos .mp3.
- **Stories:** `stories_por_dia` portadas del día se publican como Story «Nuevo post».
- **Cuota:** Instagram admite unas 100 publicaciones por API al día, sumando posts, reels y stories. Por eso los huecos bajan a 90 (uno cada 16 min) y se reservan 6 para stories.
- **Probar un reel ahora:** Actions → Publicar en Instagram → Run workflow → Formato: `reel`.

## Costes aproximados

| Concepto | Coste |
|---|---|
| GitHub Actions (repositorio público) | 0 € |
| API de Instagram | 0 € |
| Claude: Sonnet redacta y Haiku elige | unos 2,5–3 $/día (≈ 80–90 $/mes) |
| Claude: todo con Haiku | menos de 1 $/día |

## Por qué 96 posts y no 144
Meta limita la API a **100 publicaciones cada 24 horas** por cuenta. Algunas partes de su documentación hablan incluso de 50. El programa consulta la cuota real antes de cada post y se salta el hueco si está a punto de agotarse, así nunca te bloquean. Si quieres 144, la opción es una segunda cuenta con este mismo programa y la mitad de las secciones.

> Consejo: una cuenta nueva que publica 96 veces al día puede parecer spam al principio. Si quieres ir con más cuidado, crea la variable `POSTS_POR_DIA` = `48` la primera semana y bórrala después.

## Responsabilidad editorial
La IA solo usa datos de las noticias que recoge, cita siempre los medios y descarta lo que no puede contrastar. Aun así, **nadie revisa los posts antes de publicarse**: el editor responsable eres tú. Échale un vistazo a la cuenta de vez en cuando y borra lo que no te convenza. No se copian fotos ni textos de los medios: las tarjetas son de diseño propio y los textos están redactados desde cero.

## Para técnicos
```bash
pip install -r requirements.txt
python -m periodico demo                       # tarjetas de ejemplo en ./ejemplos (sin claves)
python -m periodico plan                       # reparto de secciones de hoy
python -m periodico fuentes                    # estado de las fuentes RSS
ANTHROPIC_API_KEY=... python -m periodico publicar --prueba --seccion vivienda
```
- El estado y las imágenes en curso se guardan en la rama `datos`, que se reescribe en cada ejecución para que el repositorio no crezca.
- ¿Prefieres un repositorio privado? Crea el secreto `CLOUDINARY_URL` (cuenta gratuita de Cloudinary) y las imágenes se alojarán allí. Ten en cuenta que en un repositorio privado GitHub Actions solo incluye 2.000 minutos gratis al mes, y este sistema gasta más: el exceso se paga.
- ¿Usas Facebook Login con un usuario del sistema? Crea la variable `IG_GRAPH_HOST` = `graph.facebook.com`.
- Tipografías Inter y Lora (licencia SIL OFL, en `fonts/`).
