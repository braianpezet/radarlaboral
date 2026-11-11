# -*- coding: utf-8 -*-
"""Feedback del usuario y etiquetas para el futuro aprendizaje del ranking.

Etapa 1: solo se recolecta la señal. No se cambia el puntaje todavía.

- ``feedback`` guarda los votos explícitos (me interesa / no me interesa) con
  un snapshot del puntaje y del perfil del aviso.
- Los estados del aviso también son señales: postulado (+2), guardado (+1),
  descartado (-2), visto/nuevo (0). El voto explícito tiene prioridad sobre el
  estado para evitar contar dos veces la misma decisión.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..db import conexion

MOTIVOS_VALIDOS = {
    "seniority",
    "stack",
    "zona",
    "modalidad",
    "empresa",
    "idioma",
    "tareas",
    "salario",
}

PESO_ESTADO = {
    "postulado": 2,
    "guardado": 1,
    "descartado": -2,
    "visto": 0,
    "nuevo": 0,
}

META_POSITIVAS = 30
META_NEGATIVAS = 30


class AvisoNoEncontrado(LookupError):
    """El aviso no existe (o fue eliminado)."""


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _motivos(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [m for m in raw if isinstance(m, str) and m in MOTIVOS_VALIDOS]
    try:
        datos = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(datos, list):
        return []
    return [m for m in datos if isinstance(m, str) and m in MOTIVOS_VALIDOS]


def _serializar(fila) -> dict:
    return {
        "job_id": fila["job_id"],
        "profile_id": fila["profile_id"],
        "vote": fila["vote"],
        "motivos": _motivos(fila["motivos"]),
        "score_base": fila["score_base"],
        "created_at": fila["created_at"],
    }


def _ultimos(conn) -> dict[int, dict]:
    """Último voto explícito por aviso."""
    filas = conn.execute(
        """
        SELECT f.*
        FROM feedback f
        JOIN (
            SELECT job_id, MAX(id) AS id
            FROM feedback
            GROUP BY job_id
        ) u ON u.id = f.id
        """
    ).fetchall()
    return {fila["job_id"]: _serializar(fila) for fila in filas}


def voto_de(job_id: int) -> dict | None:
    with conexion() as conn:
        fila = conn.execute(
            "SELECT * FROM feedback WHERE job_id = ? ORDER BY id DESC LIMIT 1",
            (job_id,),
        ).fetchone()
    return _serializar(fila) if fila else None


def votos_actuales(ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    marcadores = ",".join("?" * len(ids))
    with conexion() as conn:
        filas = conn.execute(
            f"""
            SELECT f.*
            FROM feedback f
            JOIN (
                SELECT job_id, MAX(id) AS id
                FROM feedback
                WHERE job_id IN ({marcadores})
                GROUP BY job_id
            ) u ON u.id = f.id
            """,
            ids,
        ).fetchall()
    return {fila["job_id"]: _serializar(fila) for fila in filas}


def registrar(job_id: int, vote: int, motivos: list[str] | None = None) -> dict:
    """Guarda el voto. Si el último voto coincide, solo actualiza los motivos."""
    motivos = [m for m in dict.fromkeys(motivos or []) if m in MOTIVOS_VALIDOS]
    with conexion() as conn:
        aviso = conn.execute(
            "SELECT id, profile_id, score, score_detail FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if not aviso:
            raise AvisoNoEncontrado(job_id)

        ultimo = conn.execute(
            "SELECT * FROM feedback WHERE job_id = ? ORDER BY id DESC LIMIT 1",
            (job_id,),
        ).fetchone()

        if ultimo and ultimo["vote"] == vote:
            if _motivos(ultimo["motivos"]) != motivos:
                conn.execute(
                    "UPDATE feedback SET motivos = ? WHERE id = ?",
                    (json.dumps(motivos, ensure_ascii=False), ultimo["id"]),
                )
            fila = conn.execute(
                "SELECT * FROM feedback WHERE id = ?", (ultimo["id"],)
            ).fetchone()
        else:
            cur = conn.execute(
                """
                INSERT INTO feedback
                    (job_id, profile_id, vote, motivos, score_base, features, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    aviso["profile_id"],
                    vote,
                    json.dumps(motivos, ensure_ascii=False),
                    aviso["score"],
                    aviso["score_detail"],
                    _ahora_iso(),
                ),
            )
            fila = conn.execute(
                "SELECT * FROM feedback WHERE id = ?", (cur.lastrowid,)
            ).fetchone()

    return _serializar(fila)


def borrar(job_id: int) -> int:
    with conexion() as conn:
        cur = conn.execute("DELETE FROM feedback WHERE job_id = ?", (job_id,))
        return cur.rowcount


def etiquetas() -> list[dict]:
    """Ejemplos etiquetados: voto explícito > estado actual del aviso."""
    with conexion() as conn:
        votos = _ultimos(conn)
        filas = conn.execute(
            """
            SELECT id, title, company_name, location, modality, seniority,
                   language, source_id, profile_id, score, status,
                   status_updated_at, score_detail
            FROM jobs
            ORDER BY id
            """
        ).fetchall()

    salida: list[dict] = []
    for fila in filas:
        voto = votos.get(fila["id"])
        if voto:
            peso = 2 if voto["vote"] > 0 else -2
            origen = "voto"
            fecha = voto["created_at"]
        else:
            peso = PESO_ESTADO.get(fila["status"], 0)
            origen = "estado" if peso else None
            fecha = fila["status_updated_at"]
        if not origen:
            continue
        salida.append(
            {
                "job_id": fila["id"],
                "title": fila["title"],
                "company_name": fila["company_name"],
                "location": fila["location"],
                "modality": fila["modality"],
                "seniority": fila["seniority"],
                "language": fila["language"],
                "source_id": fila["source_id"],
                "profile_id": fila["profile_id"],
                "score": fila["score"],
                "peso": peso,
                "etiqueta": "positiva" if peso > 0 else "negativa",
                "origen": origen,
                "fecha": fecha,
                "features": fila["score_detail"],
            }
        )
    return salida


def resumen() -> dict:
    ejemplos = etiquetas()
    positivas = sum(1 for e in ejemplos if e["peso"] > 0)
    negativas = sum(1 for e in ejemplos if e["peso"] < 0)
    desde_votos = sum(1 for e in ejemplos if e["origen"] == "voto")
    desde_estados = sum(1 for e in ejemplos if e["origen"] == "estado")

    with conexion() as conn:
        votos = _ultimos(conn)

    positivos = sum(1 for v in votos.values() if v["vote"] > 0)
    negativos = sum(1 for v in votos.values() if v["vote"] < 0)
    por_motivo: dict[str, int] = {}
    for voto in votos.values():
        for motivo in voto["motivos"]:
            por_motivo[motivo] = por_motivo.get(motivo, 0) + 1

    return {
        "votos": {
            "total": len(votos),
            "positivos": positivos,
            "negativos": negativos,
        },
        "por_motivo": dict(
            sorted(por_motivo.items(), key=lambda par: (-par[1], par[0]))
        ),
        "etiquetas": {
            "total": len(ejemplos),
            "positivas": positivas,
            "negativas": negativas,
            "desde_votos": desde_votos,
            "desde_estados": desde_estados,
            "meta": META_POSITIVAS,
            "listo": positivas >= META_POSITIVAS and negativas >= META_NEGATIVAS,
            "faltan_positivas": max(0, META_POSITIVAS - positivas),
            "faltan_negativas": max(0, META_NEGATIVAS - negativas),
        },
    }
