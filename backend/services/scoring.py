# -*- coding: utf-8 -*-
"""Cálculo y persistencia del scoring de todos los avisos."""
from __future__ import annotations

import json

from ..db import conexion
from .profiles import cargar_perfiles, elegir_mejor
from .text import ahora_utc


def puntuar_todos() -> dict:
    """Recalcula el mejor perfil y el score de cada aviso."""
    ahora = ahora_utc()
    with conexion() as conn:
        perfiles = cargar_perfiles(conn)
        if not perfiles:
            return {"total": 0, "por_perfil": {}}
        filas = conn.execute(
            """
            SELECT id, title, summary, description, location, modality,
                   seniority, language, published_at, source_id
            FROM jobs
            """
        ).fetchall()

        actualizaciones = []
        por_perfil: dict[str, int] = {}
        for fila in filas:
            job = dict(fila)
            mejor = elegir_mejor(job, perfiles, ahora)
            actualizaciones.append(
                (
                    mejor["score"],
                    mejor["profile_id"],
                    json.dumps(mejor, ensure_ascii=False),
                    1 if mejor["excluded"] else 0,
                    fila["id"],
                )
            )
            if mejor.get("profile_id"):
                por_perfil[mejor["profile_id"]] = (
                    por_perfil.get(mejor["profile_id"], 0) + 1
                )

        conn.executemany(
            """
            UPDATE jobs
            SET score = ?, profile_id = ?, score_detail = ?, excluded = ?
            WHERE id = ?
            """,
            actualizaciones,
        )

    return {"total": len(actualizaciones), "por_perfil": por_perfil}


def puntuar_uno(job_id: int) -> dict | None:
    """Recalcula el score de un aviso puntual (por ejemplo, al cargar su detalle)."""
    ahora = ahora_utc()
    with conexion() as conn:
        perfiles = cargar_perfiles(conn)
        fila = conn.execute(
            """
            SELECT id, title, summary, description, location, modality,
                   seniority, language, published_at, source_id
            FROM jobs WHERE id = ?
            """,
            (job_id,),
        ).fetchone()
        if not fila or not perfiles:
            return None
        mejor = elegir_mejor(dict(fila), perfiles, ahora)
        conn.execute(
            """
            UPDATE jobs
            SET score = ?, profile_id = ?, score_detail = ?, excluded = ?
            WHERE id = ?
            """,
            (
                mejor["score"],
                mejor["profile_id"],
                json.dumps(mejor, ensure_ascii=False),
                1 if mejor["excluded"] else 0,
                job_id,
            ),
        )
    return mejor
