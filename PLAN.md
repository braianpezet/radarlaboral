# Radar Laboral — Plan de proyecto

Aplicación de escritorio, 100 % local, que reúne avisos de empleo de varios portales,
los puntúa contra el perfil configurado y muestra una lista ordenada por
compatibilidad.

**No postula, no envía el CV, no inicia sesión en ningún portal.**

- Estado: **Fase C + aprendizaje etapa 1 + panel de fuentes + LinkedIn opcional + limpieza + registro + Empresas (ATS) + Jooble + asistente de CV con Word** (2026-11-12)
- Fecha: 2026-11-04
- Ubicación del código: raíz del repositorio

---

## 1. Decisiones de producto

| Tema | Decisión |
|---|---|
| Interfaz | App web local (FastAPI + React) en ventana propia con pywebview |
| Fuentes | APIs públicas + scraping best-effort, cada conector apagable |
| Zonas | CABA/GBA · Remoto Argentina · Remoto LATAM |
| Idioma | Español primero, inglés después (solo si acepta LatAm/Worldwide) |
| Seniority | Trainee/Junior (+15) y Semi-Senior (0); Senior/Lead (−30) |
| Perfil prioritario | P1 · ML / Visión por Computadora |
| Salario | Sin filtro; informativo si el aviso lo publica |
| Actualización | Manual + intervalo configurable en horas (6 h por defecto, apagable) |
| Avisos nuevos | Solo dentro de la app (badge/contador) |
| LinkedIn | **Apagado por defecto** (ToS + riesgo de bloqueo de IP) |
| Perfil "Varios" (P6) | Apagado por defecto |
| Asistente de CV | Manual y por aviso; usa la Gemini API con clave propia (nivel gratuito). Importa y exporta Word con la plantilla propia. No postula ni envía el CV |

---

## 2. Perfiles de búsqueda

Derivados de los CV del autor, fuera del repositorio.

| Perfil | Roles objetivo | Skills núcleo | Descarta si… |
|---|---|---|---|
| **P1 · ML / Visión** | Investigador, ML Engineer, Data Scientist, CV Engineer | Python, YOLO, OpenCV, PyTorch, numpy | ventas, sin relación a datos |
| **P2 · Backend / Full Stack** | Dev Backend, Full Stack, Java/Spring, Node, PHP, React | Java, Spring Boot, Node, React/Next, SQL, AWS, Git | solo diseño, soporte telefónico |
| **P3 · Analista Funcional** | Analista Funcional, BA, PM Jr, PO Jr | relevamiento, requerimientos, UML, SQL, Scrum, testing | senior 8+ años |
| **P4 · Soporte IT** | Helpdesk, Soporte Técnico, Infra, SysAdmin Jr | Windows, Linux, redes, Office 365, SQL | ventas, call center, chofer |
| **P5 · Docencia / Educación IT** | Docente, Tutor, JTP, Capacitador | docencia, planificación, evaluación, IA, programación | sin formación, ventas |
| **P6 · Varios** (off) | Administrativo, data entry | Office, atención al público | — |

Orden de la pantalla "Hoy": **P1 → P2 → P3 → P5 → P4** (editable).

---

## 3. Fuentes

| Fuente | Tipo | Estado probado | Idioma | Estado |
|---|---|---|---|---|
| GetOnBoard (web) | HTML | 200 | ES | **ON** |
| GetOnBoard (API) | API token | 401 sin token | ES | OFF hasta tener token |
| Computrabajo AR | HTML | 200 | ES | **ON** |
| BuscoJobs AR | HTML + JSON Next.js | 200 / 405 por WAF | ES | **ON** con ritmo lento |
| Empleos IT (AR) | HTML | 200 | ES | **ON** |
| Empresas (ATS) | API Lever/Greenhouse/Ashby | 200 (17 boards) | ES/EN | **ON** + filtro zona/rol/30 días |
| Remotive | API sin clave | 200 (pocos avisos) | EN | **ON** + filtro LatAm/Worldwide |
| RemoteOK | API sin clave | 200 | EN | **ON** + linkback |
| Himalayas | API sin clave | 200 | EN | **ON** + filtro LatAm/Worldwide |
| Jobicy | API sin clave | 200 | EN | **ON** + filtro LatAm/Worldwide |
| Bumeran AR | API Navent + Edge | 200 con sesión asistida | ES | **ON** (modo asistido) |
| Zonajobs AR | API Navent + Edge | 200 con sesión asistida | ES | **ON** (modo asistido) |
| Empleos Clarín | HTML | SSL/522 y redirección | ES | **OFF** (subdominio caído) |
| LinkedIn guest | HTML público | 200 / 429 si se insiste | ES/EN | **OFF por defecto** (ToS; activable) |
| The Muse | API sin clave | 200 | EN | Probada, no integrada |
| Arbeitnow | API sin clave | 200 | EN/DE | Probada, no integrada |
| Jooble | API con clave por país | 200 con clave de `ar.jooble.org` | ES/EN | **ON** (clave AR en `.env`) |
| Careerjet | API con clave | conexión rechazada sin clave | ES | OFF hasta tener clave |
| Adzuna | API con clave | 400 sin clave | ES/EN | OFF hasta tener clave |
| Indeed AR | HTML/RSS/móvil + Cloudflare | 403 challenge/bloqueo | ES/EN | **Descartada** (ToS + sin API pública) |
| InfoJobs AR | web | DNS caído | — | Descartada |
| InfoJobs ES | API OAuth | 401 | ES | Opcional, trámite pesado |

### Reglas por fuente

- **Rate limit** propio por conector + caché de respuestas.
- **Timeout** individual; ZonaJobs y Bumeran corren en secuencia, cada uno con
  su ventana visible y un tope de tiempo propio.
- **Backoff** ante 429/5xx; si falla 3 veces seguidas, la fuente queda en pausa y avisa en la UI.
- **WAF/captcha**: si un portal responde con un desafío anti-bot (por ejemplo
  BuscoJobs con “Human Verification” o HTTP 405), la fuente se corta en el acto,
  se registra el error y se espera. Nunca se resuelve el captcha automáticamente.
  La fuente bloqueada queda en pausa 30 minutos y no se reintenta antes, ni
  siquiera con una actualización manual.
- **Modo asistido** (ZonaJobs y Bumeran): la app abre un Edge real con perfil
  persistente y espera a que la persona resuelva Cloudflare. Después consulta
  la API desde la misma pestaña. No usa servicios de captcha, plugins stealth
  ni proxies rotativos; tampoco automatiza postulaciones.
- **LinkedIn (opcional, apagado por defecto)**: búsqueda pública sin login,
  3 consultas separadas por 8 segundos. Si responde 429/999, la fuente se
  pausa 30 minutos para no agravar el límite. La persona lo activa desde
  Configuración y acepta el aviso de ToS.
- **Aislamiento**: un conector roto no afecta al resto.
- **Linkback** obligatorio a la fuente original en cada aviso.

---

## 4. Motor de matching

Pipeline: ingesta → normalización → idioma → extracción de entidades → filtro de
exclusión → scoring → explicación → deduplicación → guardado.

### Normalización

- Minúsculas, sin acentos, sin puntuación.
- Alias de skills: `react.js → react`, `py → python`, `ML → machine learning`,
  `visión por computadora ↔ computer vision`, `spring → spring boot`.

### Entidades

Skills, seniority (`jr/ssr/sr/lead`, "3+ años", "sin experiencia"), modalidad
(remoto/híbrido/presencial), ubicación, salario, tipo de contrato, idioma.

### Score (0–100)

| Dimensión | Peso | Cómo |
|---|---|---|
| Skills técnicas | 40 | cobertura ponderada de skills núcleo |
| Afinidad de rol/título | 20 | similitud título ↔ roles objetivo |
| Seniority | 10 | Jr/Trainee +10 · SSR 0 · Sr −30 |
| Zona / modalidad | 10 | CABA/GBA, Remoto AR, Remoto LATAM |
| Idioma | 10 | ES 10 · sin dato 6 · EN 4 |
| Recencia | 10 | <24 h 10 · <3 d 8 · <7 d 6 · <14 d 4 · <30 d 2 |

**Reglas duras:** títulos de ventas, call center, administración o logística se
excluyen (score 0, no se muestran).

**Umbrales (implementados):** ≥70 vista “Hoy” · 55–69 compatible ·
40–54 explorar · <40 fuera de la vista principal.

**Explicación:** el detalle muestra el perfil elegido, los motivos, las skills
que coinciden, las que faltan y el desglose de los 6 componentes.

### Aprendizaje por preferencias (etapa 1)

Todavía **no modifica el puntaje**: solo recolecta la señal y la deja lista para
las etapas 2 y 3.

- **Voto explícito:** botones “Me interesa” (`+1`) / “No me interesa” (`−1`) en
  cada tarjeta y en el detalle. Con voto negativo se pueden marcar motivos:
  seniority, stack, zona, modalidad, empresa, idioma, tareas, salario.
- **Persistencia:** tabla `feedback`, con el voto, los motivos y un snapshot de
  `score`, `profile_id` y `score_detail` al momento de votar. El último voto por
  aviso es el vigente; votar de nuevo el mismo valor actualiza los motivos.
- **Etiquetas desde estados:** postulado `+2`, guardado `+1`, descartado `−2`,
  visto/nuevo `0`. El voto explícito tiene prioridad sobre el estado para no
  contar dos veces la misma decisión.
- **Meta inicial de entrenamiento:** 30 etiquetas positivas y 30 negativas.
  `GET /api/feedback/summary` informa el avance y los motivos más frecuentes.
- **Etapa 2 (propuesta):** afinidad suavizada (±12) explicada en el detalle.
- **Etapa 3 (propuesta):** regresión logística local con validación temporal,
  usando los 6 componentes del score como features.

---

## 5. Deduplicación

- Agrupación por **empresa normalizada**.
- Los avisos **sin empresa** se agrupan por título + ubicación y solo se
  fusionan si la descripción coincide en un 95 % o más (mismo aviso replicado
  en ZonaJobs y Bumeran).
- Fingerprint igual → duplicado; si no, **similitud de título ≥ 92 %** con
  ubicación compatible.
- Si el título supera 80 %, se compara la **descripción: ≥ 92 %**.
- Canónico: el que tiene descripción, mayor score y fuente local
  (Empleos IT > GetOnBoard > Computrabajo > APIs).
- Los duplicados se ocultan de la lista (`duplicate_of`) pero se conservan en
  la base para auditoría.

---

## 6. Arquitectura

```
Ventana pywebview
  └── React + Vite  ──►  http://127.0.0.1:8765
                              │ REST local
                        FastAPI
                          ├── /jobs /profiles /sources /runs /settings
                          ├── Scheduler (APScheduler)
                          └── Motor de matching
                        Conectores (api · rss · html)
                          └── Normalizador → Deduplicador
                        SQLite (WAL) + FTS5 + caché + logs
```

Un solo proceso, sin nube, sin servidor externo.

---

## 7. Modelo de datos

```
sources      (id, nombre, tipo, confiabilidad, activo, requiere_clave,
              ultima_ejecucion, ultimo_error)
companies    (id, nombre, nombre_normalizado)
jobs         (id, source_id, external_id, url, titulo, company_id,
              descripcion, ubicacion, modalidad, seniority, contrato,
              salario_min, salario_max, moneda, periodo,
              idioma, publicado_en, obtenido_en,
              fingerprint, hash_contenido, estado)
skills       (id, nombre, aliases, categoria)
job_skills   (job_id, skill_id, evidencia)
profiles     (id, nombre, activo, cv_archivo, pesos_json, filtros_json)
matches      (job_id, profile_id, score, detalle_json, gaps_json)
job_status   (job_id, estado, nota, fecha)
feedback     (id, job_id, profile_id, voto, motivos_json,
              score_base, features_json, creado_en)
runs         (id, inicio, fin, source_id, encontrados, nuevos, errores)
settings     (clave, valor)
jobs_fts     -- tabla virtual FTS5
```

Estados manuales: `nuevo`, `visto`, `guardado`, `descartado`, `postulado`.

---

## 8. Interfaz

1. **Hoy** — avisos con score ≥ 70, con filtro por perfil: pantalla principal
   (**implementada**).
2. **Lista / búsqueda** — filtros por perfil, fuente, estado, modalidad,
   seniority, idioma, zona y puntaje mínimo, más texto libre; orden por puntaje
   o fecha en ambos sentidos (**implementada**).
3. **Detalle** — panel lateral superpuesto, sin achicar la lista: descripción
   completa, "por qué matchea", gaps y acciones (abrir original, guardar,
   descartar, marcar postulado, nota, votar con motivos) (**implementado**).
4. **Postulaciones** — tablero de lo marcado, con fecha y nota.
5. **Configuración** — fuentes on/off (**implementado**); perfiles y pesos,
   claves, intervalo y exportación quedan pendientes.

Barra de estado: última actualización, próxima, errores por fuente.

Al guardar la copia adaptada (Word o `.md`) se abre la ventana **Guardar como**
de Windows para elegir carpeta y nombre; el endpoint `/api/guardar-como` escribe
el archivo en esa ruta. Si no está disponible (navegador normal), se usa el
selector del navegador o la descarga directa.

---

## 9. Actualización

- Botón "Actualizar ahora" siempre disponible.
- Campo "Actualizar cada __ horas" (default 6, se puede apagar → 100 % manual).
- Sin notificaciones de Windows: badge y contador dentro de la app.
- Bandeja del sistema opcional para segundo plano.

---

## 10. Privacidad y legal

- El CV base, la plantilla `.docx` y las adaptaciones se guardan en la base local.
- La plantilla Word se usa solo para generar la copia adaptada en el equipo; no
  se envía a Gemini.
- El matching nunca sale de la PC.
- El asistente de CV es **opt-in**: solo envía el CV y la descripción del aviso
  a Google Gemini cuando la persona pide una adaptación, tras confirmarlo la
  primera vez. Con el nivel gratuito, Google puede usar ese contenido para
  mejorar sus productos.
- Scraping: solo lectura, rate limit, User-Agent identificable, respeto de
  `robots.txt`, linkback a la fuente.
- LinkedIn: **apagado por defecto** por ToS y riesgo de bloqueo de IP.
- Sin login automatizado, sin captchas, sin reventa de datos.
- Los desafíos anti-bot se resuelven solo de forma manual (modo asistido); la
  app no usa servicios de captcha, proxies rotativos ni plugins de evasión.
- Claves API en el archivo `.env` local, fuera del repositorio.
- Opcional futuro: Ollama local como alternativa al asistente en la nube.

---

## 11. Stack

| Capa | Elección |
|---|---|
| Backend | Python 3.14 + FastAPI + httpx async |
| Word | python-docx (importación y plantilla) |
| Scraping | selectolax / BeautifulSoup + lxml |
| Matching | rapidfuzz + diccionario propio de skills |
| DB | SQLite + FTS5 |
| Scheduler | APScheduler |
| Frontend | React + Vite + TypeScript + Tailwind |
| Ventana | pywebview (WebView2) |
| Tray | pystray (opcional) |
| Empaquetado | PyInstaller |

Se evita PySide6 por compatibilidad con Python 3.14.

---

## 12. Fases

| Fase | Entregable | Estado |
|---|---|---|
| 0 | Esqueleto: DB, FastAPI, ventana, Computrabajo + lista básica | **Hecho** |
| 0b | GetOnBoard, Empleos IT y 4 APIs remotas (Remotive, RemoteOK, Himalayas, Jobicy) | **Hecho** |
| 1 | 5 perfiles + scoring + deduplicación | **Hecho** |
| A | BuscoJobs AR con JSON Next.js, ritmo lento, filtro IT y corte por WAF | **Hecho** |
| B | APIs de Jooble y Careerjet con clave gratuita | Jooble: **hecho** con clave AR. Careerjet: pendiente |
| C | Modo asistido para Bumeran/ZonaJobs (sesión manual) | **Hecho** |
| D | Aprendizaje por preferencias: feedback y etiquetas | **Etapa 1 hecha** |
| E | Panel de configuración: activar/desactivar fuentes | **Hecho** |
| F | LinkedIn guest opcional, apagado por defecto | **Hecho** |
| G | Limpieza automática de avisos con más de 30 días | **Hecho** |
| H | Registro de escaneos visible en la UI | **Hecho** |
| I | Boards de empresas con ATS público (Lever/Greenhouse/Ashby) | **Hecho** |
| J | Asistente de CV por aviso con la Gemini API (opt-in, manual) + importación/exportación Word con plantilla propia | **Hecho** |
| 2 | Conectores AR: Bumeran, Zonajobs, Clarín | Casi: falta Clarín (sitio caído) |
| 3 | UI completa: filtros, detalle, estados, exportación | Casi: falta exportación |
| 4 | Actualización programable, badge, bandeja, `.exe` | Pendiente |
| 5 | Extras: claves Adzuna/Careerjet, Ollama local como alternativa | Opcional |

MVP usable (fases 0–3): ~7 días de trabajo efectivo.

---

## 13. Riesgos

| Riesgo | Mitigación |
|---|---|
| Cambio de HTML en un portal | conectores aislados y apagables |
| Rate limit / bloqueo | caché, backoff, límites por fuente |
| Bumeran/Zonajobs lentos | async + timeout propio |
| Duplicados | fingerprint + similitud + agrupación |
| Falsos positivos | gate de exclusión por título |
| Exceso de avisos | umbral configurable + vista "Hoy" acotada |
| LinkedIn ToS / bloqueo IP | conector apagado por defecto |

---

## 14. Métricas de éxito

- % de avisos abiertos sobre mostrados.
- Tiempo diario de búsqueda (<15 min).
- Entrevistas originadas desde la app.
- Rendimiento por fuente (para apagar las que no aportan).

---

## 15. Claves API gratuitas

| API | Dónde | Cobertura |
|---|---|---|
| Jooble | `ar.jooble.org/api/about` (clave por país; llega por mail) | Argentina (la clave de `jooble.org` es solo EE. UU.) |
| Gemini API | `aistudio.google.com/apikey` (gratis, sin tarjeta) | Asistente de CV. Nivel gratuito: Flash/Flash-Lite. No confundir con la suscripción Google AI Plus, que no incluye API |
| Careerjet | `careerjet.com/partners/register/as-publisher` (cuenta de publisher; clave por sitio) | Argentina (`es_AR`). API v4 con Basic auth y requiere `user_ip`, `user_agent` y `Referer`; devuelve extracto corto (~120 caracteres) |
| Adzuna | `developer.adzuna.com` (app_id + app_key inmediatos) | España, México, Brasil (no Argentina) |
| GetOnBoard | `getonbrd.com/api` (token por contacto) | Tech Latam (el HTML ya funciona sin token) |

---

## 16. Notas

- El conector de LinkedIn queda implementado pero **desactivado** y con advertencia
  visible; se puede prender solo si el usuario lo decide. Consulta la búsqueda
  pública sin login y no reutiliza cookies de sesión.
- Sin login no hay riesgo de bloqueo de cuenta; el riesgo real es de IP
  (429/999, CAPTCHA). Ver análisis en la conversación.
- La limpieza usa 30 días de retención, corre al final de cada ingesta y se
  puede lanzar a mano desde Configuración. Protege guardados, postulados,
  avisos con nota y avisos con feedback; después recalcula duplicados.
- El registro de escaneos se guarda en `run_logs` (14 días o 3000 filas) y se
  muestra en la UI con filtro de errores. No reemplaza los logs de consola:
  es un diagnóstico rápido para ver qué fuente falló y por qué.
- Indeed queda **descartado**: búsqueda HTML, RSS y versión móvil responden 403
  con desafío/bloqueo de Cloudflare (`cf-mitigated: challenge`). Su API pública
  de búsqueda está retirada y el ToS prohíbe bots/scrapers sin permiso escrito.
  No se usa la API privada de la app móvil ni se resuelven captchas.
- **Empresas (ATS)** usa solo APIs JSON públicas de Lever, Greenhouse y Ashby,
  sin claves ni scraping de HTML. La lista de boards está en
  `backend/config.py` (`ATS_EMPRESAS`) y se edita sin tocar el conector.
  Filtra zona (Argentina, remoto LatAm o global), roles IT/afines y descarta
  avisos de más de 30 días antes de guardarlos, porque la limpieza los borraría
  igual. Un board caído no corta la fuente: se consulta cada empresa por
  separado y el error queda en `run_logs`.
- SmartRecruiters y Workable se probaron pero no se integraron: los tokens
  encontrados no tenían avisos argentinos útiles (solo Brubank con 1 aviso).
- El aporte de Empresas (ATS) es complementario y de bajo volumen: tras el
  filtro de 30 días quedan ~18 avisos vigentes, en su mayoría senior. La
  ventaja es la calidad del dato (descripción completa, fecha y URL oficiales)
  y que no depende de portales generalistas.
- **Jooble** exige una clave por país: la que se pide en `jooble.org` solo
  devuelve avisos de **EE. UU.** (verificado: `location: "Argentina"` da 0) y
  en `ar.jooble.org` responde 403 porque la clave no es de ese dominio. La
  clave argentina se pidió en `https://ar.jooble.org/api/about` y vive en
  `.env` (`JOOBLE_API_KEY`); el conector está en
  `backend/connectors/jooble.py`. El plan gratuito tiene **500 consultas en
  total por clave**, así que agrupa los términos en dos consultas y usa una
  sola página de hasta 100 avisos (`ResultOnPage`). La API entrega resumen
  corto, no descripción completa: el aviso se abre en Jooble.
- Resultado de Jooble en la primera corrida (2026-11-10): 2224 avisos para la
  consulta agrupada, **154 ingeridos** (el resto cayó por antigüedad, zona o
  rol), 10 duplicados de otros portales, 8 junior y 14 semi-senior. Es la
  fuente que más avisos junior aporta después de los portales generalistas.
- La clave de Jooble nunca se escribe en el código: `backend/config.py` carga
  el `.env` local con un lector propio (sin dependencias) y las variables del
  entorno tienen prioridad.
