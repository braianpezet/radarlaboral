# -*- coding: utf-8 -*-
"""Registro de eventos de las actualizaciones.

Guarda líneas cortas (info/warn/error) para que la UI pueda mostrar qué pasó
durante cada escaneo sin tener que abrir la consola. La retención es acotada:
14 días o 3000 filas, lo que se cumpla primero.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..db import conexion

NIVELES = {"info", "warn", "error"}
DIAS_RETENCION = 14
MAXIMO_FILAS = 3000


def _recortar(texto: str | None, largo: int = 600) -> str:
    limpio = " ".join(str(texto or "").split())
    return limpio[:largo]


def registrar(
    run_id: int, nivel: str, mensaje: str, source_id: str | None = None
) -> None:
    """Agrega una línea al registro. Un fallo de log no corta el escaneo."""
    if nivel not in NIVELES:
        nivel = "info"
    texto = _recortar(mensaje)
    if not texto:
        return
    try:
        with conexion() as conn:
            conn.execute(
                "INSERT INTO run_logs (run_id, source_id, level, message, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    run_id,
                    source_id,
                    nivel,
                    texto,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
    except Exception:
        # El diagnóstico nunca debe romper la actualización.
        pass


def listar(limit: int = 150, run_id: int | None = None) -> list[dict]:
    """Devuelve los eventos más recientes en orden cronológico."""
    limit = max(1, min(int(limit), 1000))
    consulta = """
        SELECT l.id, l.run_id, l.source_id, l.level, l.message, l.created_at,
               s.name AS source_name
        FROM run_logs l
        LEFT JOIN sources s ON s.id = l.source_id
    """
    params: list = []
    if run_id is not None:
        consulta += " WHERE l.run_id = ?"
        params.append(run_id)
    consulta += " ORDER BY l.id DESC LIMIT ?"
    params.append(limit)
    with conexion() as conn:
        filas = conn.execute(consulta, params).fetchall()
    return [dict(fila) for fila in reversed(filas)]


def limpiar_viejos(dias: int = DIAS_RETENCION, maximo: int = MAXIMO_FILAS) -> None:
    """Poda el registro para que no crezca sin límite."""
    corte = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat(
        timespec="seconds"
    )
    try:
        with conexion() as conn:
            conn.execute("DELETE FROM run_logs WHERE created_at < ?", (corte,))
            conn.execute(
                "DELETE FROM run_logs WHERE id NOT IN "
                "(SELECT id FROM run_logs ORDER BY id DESC LIMIT ?)",
                (maximo,),
            )
    except Exception:
        pass
