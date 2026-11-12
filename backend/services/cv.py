# -*- coding: utf-8 -*-
"""Asistente de CV: adapta el CV base a un aviso usando la Gemini API.

La clave se lee de ``GEMINI_API_KEY`` (``.env``) y nunca se escribe en el
código ni en la base. El CV base vive en SQLite, en este equipo; solo se envía
a Google cuando la persona pide una adaptación.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone

import httpx

from ..config import (
    GEMINI_API_KEY,
    GEMINI_BASE_URL,
    GEMINI_MODELO,
    GEMINI_TIMEOUT,
)
from ..db import conexion
from . import cv_docx

MAX_DESCRIPCION = 14000
CLAVE_MODELO = "gemini_modelo"


class CvError(Exception):
    """Error con un mensaje listo para mostrar en la interfaz."""


class ModeloNoDisponible(CvError):
    """El modelo configurado ya no existe para esta clave."""


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------- documentos
def obtener_documento(profile_id: str = "") -> dict | None:
    with conexion() as conn:
        fila = conn.execute(
            "SELECT profile_id, contenido, actualizado_at FROM cv_documentos "
            "WHERE profile_id = ? AND contenido <> ''",
            (profile_id,),
        ).fetchone()
    return dict(fila) if fila else None


def guardar_documento(contenido: str, profile_id: str = "") -> dict:
    texto = contenido.strip()
    if len(texto) < 80:
        raise CvError("El CV es demasiado corto: pegá al menos tus datos, experiencia y skills.")
    if len(texto) > 60000:
        raise CvError("El CV supera los 60.000 caracteres; recortalo antes de guardarlo.")
    momento = _ahora()
    with conexion() as conn:
        conn.execute(
            """
            INSERT INTO cv_documentos (profile_id, contenido, actualizado_at)
            VALUES (?, ?, ?)
            ON CONFLICT(profile_id) DO UPDATE SET
                contenido = excluded.contenido,
                actualizado_at = excluded.actualizado_at
            """,
            (profile_id, texto, momento),
        )
    return {"profile_id": profile_id, "contenido": texto, "actualizado_at": momento}


# --------------------------------------------------------------- plantilla Word
def obtener_plantilla(profile_id: str = "") -> dict | None:
    with conexion() as conn:
        fila = conn.execute(
            "SELECT plantilla, plantilla_nombre, plantilla_at FROM cv_documentos "
            "WHERE profile_id = ? AND plantilla IS NOT NULL",
            (profile_id,),
        ).fetchone()
    if not fila or not fila["plantilla"]:
        return None
    return {
        "contenido": bytes(fila["plantilla"]),
        "nombre": fila["plantilla_nombre"] or "plantilla.docx",
        "actualizado_at": fila["plantilla_at"] or "",
    }


def importar_plantilla(nombre: str, contenido: bytes, profile_id: str = "") -> dict:
    """Guarda el .docx como plantilla y devuelve su texto para revisar."""
    nombre_limpio = re.split(r"[\\/]", (nombre or "").strip())[-1][:120]
    if not nombre_limpio:
        nombre_limpio = "plantilla.docx"
    if not nombre_limpio.lower().endswith(".docx"):
        raise CvError("Subí un archivo .docx (Word). El .doc viejo no se puede leer.")
    try:
        texto = cv_docx.extraer_texto(contenido)
    except cv_docx.PlantillaError as exc:
        raise CvError(str(exc)) from exc
    momento = _ahora()
    with conexion() as conn:
        conn.execute(
            """
            INSERT INTO cv_documentos
                (profile_id, contenido, actualizado_at,
                 plantilla, plantilla_nombre, plantilla_at)
            VALUES (?, '', ?, ?, ?, ?)
            ON CONFLICT(profile_id) DO UPDATE SET
                plantilla = excluded.plantilla,
                plantilla_nombre = excluded.plantilla_nombre,
                plantilla_at = excluded.plantilla_at
            """,
            (profile_id, momento, contenido, nombre_limpio, momento),
        )
    return {
        "nombre": nombre_limpio,
        "contenido": texto,
        "actualizado_at": momento,
    }


# --------------------------------------------------------------- estado
def _modelo_guardado() -> str:
    with conexion() as conn:
        fila = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (CLAVE_MODELO,)
        ).fetchone()
    return (fila["value"] or "") if fila else ""


def _guardar_modelo(nombre: str) -> None:
    with conexion() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (CLAVE_MODELO, nombre),
        )


def estado() -> dict:
    doc = obtener_documento("")
    plantilla = obtener_plantilla("")
    return {
        "configurado": bool(GEMINI_API_KEY),
        "modelo": GEMINI_MODELO or _modelo_guardado() or None,
        "cv": doc,
        "plantilla": (
            {"nombre": plantilla["nombre"], "actualizado_at": plantilla["actualizado_at"]}
            if plantilla
            else None
        ),
        "limite_caracteres": 60000,
    }


# --------------------------------------------------------------- modelos
def _version(nombre: str) -> tuple[int, ...]:
    numeros = re.findall(r"\d+", nombre)
    return tuple(int(n) for n in numeros[:3])


def _puntaje_modelo(nombre: str) -> tuple:
    """Prefiere Flash-Lite (nivel gratuito) y descarta previews."""
    if "flash-lite" in nombre:
        familia = 0
    elif "flash" in nombre:
        familia = 1
    elif "pro" in nombre:
        familia = 2
    else:
        familia = 3
    inestable = 1 if ("preview" in nombre or "exp" in nombre) else 0
    return (familia, inestable, tuple(-n for n in _version(nombre)), nombre)


async def listar_modelos() -> list[str]:
    if not GEMINI_API_KEY:
        raise CvError(
            "Falta GEMINI_API_KEY en el archivo .env. Se obtiene gratis en "
            "https://aistudio.google.com/apikey"
        )
    try:
        async with httpx.AsyncClient(timeout=30) as cliente:
            respuesta = await cliente.get(
                f"{GEMINI_BASE_URL}/models",
                headers={"x-goog-api-key": GEMINI_API_KEY},
                params={"pageSize": 200},
            )
    except httpx.HTTPError as exc:
        raise CvError(f"No se pudo conectar con Gemini: {exc}") from exc

    if respuesta.status_code in (400, 403):
        raise CvError("La clave GEMINI_API_KEY no es válida o fue revocada.")
    if respuesta.status_code != 200:
        raise CvError(f"Gemini respondió HTTP {respuesta.status_code} al listar modelos.")

    datos = respuesta.json()
    utiles: list[str] = []
    for modelo in datos.get("models", []):
        metodos = modelo.get("supportedGenerationMethods") or []
        if "generateContent" not in metodos:
            continue
        nombre = str(modelo.get("name", "")).removeprefix("models/")
        if not nombre.startswith("gemini"):
            continue
        if any(x in nombre for x in ("image", "tts", "embedding", "live", "audio")):
            continue
        utiles.append(nombre)
    return sorted(set(utiles), key=_puntaje_modelo)


async def elegir_modelo() -> str:
    if GEMINI_MODELO:
        return GEMINI_MODELO
    guardado = _modelo_guardado()
    if guardado:
        return guardado
    modelos = await listar_modelos()
    if not modelos:
        raise CvError("La clave no tiene modelos de texto disponibles.")
    _guardar_modelo(modelos[0])
    return modelos[0]


# --------------------------------------------------------------- adaptación
SISTEMA = """Sos un asistente que adapta currículums vitae a un aviso de empleo \
concreto. Trabajás en español rioplatense neutro, sin inventar nada.

Reglas obligatorias:
- No inventes experiencia, empresas, títulos, fechas, certificaciones ni \
tecnologías. Solo podés reformular, reordenar, resumir y destacar lo que ya \
existe en el CV.
- Si el aviso pide algo que no está en el CV, no lo agregues: listalo en \
"faltantes".
- Conservá los datos de contacto tal como están.
- El resultado debe ser texto plano con secciones y viñetas simples, sin \
markdown complejo ni tablas.
- Extensión objetivo: dos páginas como máximo.
- Si el aviso está en inglés, escribí el CV en inglés.
- En "cambios" explicá en frases cortas qué reordenaste o reformulaste y por qué."""

ESQUEMA_RESPUESTA = {
    "type": "object",
    "properties": {
        "cv": {"type": "string"},
        "resumen": {"type": "string"},
        "cambios": {"type": "array", "items": {"type": "string"}},
        "faltantes": {"type": "array", "items": {"type": "string"}},
        "perfil": {"type": "string"},
        "experiencia": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["titulo", "bullets"],
            },
        },
        "educacion": {"type": "array", "items": {"type": "string"}},
        "habilidades": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "etiqueta": {"type": "string"},
                    "items": {"type": "string"},
                },
                "required": ["etiqueta", "items"],
            },
        },
        "idiomas": {"type": "array", "items": {"type": "string"}},
        "otras": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "lineas": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["titulo", "lineas"],
            },
        },
    },
    "required": [
        "cv",
        "resumen",
        "cambios",
        "faltantes",
        "perfil",
        "experiencia",
        "educacion",
        "habilidades",
        "idiomas",
        "otras",
    ],
}


def _prompt(cv: str, job: dict) -> str:
    descripcion = (job.get("description") or "").strip()[:MAX_DESCRIPCION]
    return f"""Adaptá el CV de la persona al siguiente aviso.

## Aviso
Puesto: {job.get("title") or "sin título"}
Empresa: {job.get("company_name") or "no informada"}
Ubicación: {job.get("location") or "no informada"}
Modalidad: {job.get("modality") or "no informada"}
Seniority: {job.get("seniority") or "no informado"}
Idioma del aviso: {"inglés" if job.get("language") == "en" else "español"}

Descripción:
{descripcion or "(sin descripción disponible)"}

## CV base
{cv}

## Formato de salida
Devolvé un objeto JSON con:
- "cv": el CV completo adaptado, en texto plano.
- "resumen": dos o tres líneas sobre por qué encaja y qué se destacó.
- "cambios": lista de cambios concretos que hiciste.
- "faltantes": requisitos del aviso que no aparecen en el CV y que la persona \
debería cubrir o aclarar.
- "perfil": el párrafo de perfil adaptado, sin el título de la sección.
- "experiencia": lista de puestos. En "titulo" copiá exactamente la línea de \
puesto, empresa y fechas del CV base; en "bullets" poné las viñetas reformuladas.
- "educacion": lista de líneas de educación, copiadas del CV base.
- "habilidades": lista de categorías con "etiqueta" (por ejemplo "Back-End") e \
"items" (tecnologías separadas por coma). Usá solo tecnologías que ya estén en \
el CV; podés reordenarlas o agruparlas.
- "idiomas": lista de líneas de idiomas, si el CV las tiene.
- "otras": solo si el CV tiene otra sección (certificaciones, proyectos, \
publicaciones). Incluí "titulo" y "lineas".

Los campos estructurados deben contener la misma información que "cv": nada \
nuevo. Si una sección no existe en el CV base, devolvé una lista vacía o una \
cadena vacía, según corresponda.
"""


def _extraer_texto(datos: dict) -> str:
    candidatos = datos.get("candidates") or []
    if not candidatos:
        bloqueo = (datos.get("promptFeedback") or {}).get("blockReason")
        if bloqueo:
            raise CvError(f"Gemini bloqueó la solicitud ({bloqueo}).")
        raise CvError("Gemini no devolvió ninguna respuesta.")
    partes = (candidatos[0].get("content") or {}).get("parts") or []
    texto = "".join(p.get("text", "") for p in partes).strip()
    if not texto:
        razon = candidatos[0].get("finishReason")
        raise CvError(f"Gemini devolvió una respuesta vacía ({razon or 'sin motivo'}).")
    return texto


def _lista_textos(valor) -> list[str]:
    return [str(item).strip() for item in valor or [] if str(item).strip()]


def _parsear_json(texto: str) -> dict:
    limpio = texto.strip()
    if limpio.startswith("```"):
        limpio = re.sub(r"^```(?:json)?\s*", "", limpio)
        limpio = re.sub(r"\s*```$", "", limpio)
    try:
        datos = json.loads(limpio)
    except json.JSONDecodeError as exc:
        raise CvError("Gemini devolvió un formato inesperado; probá de nuevo.") from exc
    if not isinstance(datos, dict) or not str(datos.get("cv", "")).strip():
        raise CvError("La respuesta no incluyó el CV adaptado; probá de nuevo.")

    experiencia = []
    for entrada in datos.get("experiencia") or []:
        if not isinstance(entrada, dict):
            continue
        titulo = str(entrada.get("titulo") or "").strip()
        if titulo:
            experiencia.append(
                {"titulo": titulo, "bullets": _lista_textos(entrada.get("bullets"))}
            )

    habilidades = []
    for item in datos.get("habilidades") or []:
        if not isinstance(item, dict):
            continue
        etiqueta = str(item.get("etiqueta") or "").strip()
        items = str(item.get("items") or "").strip()
        if etiqueta or items:
            habilidades.append({"etiqueta": etiqueta, "items": items})

    otras = []
    for bloque in datos.get("otras") or []:
        if not isinstance(bloque, dict):
            continue
        titulo = str(bloque.get("titulo") or "").strip()
        lineas = _lista_textos(bloque.get("lineas"))
        if titulo and lineas:
            otras.append({"titulo": titulo, "lineas": lineas})

    return {
        "cv": str(datos.get("cv", "")).strip(),
        "resumen": str(datos.get("resumen", "")).strip(),
        "cambios": _lista_textos(datos.get("cambios")),
        "faltantes": _lista_textos(datos.get("faltantes")),
        "perfil": str(datos.get("perfil", "")).strip(),
        "experiencia": experiencia,
        "educacion": _lista_textos(datos.get("educacion")),
        "habilidades": habilidades,
        "idiomas": _lista_textos(datos.get("idiomas")),
        "otras": otras,
    }


async def _generar(modelo: str, prompt: str) -> str:
    cuerpo = {
        "systemInstruction": {"parts": [{"text": SISTEMA}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "responseMimeType": "application/json",
            "responseSchema": ESQUEMA_RESPUESTA,
        },
    }
    try:
        async with httpx.AsyncClient(timeout=GEMINI_TIMEOUT) as cliente:
            respuesta = await cliente.post(
                f"{GEMINI_BASE_URL}/models/{modelo}:generateContent",
                headers={"x-goog-api-key": GEMINI_API_KEY},
                json=cuerpo,
            )
    except httpx.TimeoutException as exc:
        raise CvError("Gemini tardó demasiado; probá de nuevo en un rato.") from exc
    except httpx.HTTPError as exc:
        raise CvError(f"No se pudo conectar con Gemini: {exc}") from exc

    if respuesta.status_code == 429:
        raise CvError(
            "Se agotó el cupo gratuito de Gemini por ahora. Esperá unos minutos "
            "o probá mañana; el límite se reinicia a medianoche del Pacífico."
        )
    if respuesta.status_code in (400, 403):
        raise CvError(
            "Gemini rechazó la solicitud: revisá que GEMINI_API_KEY sea válida "
            "y que el modelo elegido esté disponible para tu cuenta."
        )
    if respuesta.status_code == 404:
        raise ModeloNoDisponible(
            f"El modelo «{modelo}» no está disponible para esta clave. "
            "Borrá GEMINI_MODELO del .env para que la app elija uno automáticamente."
        )
    if respuesta.status_code != 200:
        detalle = ""
        try:
            detalle = (respuesta.json().get("error") or {}).get("message", "")
        except ValueError:
            detalle = respuesta.text[:200]
        raise CvError(f"Gemini respondió HTTP {respuesta.status_code}. {detalle}".strip())

    return _extraer_texto(respuesta.json())


async def adaptar(job_id: int, profile_id: str = "") -> dict:
    if not GEMINI_API_KEY:
        raise CvError(
            "Falta GEMINI_API_KEY en el archivo .env. Se obtiene gratis en "
            "https://aistudio.google.com/apikey"
        )
    documento = obtener_documento(profile_id)
    if not documento:
        raise CvError("Todavía no guardaste tu CV. Cargalo en Mi CV y volvé a intentar.")

    with conexion() as conn:
        fila = conn.execute(
            """
            SELECT id, title, company_name, location, modality, seniority,
                   language, description
            FROM jobs WHERE id = ?
            """,
            (job_id,),
        ).fetchone()
    if not fila:
        raise CvError("Aviso no encontrado.")
    job = dict(fila)
    if not (job.get("description") or "").strip():
        raise CvError(
            "Este aviso no tiene descripción; abrí el original y copiala en la nota "
            "o probá con otro aviso."
        )

    modelo = await elegir_modelo()
    try:
        texto = await _generar(modelo, _prompt(documento["contenido"], job))
    except ModeloNoDisponible:
        # El modelo guardado ya no existe: se elige otro y se reintenta una vez.
        if GEMINI_MODELO:
            raise
        _guardar_modelo("")
        modelo = await elegir_modelo()
        texto = await _generar(modelo, _prompt(documento["contenido"], job))

    resultado = _parsear_json(texto)
    resultado["modelo"] = modelo
    momento = _ahora()
    with conexion() as conn:
        cursor = conn.execute(
            """
            INSERT INTO cv_adaptaciones (job_id, profile_id, modelo, resultado, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (job_id, profile_id or None, modelo, json.dumps(resultado, ensure_ascii=False), momento),
        )
        adaptacion_id = cursor.lastrowid
    return {
        "id": adaptacion_id,
        "job_id": job_id,
        "profile_id": profile_id or None,
        "modelo": modelo,
        "created_at": momento,
        **resultado,
    }


# --------------------------------------------------------------- historial
def _armar(fila) -> dict:
    base = dict(fila)
    contenido = json.loads(base.pop("resultado") or "{}")
    return {**base, **contenido}


def listar_adaptaciones(job_id: int) -> list[dict]:
    with conexion() as conn:
        filas = conn.execute(
            "SELECT id, job_id, profile_id, modelo, resultado, created_at "
            "FROM cv_adaptaciones WHERE job_id = ? ORDER BY id DESC",
            (job_id,),
        ).fetchall()
    return [_armar(f) for f in filas]


def borrar_adaptacion(adaptacion_id: int) -> int:
    with conexion() as conn:
        cursor = conn.execute("DELETE FROM cv_adaptaciones WHERE id = ?", (adaptacion_id,))
    return cursor.rowcount


# --------------------------------------------------------------- Word
def _nombre_docx(empresa: str | None, puesto: str | None) -> str:
    base = "-".join(parte for parte in (empresa, puesto) if parte) or "cv"
    base = unicodedata.normalize("NFD", base)
    base = "".join(c for c in base if unicodedata.category(c) != "Mn")
    base = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower()[:80]
    return f"cv-{base or 'adaptado'}.docx"


def _nombre_archivo(
    nombre: str | None,
    empresa: str | None,
    puesto: str | None,
) -> str:
    """Nombre elegido por la persona, sin caracteres que rompan la descarga."""
    base = (nombre or "").strip()
    if base.lower().endswith(".docx"):
        base = base[:-5]
    base = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", base)
    base = re.sub(r"\s+", " ", base).strip(" .")
    base = base[:100].strip()
    return f"{base}.docx" if base else _nombre_docx(empresa, puesto)


def generar_word(adaptacion_id: int, nombre: str | None = None) -> tuple[bytes, str]:
    """Genera el .docx adaptado usando la plantilla guardada, si existe."""
    with conexion() as conn:
        fila = conn.execute(
            """
            SELECT a.profile_id, a.resultado, j.title, j.company_name
            FROM cv_adaptaciones a
            JOIN jobs j ON j.id = a.job_id
            WHERE a.id = ?
            """,
            (adaptacion_id,),
        ).fetchone()
    if not fila:
        raise CvError("Adaptación no encontrada.")

    datos = json.loads(fila["resultado"] or "{}")
    plantilla = obtener_plantilla(fila["profile_id"] or "")
    try:
        contenido = cv_docx.generar_docx(
            plantilla["contenido"] if plantilla else None,
            datos,
            datos.get("cv", ""),
        )
    except cv_docx.PlantillaError as exc:
        raise CvError(f"No se pudo usar la plantilla Word: {exc}") from exc
    return contenido, _nombre_archivo(nombre, fila["company_name"], fila["title"])
