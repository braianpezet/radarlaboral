# -*- coding: utf-8 -*-
"""Radar Laboral — API local."""
from __future__ import annotations

import asyncio
import re
import sqlite3
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_DIST
from .connectors import crear_conector
from .db import conexion, init_db
from .schemas import CvAdaptar, CvUpdate, FeedbackCreate, JobUpdate, SourceUpdate
from .services import ingest
from .services.dedupe import deduplicar
from .services.scoring import puntuar_todos, puntuar_uno
from .services import cv, feedback, limpieza, logs, sesiones
from .services.text import (
    detectar_idioma,
    detectar_modalidad,
    detectar_seniority,
    hash_contenido,
    limpiar_descripcion,
)

VERSION = "0.16.0"
_tarea_actual: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with conexion() as conn:
        faltan = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE score IS NULL"
        ).fetchone()[0]
    if faltan:
        puntuar_todos()
        deduplicar()
    yield


app = FastAPI(title="Radar Laboral", version=VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- utils
def _consulta_fts(texto: str) -> str | None:
    terminos = [t for t in re.findall(r"\w+", texto, flags=re.UNICODE) if len(t) >= 2]
    if not terminos:
        return None
    return " AND ".join(f'"{t}"*' for t in terminos)


MODALIDADES = {"remoto", "hibrido", "presencial"}
SENIORITIES = {"trainee", "junior", "semi-senior", "senior"}
IDIOMAS = {"es", "en"}

ORDENES = {
    ("score", "desc"): "j.score IS NULL, j.score DESC, j.published_at DESC, j.id DESC",
    ("score", "asc"): "j.score IS NULL, j.score ASC, j.published_at DESC, j.id DESC",
    ("date", "desc"): "j.published_at IS NULL, j.published_at DESC, j.score DESC, j.id DESC",
    ("date", "asc"): "j.published_at IS NULL, j.published_at ASC, j.score DESC, j.id DESC",
}


def _where(
    q: str,
    source: str,
    status: str,
    view: str = "",
    profile: str = "",
    modality: str = "",
    seniority: str = "",
    language: str = "",
    min_score: int | None = None,
) -> tuple[str, list]:
    # Los duplicados y los avisos fuera de perfil no se muestran en la lista.
    condiciones: list[str] = ["j.duplicate_of IS NULL", "j.excluded = 0"]
    params: list = []
    if view == "hoy":
        condiciones.append("j.score >= 70")
    if profile:
        condiciones.append("j.profile_id = ?")
        params.append(profile)
    if status:
        condiciones.append("j.status = ?")
        params.append(status)
    if source:
        condiciones.append("j.source_id = ?")
        params.append(source)
    if modality in MODALIDADES:
        condiciones.append("j.modality = ?")
        params.append(modality)
    if seniority in SENIORITIES:
        condiciones.append("j.seniority = ?")
        params.append(seniority)
    if language in IDIOMAS:
        condiciones.append("j.language = ?")
        params.append(language)
    if min_score is not None:
        condiciones.append("j.score >= ?")
        params.append(min_score)
    return " AND ".join(condiciones), params


def _serializar_job(fila: sqlite3.Row) -> dict:
    data = dict(fila)
    data.pop("content_hash", None)
    return data


# --------------------------------------------------------------------------- API
@app.get("/api/health")
def health():
    return {"ok": True, "version": VERSION}


@app.get("/api/sources")
def listar_fuentes():
    with conexion() as conn:
        filas = conn.execute(
            """
            SELECT s.*,
                   COUNT(j.id) AS job_count,
                   SUM(CASE WHEN j.duplicate_of IS NULL AND j.excluded = 0
                            THEN 1 ELSE 0 END) AS visible_count
            FROM sources s
            LEFT JOIN jobs j ON j.source_id = s.id
            GROUP BY s.id
            ORDER BY s.enabled DESC, s.name
            """
        ).fetchall()
    return [dict(f) for f in filas]


@app.patch("/api/sources/{source_id}")
def actualizar_fuente(source_id: str, datos: SourceUpdate):
    """Activa o desactiva una fuente para las próximas actualizaciones."""
    with conexion() as conn:
        fila = conn.execute("SELECT id FROM sources WHERE id = ?", (source_id,)).fetchone()
        if not fila:
            raise HTTPException(status_code=404, detail="Fuente no encontrada")
        conn.execute(
            "UPDATE sources SET enabled = ? WHERE id = ?",
            (1 if datos.enabled else 0, source_id),
        )
        actualizada = conn.execute(
            """
            SELECT s.*,
                   COUNT(j.id) AS job_count,
                   SUM(CASE WHEN j.duplicate_of IS NULL AND j.excluded = 0
                            THEN 1 ELSE 0 END) AS visible_count
            FROM sources s
            LEFT JOIN jobs j ON j.source_id = s.id
            WHERE s.id = ?
            GROUP BY s.id
            """,
            (source_id,),
        ).fetchone()
    return dict(actualizada)


@app.get("/api/stats")
def estadisticas():
    with conexion() as conn:
        fila = conn.execute(
            """
            SELECT
                SUM(CASE WHEN duplicate_of IS NULL AND excluded = 0
                         THEN 1 ELSE 0 END) AS total,
                SUM(CASE WHEN status = 'nuevo' AND duplicate_of IS NULL AND excluded = 0
                         THEN 1 ELSE 0 END) AS nuevos,
                SUM(CASE WHEN status = 'guardado'   THEN 1 ELSE 0 END) AS guardados,
                SUM(CASE WHEN status = 'postulado'  THEN 1 ELSE 0 END) AS postulados,
                SUM(CASE WHEN status = 'descartado' THEN 1 ELSE 0 END) AS descartados,
                SUM(CASE WHEN duplicate_of IS NULL AND excluded = 0 AND score >= 70
                         THEN 1 ELSE 0 END) AS hoy,
                SUM(CASE WHEN duplicate_of IS NOT NULL THEN 1 ELSE 0 END) AS duplicados,
                SUM(CASE WHEN excluded = 1 THEN 1 ELSE 0 END) AS excluidos,
                (SELECT COUNT(DISTINCT job_id) FROM feedback) AS valorados
            FROM jobs
            """
        ).fetchone()
        fuentes = conn.execute(
            "SELECT COUNT(*) AS n FROM sources WHERE enabled = 1"
        ).fetchone()["n"]
        ultima = conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT 1"
        ).fetchone()

    datos = dict(fila)
    for clave in (
        "total",
        "nuevos",
        "guardados",
        "postulados",
        "descartados",
        "hoy",
        "duplicados",
        "excluidos",
        "valorados",
    ):
        datos[clave] = datos[clave] or 0
    datos["fuentes_activas"] = fuentes
    datos["ultima"] = dict(ultima) if ultima else None
    return datos


@app.get("/api/profiles")
def listar_perfiles():
    with conexion() as conn:
        filas = conn.execute(
            """
            SELECT p.id, p.name, p.priority,
                   COUNT(j.id) AS job_count,
                   SUM(CASE WHEN j.duplicate_of IS NULL AND j.excluded = 0
                            THEN 1 ELSE 0 END) AS visible_count,
                   SUM(CASE WHEN j.duplicate_of IS NULL AND j.excluded = 0
                                 AND j.score >= 70
                            THEN 1 ELSE 0 END) AS hoy_count
            FROM profiles p
            LEFT JOIN jobs j ON j.profile_id = p.id
            WHERE p.enabled = 1
            GROUP BY p.id
            ORDER BY p.priority
            """
        ).fetchall()
    return [dict(f) for f in filas]


@app.get("/api/jobs")
def listar_jobs(
    q: str = "",
    source: str = "",
    status: str = "",
    view: str = "",
    profile: str = "",
    modality: str = "",
    seniority: str = "",
    language: str = "",
    min_score: int | None = None,
    sort: str = "score",
    order: str = "desc",
    limit: int = 100,
    offset: int = 0,
):
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    if min_score is not None:
        min_score = max(0, min(min_score, 100))
    if sort not in {"score", "date"}:
        sort = "score"
    if order not in {"asc", "desc"}:
        order = "desc"
    where, params = _where(
        q, source, status, view, profile, modality, seniority, language, min_score
    )
    fts = _consulta_fts(q) if q else None

    base = (
        "FROM jobs j JOIN sources s ON s.id = j.source_id "
        "LEFT JOIN profiles p ON p.id = j.profile_id"
    )
    if fts:
        base += " JOIN jobs_fts f ON f.rowid = j.id"
        where = (where + " AND " if where else "") + "f MATCH ?"
        params = params + [fts]

    seleccion = """
        SELECT j.id, j.title, j.company_name, j.location, j.modality, j.seniority,
               j.language, j.salary_text, j.published_at, j.fetched_at,
               j.source_id, j.url, j.status, j.note,
               j.score, j.profile_id, j.excluded, j.duplicate_of,
               s.name AS source_name,
               p.name AS profile_name,
               CASE WHEN j.description IS NOT NULL AND length(j.description) > 0
                    THEN 1 ELSE 0 END AS has_description,
               j.fingerprint
    """
    orden = " ORDER BY " + ORDENES[(sort, order)]

    try:
        with conexion() as conn:
            total = conn.execute(f"SELECT COUNT(*) {base}" + (f" WHERE {where}" if where else ""), params).fetchone()[0]
            filas = conn.execute(
                seleccion + base + (f" WHERE {where}" if where else "") + orden + " LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
    except sqlite3.OperationalError:
        # Si la consulta FTS falla, se cae a búsqueda simple por LIKE.
        where, params = _where(
            "", source, status, view, profile, modality, seniority, language, min_score
        )
        if q:
            cond = "(j.title LIKE ? OR j.company_name LIKE ? OR j.description LIKE ?)"
            where = (where + " AND " if where else "") + cond
            patron = f"%{q}%"
            params = params + [patron, patron, patron]
        with conexion() as conn:
            total = conn.execute(f"SELECT COUNT(*) {base}" + (f" WHERE {where}" if where else ""), params).fetchone()[0]
            filas = conn.execute(
                seleccion + base + (f" WHERE {where}" if where else "") + orden + " LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()

    votos = feedback.votos_actuales([fila["id"] for fila in filas])
    items = []
    for fila in filas:
        data = _serializar_job(fila)
        voto = votos.get(data["id"])
        data["feedback_vote"] = voto["vote"] if voto else None
        data["feedback_motivos"] = voto["motivos"] if voto else []
        items.append(data)
    return {"total": total, "items": items}


@app.get("/api/jobs/{job_id}")
async def obtener_job(job_id: int):
    with conexion() as conn:
        fila = conn.execute(
            """
            SELECT j.*, s.name AS source_name, p.name AS profile_name,
                   CASE WHEN j.description IS NOT NULL AND length(j.description) > 0
                        THEN 1 ELSE 0 END AS has_description
            FROM jobs j
            JOIN sources s ON s.id = j.source_id
            LEFT JOIN profiles p ON p.id = j.profile_id
            WHERE j.id = ?
            """,
            (job_id,),
        ).fetchone()
    if not fila:
        raise HTTPException(status_code=404, detail="Aviso no encontrado")

    data = _serializar_job(fila)

    if not data.get("description"):
        conector = crear_conector(data["source_id"])
        if conector is not None:
            try:
                async with conector.cliente() as client:
                    descripcion, contrato = await conector.detalle(client, data["url"])
                descripcion = limpiar_descripcion(descripcion)
                if descripcion:
                    _guardar_detalle(job_id, data["title"], descripcion, contrato)
                    with conexion() as conn:
                        fila = conn.execute(
                            """
                            SELECT j.*, s.name AS source_name, p.name AS profile_name,
                                   CASE WHEN j.description IS NOT NULL
                                             AND length(j.description) > 0
                                        THEN 1 ELSE 0 END AS has_description
                            FROM jobs j
                            JOIN sources s ON s.id = j.source_id
                            LEFT JOIN profiles p ON p.id = j.profile_id
                            WHERE j.id = ?
                            """,
                            (job_id,),
                        ).fetchone()
                    data = _serializar_job(fila)
            except Exception as exc:
                data["detail_error"] = f"No se pudo cargar la descripción: {exc}"

    voto = feedback.voto_de(job_id)
    data["feedback_vote"] = voto["vote"] if voto else None
    data["feedback_motivos"] = voto["motivos"] if voto else []
    return data


def _guardar_detalle(job_id: int, titulo: str, descripcion: str, contrato: str | None) -> None:
    texto = f"{titulo}\n{descripcion}"
    modalidad = detectar_modalidad(titulo) or detectar_modalidad(descripcion)
    with conexion() as conn:
        conn.execute(
            """
            UPDATE jobs SET
                description   = ?,
                contract_type = COALESCE(?, contract_type),
                language      = ?,
                modality      = COALESCE(?, modality),
                seniority     = COALESCE(?, seniority),
                content_hash  = ?
            WHERE id = ?
            """,
            (
                descripcion,
                contrato,
                detectar_idioma(texto),
                modalidad,
                detectar_seniority(texto),
                hash_contenido(descripcion),
                job_id,
            ),
        )
    # La descripción nueva puede cambiar el encaje con los perfiles.
    puntuar_uno(job_id)


@app.patch("/api/jobs/{job_id}")
def actualizar_job(job_id: int, cambios: JobUpdate):
    campos: dict = {}
    if cambios.status is not None:
        campos["status"] = cambios.status
        campos["status_updated_at"] = ingest.iso(ingest.ahora_utc())
    if cambios.note is not None:
        campos["note"] = cambios.note.strip() or None

    if not campos:
        raise HTTPException(status_code=400, detail="No hay cambios para aplicar")

    sets = ", ".join(f"{k} = ?" for k in campos)
    with conexion() as conn:
        cur = conn.execute(
            f"UPDATE jobs SET {sets} WHERE id = ?", (*campos.values(), job_id)
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Aviso no encontrado")
        fila = conn.execute(
            "SELECT id, status, note, status_updated_at FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
    return dict(fila)


@app.post("/api/feedback")
def registrar_feedback(datos: FeedbackCreate):
    """Guarda la valoración explícita de un aviso."""
    try:
        return feedback.registrar(datos.job_id, datos.vote, datos.motivos)
    except feedback.AvisoNoEncontrado:
        raise HTTPException(status_code=404, detail="Aviso no encontrado")


@app.delete("/api/feedback/{job_id}")
def borrar_feedback(job_id: int):
    return {"eliminados": feedback.borrar(job_id)}


@app.get("/api/feedback/summary")
def resumen_feedback():
    """Votos y etiquetas disponibles para el futuro aprendizaje del ranking."""
    return feedback.resumen()


# --------------------------------------------------------------------------- CV
@app.get("/api/cv")
def estado_cv():
    """CV base guardado y estado de la clave de Gemini."""
    return cv.estado()


@app.post("/api/cv/plantilla")
async def importar_plantilla_cv(request: Request, nombre: str = ""):
    """Guarda el .docx como plantilla y devuelve su texto para revisar."""
    contenido = await request.body()
    try:
        return cv.importar_plantilla(nombre, contenido)
    except cv.CvError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/cv/adaptaciones/{adaptacion_id}/docx")
def descargar_cv_word(adaptacion_id: int, nombre: str = ""):
    """Genera el Word adaptado con la plantilla cargada (o una limpia)."""
    try:
        contenido, nombre_archivo = cv.generar_word(adaptacion_id, nombre or None)
    except cv.CvError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    ascii_nombre = (
        nombre_archivo.encode("ascii", "ignore").decode().strip() or "cv-adaptado.docx"
    )
    return Response(
        content=contenido,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_nombre}"; '
                f"filename*=UTF-8''{quote(nombre_archivo)}"
            )
        },
    )


@app.put("/api/cv")
def guardar_cv(datos: CvUpdate):
    try:
        return cv.guardar_documento(datos.contenido, datos.profile_id)
    except cv.CvError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/cv/adaptar")
async def adaptar_cv(datos: CvAdaptar):
    """Genera un CV adaptado al aviso. Requiere GEMINI_API_KEY en .env."""
    try:
        return await cv.adaptar(datos.job_id, datos.profile_id)
    except cv.CvError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/jobs/{job_id}/cv")
def listar_adaptaciones_cv(job_id: int):
    return cv.listar_adaptaciones(job_id)


@app.delete("/api/cv/adaptaciones/{adaptacion_id}")
def borrar_adaptacion_cv(adaptacion_id: int):
    if not cv.borrar_adaptacion(adaptacion_id):
        raise HTTPException(status_code=404, detail="Adaptación no encontrada")
    return {"eliminados": 1}


@app.get("/api/cleanup/preview")
def previsualizar_limpieza(dias: int = 30):
    """Cuenta los avisos antiguos que se eliminarían."""
    return limpieza.previsualizar(dias)


@app.post("/api/cleanup")
def limpiar_avisos(dias: int = 30):
    """Elimina avisos antiguos sin señales del usuario y recalcula duplicados."""
    return limpieza.limpiar(dias)


@app.post("/api/refresh")
async def actualizar_ahora():
    global _tarea_actual
    if _tarea_actual and not _tarea_actual.done():
        raise HTTPException(status_code=409, detail="Ya hay una actualización en curso")
    run_id = ingest.crear_run()
    _tarea_actual = asyncio.create_task(ingest.ejecutar_actualizacion(run_id))
    return {"run_id": run_id}


@app.get("/api/session")
def estado_sesiones():
    """Estado de las sesiones asistidas de ZonaJobs y Bumeran."""
    return sesiones.resumen()


@app.post("/api/session/{source_id}")
def abrir_sesion(source_id: str):
    """Abre la ventana del portal para que la persona valide la sesión."""
    if _tarea_actual and not _tarea_actual.done():
        raise HTTPException(
            status_code=409,
            detail="Hay una actualización en curso; esperá a que termine para abrir la sesión.",
        )
    try:
        estado = sesiones.abrir_sesion(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Fuente sin sesión asistida")
    except sesiones.SesionEnCurso as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return estado


@app.get("/api/runs/latest")
def ultima_corrida():
    with conexion() as conn:
        fila = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    return dict(fila) if fila else None


@app.get("/api/runs/{run_id}")
def obtener_run(run_id: int):
    with conexion() as conn:
        fila = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not fila:
        raise HTTPException(status_code=404, detail="Corrida no encontrada")
    return dict(fila)


@app.get("/api/logs")
def listar_logs(limit: int = 150, run_id: int | None = None):
    """Eventos de las actualizaciones, del más viejo al más nuevo."""
    return logs.listar(limit=limit, run_id=run_id)


# --------------------------------------------------------------------------- frontend
if FRONTEND_DIST.exists():
    assets = FRONTEND_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{ruta:path}")
    async def spa(ruta: str):
        if ruta.startswith("api/"):
            raise HTTPException(status_code=404, detail="No encontrado")
        archivo = FRONTEND_DIST / ruta
        if ruta and archivo.is_file():
            return FileResponse(archivo)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/")
    async def sin_frontend():
        return HTMLResponse(
            "<h1>Radar Laboral</h1>"
            "<p>Falta compilar el frontend. Ejecutá <code>npm install &amp;&amp; npm run build</code> "
            "dentro de <code>frontend/</code>.</p>"
        )
