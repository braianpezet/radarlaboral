# -*- coding: utf-8 -*-
"""Orquestación de la recolección de avisos (múltiples fuentes)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from ..config import (
    PAUSA_BLOQUEO_MINUTOS,
    PAUSA_ENTRE_BUSQUEDAS,
    PAUSA_ENTRE_FUENTES,
)
from ..connectors import crear_conector
from ..connectors.base import FuenteBloqueada, JobRaw, SesionAsistidaRequerida
from ..db import conexion
from .text import (
    ahora_utc,
    clave_zona,
    detectar_idioma,
    detectar_modalidad,
    detectar_seniority,
    huella,
    iso,
    normalizar,
    parsear_fecha,
    parsear_salario,
)
from .limpieza import limpiar
from .logs import limpiar_viejos, registrar
from .scoring import puntuar_todos
LOCK = asyncio.Lock()


def crear_run() -> int:
    with conexion() as conn:
        cur = conn.execute(
            "INSERT INTO runs (started_at, status) VALUES (?, 'running')",
            (iso(ahora_utc()),),
        )
        return int(cur.lastrowid)


def _actualizar_run(run_id: int, **campos) -> None:
    if not campos:
        return
    sets = ", ".join(f"{clave} = ?" for clave in campos)
    with conexion() as conn:
        conn.execute(f"UPDATE runs SET {sets} WHERE id = ?", (*campos.values(), run_id))


def _empresa(conn, nombre: str | None) -> int | None:
    if not nombre:
        return None
    norm = normalizar(nombre)
    if not norm:
        return None
    conn.execute(
        "INSERT OR IGNORE INTO companies (name, name_norm) VALUES (?, ?)",
        (nombre.strip(), norm),
    )
    fila = conn.execute("SELECT id FROM companies WHERE name_norm = ?", (norm,)).fetchone()
    return int(fila["id"]) if fila else None


def _guardar(conn, oferta: JobRaw, ahora) -> bool:
    """Inserta o actualiza una oferta. Devuelve True si es nueva."""
    texto = "\n".join(
        parte
        for parte in (oferta.title, oferta.summary, oferta.modality_hint, oferta.description)
        if parte
    )
    modalidad = (
        detectar_modalidad(oferta.modality_hint)
        or detectar_modalidad(oferta.title)
        or detectar_modalidad(oferta.summary)
        or detectar_modalidad(oferta.description)
    )
    salario = parsear_salario(oferta.salary_text) or {}
    fecha = parsear_fecha(oferta.published_text, ahora)
    empresa_id = _empresa(conn, oferta.company)
    fingerprint = huella(oferta.title, oferta.company, oferta.location)
    zona = clave_zona(oferta.location, modalidad)

    existente = conn.execute(
        "SELECT id FROM jobs WHERE source_id = ? AND external_id = ?",
        (oferta.source_id, oferta.external_id),
    ).fetchone()

    if existente:
        conn.execute(
            """
            UPDATE jobs SET
                title = ?, url = ?, company_id = ?, company_name = ?, location = ?,
                description   = COALESCE(?, description),
                summary       = COALESCE(?, summary),
                salary_text   = COALESCE(?, salary_text),
                salary_min    = COALESCE(?, salary_min),
                salary_max    = COALESCE(?, salary_max),
                currency      = COALESCE(?, currency),
                period        = COALESCE(?, period),
                language      = ?,
                modality      = COALESCE(?, modality),
                zone          = ?,
                seniority     = COALESCE(?, seniority),
                contract_type = COALESCE(?, contract_type),
                published_at  = COALESCE(?, published_at),
                fetched_at    = ?,
                fingerprint   = ?
            WHERE id = ?
            """,
            (
                oferta.title,
                oferta.url,
                empresa_id,
                oferta.company,
                oferta.location,
                oferta.description,
                oferta.summary,
                oferta.salary_text,
                salario.get("min"),
                salario.get("max"),
                salario.get("moneda"),
                salario.get("periodo"),
                detectar_idioma(texto),
                modalidad,
                zona,
                detectar_seniority(texto),
                oferta.contract_type,
                iso(fecha),
                iso(ahora),
                fingerprint,
                existente["id"],
            ),
        )
        return False

    # Un aviso ya visto, descartado o postulado no vuelve a entrar aunque el
    # portal lo publique con otro identificador.
    repetido = conn.execute(
        """
        SELECT 1 FROM jobs
        WHERE fingerprint = ?
          AND COALESCE(company_name, '') = COALESCE(?, '')
          AND status IN ('visto', 'descartado', 'postulado')
        LIMIT 1
        """,
        (fingerprint, oferta.company),
    ).fetchone()
    if repetido:
        return False

    conn.execute(
        """
        INSERT INTO jobs (
            source_id, external_id, url, title, company_id, company_name,
            description, summary, location, modality, zone, seniority, contract_type,
            salary_text, salary_min, salary_max, currency, period,
            language, published_at, fetched_at, fingerprint, content_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            oferta.source_id,
            oferta.external_id,
            oferta.url,
            oferta.title,
            empresa_id,
            oferta.company,
            oferta.description,
            oferta.summary,
            oferta.location,
            modalidad,
            zona,
            detectar_seniority(texto),
            oferta.contract_type,
            oferta.salary_text,
            salario.get("min"),
            salario.get("max"),
            salario.get("moneda"),
            salario.get("periodo"),
            detectar_idioma(texto),
            iso(fecha),
            iso(ahora),
            fingerprint,
            None,
        ),
    )
    return True


def _fuentes_activas() -> list[str]:
    with conexion() as conn:
        filas = conn.execute(
            "SELECT id FROM sources WHERE enabled = 1 ORDER BY id"
        ).fetchall()
    return [fila["id"] for fila in filas]


def _fuente_en_pausa(fila) -> bool:
    """True si la fuente viene de un bloqueo anti-bot reciente."""
    if not fila or not fila["last_error"] or not fila["last_run_at"]:
        return False
    if "bloqueó" not in fila["last_error"] and "WAF" not in fila["last_error"]:
        return False
    try:
        ultimo = datetime.fromisoformat(fila["last_run_at"])
    except (TypeError, ValueError):
        return False
    if ultimo.tzinfo is None:
        ultimo = ultimo.replace(tzinfo=timezone.utc)
    return ahora_utc() - ultimo < timedelta(minutes=PAUSA_BLOQUEO_MINUTOS)


async def _actualizar_fuente(conector, run_id: int, contadores: dict) -> list[str]:
    """Recorre todas las búsquedas de un conector. Devuelve mensajes de error."""
    mensajes: list[str] = []
    pausa = getattr(conector, "pausa_entre_busquedas", PAUSA_ENTRE_BUSQUEDAS)

    async with conector.cliente() as client:
        for consulta in conector.busquedas:
            try:
                ofertas = await conector.buscar(client, consulta, 1)
            except SesionAsistidaRequerida as exc:
                # La ventana quedó abierta esperando a la persona; se corta acá.
                contadores["errors"] += 1
                mensajes.append(str(exc))
                registrar(run_id, "warn", str(exc), conector.id)
                break
            except FuenteBloqueada as exc:
                # El portal pidió verificación humana: no se insiste.
                contadores["errors"] += 1
                mensajes.append(str(exc))
                registrar(run_id, "error", str(exc), conector.id)
                break
            except Exception as exc:  # una búsqueda no corta el resto
                contadores["errors"] += 1
                detalle = f"{conector.id}/{consulta}: {type(exc).__name__}: {exc}"
                mensajes.append(detalle)
                registrar(run_id, "error", detalle, conector.id)
                continue

            contadores["found"] += len(ofertas)
            ahora = ahora_utc()
            with conexion() as conn:
                for oferta in ofertas:
                    try:
                        if _guardar(conn, oferta, ahora):
                            contadores["new"] += 1
                        else:
                            contadores["updated"] += 1
                    except Exception as exc:
                        contadores["errors"] += 1
                        detalle = f"guardar {oferta.external_id}: {exc}"
                        mensajes.append(detalle)
                        registrar(run_id, "error", detalle, conector.id)

            _actualizar_run(
                run_id,
                found=contadores["found"],
                new=contadores["new"],
                updated=contadores["updated"],
                errors=contadores["errors"],
            )
            await asyncio.sleep(pausa)

    return mensajes


async def ejecutar_actualizacion(run_id: int) -> None:
    async with LOCK:
        contadores = {"found": 0, "new": 0, "updated": 0, "errors": 0}
        mensajes: list[str] = []
        fuentes = _fuentes_activas()

        limpiar_viejos()
        registrar(
            run_id,
            "info",
            f"Actualización iniciada: {len(fuentes)} fuentes activas",
        )

        try:
            for indice, source_id in enumerate(fuentes):
                conector = crear_conector(source_id)
                if conector is None:
                    registrar(
                        run_id,
                        "warn",
                        "No hay conector registrado para esta fuente",
                        source_id,
                    )
                    continue

                with conexion() as conn:
                    fila_fuente = conn.execute(
                        "SELECT last_run_at, last_error FROM sources WHERE id = ?",
                        (source_id,),
                    ).fetchone()
                if _fuente_en_pausa(fila_fuente):
                    detalle = (
                        f"En pausa por bloqueo anti-bot; se reintenta en "
                        f"{PAUSA_BLOQUEO_MINUTOS} minutos"
                    )
                    mensajes.append(f"{source_id}: {detalle.lower()}")
                    registrar(run_id, "warn", detalle, source_id)
                    continue

                registrar(run_id, "info", "Consultando fuente", source_id)
                antes = dict(contadores)
                errores_fuente = await _actualizar_fuente(conector, run_id, contadores)
                mensajes.extend(errores_fuente)
                registrar(
                    run_id,
                    "info" if not errores_fuente else "warn",
                    (
                        f"{conector.nombre}: "
                        f"{contadores['found'] - antes['found']} encontrados, "
                        f"{contadores['new'] - antes['new']} nuevos, "
                        f"{contadores['updated'] - antes['updated']} actualizados"
                    ),
                    source_id,
                )

                with conexion() as conn:
                    conn.execute(
                        "UPDATE sources SET last_run_at = ?, last_error = ? WHERE id = ?",
                        (
                            iso(ahora_utc()),
                            ("; ".join(errores_fuente)[:500] or None),
                            source_id,
                        ),
                    )

                if indice < len(fuentes) - 1:
                    await asyncio.sleep(PAUSA_ENTRE_FUENTES)

            # Una vez guardados los avisos: puntuar, limpiar antiguos y agrupar duplicados.
            puntuar_todos()
            resultado_limpieza = limpiar()

            mensaje = "; ".join(mensajes)[:1000] or None
            if resultado_limpieza["eliminados"]:
                extra = (
                    f"limpiados {resultado_limpieza['eliminados']} avisos de más de "
                    f"{resultado_limpieza['dias']} días"
                )
                mensaje = f"{mensaje}; {extra}" if mensaje else extra
                registrar(
                    run_id,
                    "info",
                    f"Limpieza: {resultado_limpieza['eliminados']} avisos antiguos eliminados",
                )

            resumen = (
                f"Actualización completada: {contadores['found']} encontrados, "
                f"{contadores['new']} nuevos, {contadores['updated']} actualizados, "
                f"{contadores['errors']} errores"
            )
            registrar(
                run_id,
                "warn" if contadores["errors"] else "info",
                resumen,
            )
            _actualizar_run(
                run_id,
                status="ok",
                finished_at=iso(ahora_utc()),
                found=contadores["found"],
                new=contadores["new"],
                updated=contadores["updated"],
                errors=contadores["errors"],
                message=mensaje,
            )
        except Exception as exc:
            mensaje = f"{type(exc).__name__}: {exc}"[:1000]
            registrar(run_id, "error", f"Actualización interrumpida: {mensaje}")
            _actualizar_run(
                run_id,
                status="error",
                finished_at=iso(ahora_utc()),
                found=contadores["found"],
                new=contadores["new"],
                updated=contadores["updated"],
                errors=contadores["errors"] + 1,
                message=mensaje,
            )
