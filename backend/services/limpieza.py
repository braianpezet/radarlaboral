# -*- coding: utf-8 -*-
"""Limpieza de avisos antiguos.

Elimina los avisos con más de ``DIAS_RETENCION`` días que no tengan una señal
del usuario. Se conservan:

- guardados y postulados;
- avisos con nota;
- avisos con algún voto de feedback (sirven para entrenar el ranking).

Después de borrar, recalcula los duplicados para que no queden referencias
colgadas a un canónico eliminado.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..config import DIAS_RETENCION
from ..db import conexion
from .dedupe import deduplicar

_FILTRO = """
    COALESCE(j.published_at, j.fetched_at) < ?
    AND j.status NOT IN ('guardado', 'postulado')
    AND (j.note IS NULL OR trim(j.note) = '')
    AND NOT EXISTS (SELECT 1 FROM feedback f WHERE f.job_id = j.id)
"""


def _dias(dias: int | None) -> int:
    valor = DIAS_RETENCION if dias is None else int(dias)
    return max(1, min(valor, 3650))


def _corte(dias: int, ahora: datetime | None = None) -> str:
    ahora = ahora or datetime.now(timezone.utc)
    return (ahora - timedelta(days=dias)).isoformat(timespec="seconds")


def previsualizar(dias: int | None = None) -> dict:
    """Cuenta cuántos avisos se eliminarían sin borrar nada."""
    dias = _dias(dias)
    corte = _corte(dias)
    with conexion() as conn:
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        viejos = conn.execute(
            "SELECT COUNT(*) FROM jobs j "
            "WHERE COALESCE(j.published_at, j.fetched_at) < ?",
            (corte,),
        ).fetchone()[0]
        eliminables = conn.execute(
            f"SELECT COUNT(*) FROM jobs j WHERE {_FILTRO}", (corte,)
        ).fetchone()[0]
        protegidos = conn.execute(
            "SELECT COUNT(*) FROM jobs j "
            "WHERE COALESCE(j.published_at, j.fetched_at) < ? "
            "AND j.status IN ('guardado', 'postulado')",
            (corte,),
        ).fetchone()[0]
        con_nota = conn.execute(
            "SELECT COUNT(*) FROM jobs j "
            "WHERE COALESCE(j.published_at, j.fetched_at) < ? "
            "AND (j.note IS NOT NULL AND trim(j.note) <> '')",
            (corte,),
        ).fetchone()[0]
        con_feedback = conn.execute(
            "SELECT COUNT(*) FROM jobs j "
            "WHERE COALESCE(j.published_at, j.fetched_at) < ? "
            "AND EXISTS (SELECT 1 FROM feedback f WHERE f.job_id = j.id)",
            (corte,),
        ).fetchone()[0]
    return {
        "dias": dias,
        "corte": corte,
        "total": total,
        "viejos": viejos,
        "eliminables": eliminables,
        "protegidos": protegidos,
        "con_nota": con_nota,
        "con_feedback": con_feedback,
    }


def limpiar(dias: int | None = None) -> dict:
    """Borra los avisos antiguos sin señal del usuario y recalcula duplicados."""
    dias = _dias(dias)
    corte = _corte(dias)
    with conexion() as conn:
        ids = [
            fila["id"]
            for fila in conn.execute(
                f"SELECT j.id FROM jobs j WHERE {_FILTRO}", (corte,)
            ).fetchall()
        ]
        if ids:
            marcadores = ",".join("?" * len(ids))
            conn.execute(f"DELETE FROM jobs WHERE id IN ({marcadores})", ids)
            conn.execute(
                "UPDATE jobs SET duplicate_of = NULL "
                "WHERE duplicate_of IS NOT NULL "
                "AND duplicate_of NOT IN (SELECT id FROM jobs)"
            )
        restantes = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    duplicados = deduplicar()["duplicados"] if ids else 0
    return {
        "eliminados": len(ids),
        "duplicados": duplicados,
        "dias": dias,
        "corte": corte,
        "restantes": restantes,
    }
