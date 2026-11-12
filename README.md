# Radar Laboral

Aplicación de escritorio local que reúne avisos de empleo de varios portales,
los ordena según el perfil configurado y permite marcarlos. **No postula
automáticamente ni envía el CV a ningún sitio.**

El plan completo está en [`PLAN.md`](PLAN.md).

## Estado actual — Fase 1 + Fase A + Fase C + aprendizaje (etapa 1) + configuración + Empresas (ATS) + Jooble + asistente de CV con Word
- Backend FastAPI + SQLite con búsqueda de texto completo (FTS5).
- Conectores de **Computrabajo AR**, **BuscoJobs AR**, **ZonaJobs AR**,
  **Bumeran AR**, **GetOnBoard**, **Empleos IT**, **Empresas (ATS)**,
  **Jooble** (requiere clave del dominio argentino), **Remotive**,
  **RemoteOK**, **Himalayas** y **Jobicy**.
- **5 perfiles (P1–P5)** con puntaje 0–100 y explicación por aviso.
- **Vista “Hoy”** con los avisos que superan el umbral (70), ordenables por
  **puntaje** o por **fecha** (ascendente o descendente).
- **Deduplicación entre portales**: una tarjeta por aviso, ocultando repetidos.
- Filtros por perfil, fuente, modalidad, seniority, idioma, puntaje mínimo y
  estado, además de la búsqueda por texto.
- Ventana nativa con pywebview.
- Interfaz React: lista, búsqueda, filtros, detalle con “por qué matchea” y
  estados (nuevo / visto / guardado / descartado / postulado) con notas.
- Actualización manual con progreso en vivo.
- **Panel de configuración**: activa o desactiva fuentes para las próximas
  actualizaciones, con estado, confiabilidad y última corrida de cada una.
- **BuscoJobs AR** integrado con lectura del JSON `__NEXT_DATA__`, pausas
  lentas y corte automático si el WAF pide verificación humana.
- **ZonaJobs AR y Bumeran AR** integrados con **sesión asistida**: una ventana
  real de Edge con perfil persistente para que la persona resuelva Cloudflare a
  mano; la app reutiliza esa sesión y consulta la API de avisos.
- **Feedback de preferencias (etapa 1)**: botones “Me interesa” / “No me
  interesa” por aviso, con motivos, y etiquetas derivadas de los estados.
- **Asistente de CV (opcional)**: adapta el CV base a cada aviso con la Gemini
  API, muestra qué cambió y qué falta cubrir, y guarda versiones. Importa tu CV
  en Word y descarga la copia adaptada con tu propia plantilla. Manual, sin
  postulaciones automáticas.

### Perfiles y puntaje

| Perfil | Nombre | Prioridad |
|---|---|---|
| P1 | ML / Visión | 1 |
| P2 | Backend / Full Stack | 2 |
| P3 | Analista Funcional | 3 |
| P5 | Docencia / Educación IT | 4 |
| P4 | Soporte IT | 5 |

El score combina skills (40), rol (20), seniority (10), zona/modalidad (10),
idioma (10) y recencia (10). Trainee/Junior suma 10 y Senior resta 30.
La vista “Hoy” muestra los avisos con **70 puntos o más**.

### Fuentes

| Fuente | Tipo | Cómo busca | Qué trae |
|---|---|---|---|
| Computrabajo AR | HTML | 4 búsquedas por texto | Avisos de Argentina (CABA/GBA y país) |
| BuscoJobs AR | HTML + JSON | 4 búsquedas, 1 página y ritmo lento | Avisos de Argentina (CABA/GBA, provincias y teletrabajo) |
| ZonaJobs AR | API Navent | 4 búsquedas con sesión asistida | Avisos de Argentina (CABA/GBA, provincias y remoto) |
| Bumeran AR | API Navent | 4 búsquedas con sesión asistida | Avisos de Argentina (CABA/GBA, provincias y remoto) |
| LinkedIn | HTML público | 3 búsquedas sin login (opcional) | Avisos de Argentina; apagado por defecto |
| GetOnBoard | HTML | 4 categorías tech | Avisos remotos de Latam y presenciales/híbridos en Argentina |
| Empleos IT | HTML | 19 categorías IT | Avisos de Argentina (CABA/GBA, provincias y remoto) |
| Empresas (ATS) | API | 17 boards públicos de Lever, Greenhouse y Ashby | Avisos de Argentina, remoto LatAm y remoto global; solo roles IT y afines |
| Jooble | API con clave | 2 búsquedas agrupadas, 1 página de hasta 100 | Avisos de Argentina, remoto LatAm y global; usa clave del dominio `ar.jooble.org` |
| Remotive | API | Listado general | Remoto LatAm / Argentina / Worldwide, solo roles IT |
| RemoteOK | API | Listado general | Remoto LatAm / Argentina / Worldwide, solo roles IT |
| Himalayas | API | 3 páginas de 20 | Remoto LatAm / Argentina / Worldwide, solo roles IT |
| Jobicy | API | 100 avisos | Remoto LatAm / Argentina / Worldwide, solo roles IT |

GetOnBoard se recorre por categorías (`programacion`,
`data-science-analytics`, `sysadmin-devops-qa`, `desarrollo-mobile`) y se
descartan los avisos presenciales/híbridos radicados fuera de Argentina.
Los remotos se conservan; la ubicación exacta se muestra en cada aviso.

Empleos IT se recorre por categorías alineadas a los perfiles (desarrollo,
datos, soporte, análisis funcional, DevOps, seguridad, PM) y trae el listado
completo de cada una en una sola página.

Empresas (ATS) consulta las **APIs JSON oficiales** de los boards de cada
compañía, sin scraping de HTML ni credenciales. La lista vive en
`backend/config.py` (`ATS_EMPRESAS`) y hoy incluye 17 boards:

| ATS | Boards |
|---|---|
| Lever | `despegar`, `aleph` |
| Greenhouse | `santex`, `clara`, `quintoandar`, `dept`, `gofundme`, `greenhouse` |
| Ashby | `whippy`, `mural`, `nubank`, `canals`, `homevision`, `stensul`, `profound`, `rehire`, `arq` |

El token es el slug que aparece en la URL del board (`jobs.lever.co/<token>`,
`job-boards.greenhouse.io/<token>` o `jobs.ashbyhq.com/<token>`). Para sumar una
empresa alcanza con agregar una línea con `ats`, `token` y `nombre`; para
quitarla, borrar su línea. El conector trae título, empresa, ubicación, fecha,
descripción completa, salario (si el board lo publica) y URL.

Los filtros son más estrictos que en los boards remotos:

- **Zona**: Argentina, remoto LatAm explícito o remoto global. Se descartan las
  sedes presenciales en otros países de LatAm y los remotos limitados a un solo
  país que no sea Argentina.
- **Rol**: solo títulos de IT, datos, producto, análisis funcional, soporte
  técnico y docencia. Se excluyen ventas, marketing, recruiting, finanzas,
  legal y operaciones.
- **Antigüedad**: se descartan los avisos con más de 30 días antes de guardarlos,
  para no ingerir lo que la limpieza borraría enseguida.

Un board caído no corta la fuente: cada empresa se consulta por separado y el
error queda en el registro de escaneos. Si un board responde 403/429, la fuente
se pausa para no agravar el bloqueo.

**Jooble** usa su API REST oficial con clave gratuita. Cada país tiene su
propio dominio y su propia clave: una clave pedida en `jooble.org` solo
devuelve avisos de **EE. UU.**, así que para Argentina hay que solicitarla en
`https://ar.jooble.org/api/about`. La clave va en el `.env`
(`JOOBLE_API_KEY`); si falta o es de otro país, la fuente avisa en el registro
de escaneos en vez de guardar avisos equivocados. El plan gratuito tiene
**500 consultas en total por clave** (no mensuales), por eso los términos se
agrupan en dos consultas y se pide una sola página de hasta 100 avisos por
búsqueda. Al activarla, la app avisa de estas condiciones.

La API entrega título, empresa, ubicación, salario (si existe), tipo, fecha y
un resumen corto; la descripción completa queda en el aviso original, que se
abre desde la app. Se aplican los mismos filtros de zona, de rol y de 30 días
que en Empresas (ATS), más un descarte de títulos no técnicos.

Las APIs remotas son genéricas: se descartan los países que no interesan
(EE. UU., Europa, Asia, etc.) y los títulos que no son de IT. Los avisos en
inglés se muestran etiquetados como **Inglés**.

LinkedIn es opcional y está **apagado por defecto**. Se activa desde
Configuración; al hacerlo consulta 3 búsquedas públicas sin login, con pausas
largas. Sus términos de uso prohíben la recolección automatizada y el sitio
limita rápido (HTTP 429): si eso pasa, la fuente se pausa 30 minutos. No usa
cookies de sesión, proxies ni captchas.

BuscoJobs AR se lee desde el JSON `__NEXT_DATA__` que el propio sitio incrusta
en sus páginas, sin navegador. Como está detrás de un WAF de AWS, usa pausas
de 12 segundos, una sola página por búsqueda y el detalle se carga recién al
abrir el aviso. Se descartan los títulos industriales (CNC, obra, logística,
PLC) que no son de IT, salvo que el aviso traiga una señal tecnológica clara. Si el portal responde con “Human Verification” (HTTP 405) o un
desafío equivalente, **la fuente se detiene sin reintentar** y el error queda
visible en la barra de estado. No se resuelven captchas automáticamente: si el
bloqueo persiste, hay que esperar a que el portal lo libere.

### Sesión asistida: ZonaJobs y Bumeran

Los dos portales usan la misma API de avisos (Navent) y están detrás de
Cloudflare. La app **no intenta resolver el desafío**:

1. Al actualizar, si la sesión no está validada se abre una ventana real de
   Edge con el perfil persistente `data/sesion_navent`.
2. La persona resuelve la verificación de Cloudflare en esa ventana. La app
   espera hasta 2 minutos y detecta la validación sola.
3. Con la sesión validada, la consulta a `/api/avisos/searchV2` se hace desde
   la misma pestaña (mismo origen y cookies) y los avisos se importan.

Desde el banner **Sesión asistida** también se puede abrir el portal a mano con
“Abrir ZonaJobs” / “Abrir Bumeran” (o “Renovar” si la sesión venció). ZonaJobs y
Bumeran comparten el perfil de navegador, así que hay que **cerrar una ventana
antes de abrir la otra** y cerrarla antes de volver a actualizar.

Como los dos portales publican el mismo catálogo, la deduplicación deja **una
sola tarjeta por aviso**; puede aparecer bajo Bumeran o bajo ZonaJobs.

Advertencia: reutilizar una sesión y consultar la API desde la ventana del
portal puede contravenir los términos de uso del sitio. Es una decisión del
usuario, con bajo volumen de consultas y sin automatizar postulaciones.

### Panel de configuración y limpieza

El botón **Configuración** abre el panel de fuentes. Cada fila tiene un
interruptor para activar o desactivar la ingesta; apagar una fuente **no borra**
los avisos ya guardados, solo detiene las próximas actualizaciones. El panel
muestra el estado, la confiabilidad, la última corrida y el último error de cada
fuente.

Abajo hay un bloque de **Mantenimiento** con la vista previa de la limpieza:

- Se eliminan los avisos con más de **30 días** de antigüedad
  (`COALESCE(published_at, fetched_at)`).
- Se conservan los avisos **guardados** y **postulados**.
- También se conservan los que tienen **nota** o **algún voto de feedback**, para
  no perder señal de entrenamiento.
- Después del borrado se recalculan los duplicados.

La limpieza corre **automáticamente al final de cada ingesta** y también se puede
ejecutar a mano con **Limpiar ahora**. `GET /api/cleanup/preview` muestra cuántos
avisos se eliminarían sin borrar nada y `POST /api/cleanup` ejecuta el borrado.

### Registro de escaneos

El botón **Registro** de la barra superior abre un log de los eventos de las
últimas actualizaciones:

- Inicio y fin de cada corrida, con encontrados, nuevos, actualizados y errores.
- Inicio y resumen por fuente (encontrados, nuevos, actualizados).
- Errores de búsqueda, bloqueos anti-bot, fallos al guardar y fuentes en pausa.
- Resultado de la limpieza automática de avisos antiguos.

Cada línea tiene hora, nivel (`info`, `warn` o `error`), fuente y mensaje. Se
puede filtrar con **Solo errores** y el registro se actualiza solo mientras hay
un escaneo en curso. Si la última corrida terminó con errores, el botón muestra
un contador rojo. Los eventos se guardan en `run_logs` y se podan a los 14 días
o 3000 filas. `GET /api/logs?limit=150` devuelve el historial.

### Aprendizaje por preferencias (etapa 1)

Todavía **no cambia el puntaje**: solo recolecta la señal para las próximas
etapas. En cada tarjeta y en el detalle hay dos botones:

- **Me interesa** → voto `+1`.
- **No me interesa** → voto `-1`; en el detalle se pueden marcar motivos
  (seniority, stack, zona, modalidad, empresa, idioma, tareas, salario).

Cada voto se guarda en la tabla `feedback` con el `score`, el perfil y un
snapshot del `score_detail` del momento. Los estados también cuentan como
etiquetas débiles:

| Estado | Peso |
|---|---|
| Postulado | +2 |
| Guardado | +1 |
| Visto / Nuevo | 0 |
| Descartado | −2 |

El voto explícito tiene prioridad sobre el estado para no contar dos veces la
misma decisión. `GET /api/feedback/summary` devuelve los conteos y cuántos
ejemplos faltan para poder entrenar (meta inicial: 30 positivos y 30 negativos).
Con esa base, la etapa 2 puede sumar una afinidad suavizada y la etapa 3 un
clasificador local.

## Requisitos

- Python 3.12+ (probado en 3.14.6)
- Node.js 20+ (frontend y sesión asistida de ZonaJobs/Bumeran)
- Microsoft Edge o Google Chrome instalado

## Puesta en marcha

```powershell
git clone https://github.com/braianpezet/radarlaboral.git
cd radarlaboral

pip install -r requirements.txt

cd frontend
npm install
npm run build
cd ..

cd assisted
npm install
cd ..

python run.py
```

Se abre una ventana con la aplicación. La primera vez no hay avisos:
apretá **Actualizar ahora** para traer las primeras ofertas.

### Claves opcionales (`.env`)

Las fuentes que usan clave leen el archivo `.env` de la raíz del proyecto. Ya
está en `.gitignore`, así que no se comparte ni se sube a ningún lado:

```
JOOBLE_API_KEY=<clave del dominio ar.jooble.org>
GEMINI_API_KEY=<clave gratuita de aistudio.google.com/apikey>
# GEMINI_MODELO=                # opcional: vacío elige un Flash-Lite disponible
```

Las variables del entorno tienen prioridad sobre el archivo. Si borrás una
clave, la fuente avisa en el registro de escaneos y se puede apagar desde
Configuración. La clave de Gemini solo habilita el asistente de CV.

### Modo desarrollo

Terminal 1 (API):

```powershell
python run.py --no-window --verbose
```

Terminal 2 (frontend con recarga en caliente):

```powershell
cd frontend
npm run dev
```

Abrí `http://127.0.0.1:5173`.

## Estructura

```
radar-laboral/
├── backend/
│   ├── config.py            # rutas, puerto, búsquedas
│   ├── db.py                # esquema SQLite + FTS5
│   ├── main.py              # API FastAPI
│   ├── connectors/
│   │   ├── base.py          # JobRaw, FuenteBloqueada y SesionAsistidaRequerida
│   │   ├── buscojobs.py     # conector HTML + JSON (Next.js)
│   │   ├── computrabajo.py  # conector HTML
│   │   ├── filtros.py       # descarte de títulos industriales
│   │   ├── getonboard.py    # conector HTML
│   │   ├── empleosit.py     # conector HTML (Argentina)
│   │   ├── empresas.py      # boards ATS: Lever, Greenhouse y Ashby
│   │   ├── jooble.py        # Jooble (API con clave por país)
│   │   ├── linkedin.py      # LinkedIn público (opcional, apagado)
│   │   ├── navent.py        # ZonaJobs y Bumeran (API + sesión asistida)
│   │   └── remotos.py       # Remotive, RemoteOK, Himalayas, Jobicy
│   └── services/
│       ├── ingest.py        # orquestación y guardado
│       ├── profiles.py      # perfiles P1–P5 y cálculo del score
│       ├── scoring.py       # recálculo y persistencia del puntaje
│       ├── dedupe.py        # agrupación de duplicados entre portales
│       ├── cv.py            # asistente de CV con la Gemini API
│       ├── cv_docx.py       # importación y generación de CV en Word
│       ├── guardar.py       # diálogo "Guardar como" de Windows
│       ├── limpieza.py      # retención de 30 días y purga de avisos
│       ├── logs.py          # registro de eventos de los escaneos
│       ├── sesiones.py      # estado y apertura de la sesión asistida
│       └── text.py          # fechas, salario, idioma, modalidad
├── assisted/
│   ├── navent.mjs           # Edge + Playwright para ZonaJobs/Bumeran
│   └── package.json         # playwright-core
├── frontend/                # React + Vite
├── data/                    # base SQLite (se crea sola) + perfil de sesión
├── run.py                   # lanzador con ventana
└── PLAN.md
```

## Asistente de CV (opcional)

Con una clave gratuita de la **Gemini API** la app puede reescribir tu CV para
un aviso concreto:

1. Abrí **Mi CV** (botón en la barra superior) y pegá tu CV base, o importá un
   archivo `.docx` con **Importar Word**. El texto queda en el cuadro para que lo
   revises antes de guardarlo.
2. Abrí un aviso y usá **Adaptar mi CV**.
3. Revisá el resultado, la lista de cambios y lo que falta cubrir; copialo,
   descargalo como `.md` o como **Word**.

El `.docx` que importás queda guardado como **plantilla**: la copia adaptada
conserva tu página, márgenes, cabecera (nombre y contacto), fuente y tamaños, y
vuelca el contenido nuevo respetando el diseño. Si no importás ninguna plantilla,
la app genera un Word limpio con el mismo contenido. La generación del Word es
local y no consume la API. Antes de descargarlo podés cambiar el nombre del
archivo en el mismo bloque del asistente.

Al guardar la copia, tanto en Word como en `.md`, se abre la ventana
**Guardar como** de Windows para elegir la carpeta y, si hace falta, el nombre
final. La app escribe el archivo directamente en la ruta elegida, sin pasar por
la carpeta de descargas. Si esa ventana no está disponible (por ejemplo, si
abrís la interfaz en un navegador normal), se usa el selector del navegador y,
como último recurso, la descarga habitual.

Qué hace y qué no:

- Solo reformula, reordena y resume lo que ya está en tu CV: no inventa
  experiencia, empresas, títulos ni fechas. Lo que pide el aviso y no tenés
  aparece aparte en **Falta cubrir**.
- Es manual, aviso por aviso. La app no postula, no envía el CV a ningún portal
  y no completa formularios.
- Guarda las versiones en la base local, para poder volver a una anterior.

La suscripción **Google AI Plus** (o Gemini) **no incluye acceso a la API**: es
otro producto y se factura aparte. La clave se crea gratis en
`https://aistudio.google.com/apikey` y se guarda en `.env` como
`GEMINI_API_KEY`.

Con el nivel gratuito alcanza de sobra (una adaptación ≈ 1 request), pero
Google puede usar ese contenido para mejorar sus productos. Si eso no te
conviene, dejá el asistente sin clave: el resto de la app funciona igual.

## Datos y privacidad

- Todo se guarda en `data/radar.db`, en tu equipo.
- La sesión asistida guarda las cookies del portal en `data/sesion_navent`,
  también en tu equipo; se puede borrar esa carpeta para empezar de cero.
- La clave de Jooble se guarda en `.env`, en tu equipo y fuera de lo que se
  comparte. Solo se usa para consultar la API de Jooble.
- El CV base, la plantilla `.docx` y las adaptaciones se guardan en
  `data/radar.db`, en tu equipo.
- La plantilla solo se usa para generar el Word adaptado en tu equipo; no se
  envía a Google. Al adaptar solo se envía el texto del CV y la descripción del
  aviso.
- No se envía el CV ni datos personales a ningún servicio salvo que uses el
  asistente de CV (ver abajo), que lo hace a pedido y con confirmación.
- El conector de LinkedIn está incluido pero **desactivado por defecto**; se
  puede activar desde Configuración, con aviso de ToS y riesgo de bloqueo.
- Los avisos con más de 30 días se purgan automáticamente, salvo que estén
  guardados, postulados, valorados o tengan nota.

## Aviso legal y uso responsable

Este es un proyecto personal, sin fines comerciales y sin relación con los
portales que consulta. Los conectores solo leen información pública, con
pausas y bajo volumen; no automatizan postulaciones, no envían el CV y no
resuelven captchas ni eluden autenticaciones.

Cada portal tiene sus propios términos de uso. La app permite apagar cualquier
fuente y así debe quedar si el sitio no permite la consulta automatizada. El
uso de cada conector es responsabilidad de quien ejecuta la aplicación.

## Próximas fases

1. Notificaciones internas y actualización programable en horas.
2. Clave de Careerjet (cuenta de publisher; devuelve extractos cortos). Jooble ya está integrado.
3. Exportación a CSV y tablero de postulaciones.
4. Aprendizaje etapa 2: afinidad suavizada sobre el feedback recolectado.

## Licencia

[MIT](LICENSE) © 2026 Braian Pezet
