# -*- coding: utf-8 -*-
"""Deduplicación entre portales.

Agrupa por empresa, compara título/ubicación y, si hace falta, descripción.
El aviso canónico es el que tiene descripción, mejor score y fuente local.
Los demás quedan ocultos con `duplicate_of` apuntando al canónico.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from ..db import conexion
from .text import normalizar

_RANGO_FUENTE = {
    "empleosit": 0,
    "getonboard": 0,
    "computrabajo": 0,
}


def _clave(texto: str | None) -> str:
    return re.sub(r"[^\w\s]", " ", normalizar(texto)).strip()


_SENIORITY = re.compile(
    r"(?<!\w)(semi[\s-]?senior|trainee|junior|jr|ssr|senior|sr|lead)(?!\w)"
)


def _nivel_seniority(texto: str) -> str | None:
    """Nivel explícito en el título; sirve para no fusionar Jr con Sr."""
    encontrado = _SENIORITY.search(texto)
    if not encontrado:
        return None
    valor = encontrado.group(1)
    if valor == "trainee":
        return "trainee"
    if valor in ("junior", "jr"):
        return "junior"
    if valor in ("semi senior", "semi-senior", "ssr"):
        return "semi"
    if valor in ("senior", "sr"):
        return "senior"
    return "lead"


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _misma_ubicacion(a: str, b: str) -> bool:
    if not a or not b:
        return True
    if a == b:
        return True
    ta, tb = set(a.split()), set(b.split())
    if ta <= tb or tb <= ta:
        return True
    return _ratio(a, b) >= 0.75


def _son_duplicados(a: dict, b: dict) -> bool:
    # Sin empresa no se puede usar el fingerprint como atajo: dos empleadores
    # distintos pueden publicar el mismo título genérico en la misma ciudad.
    sin_empresa = a.get("sin_empresa") or b.get("sin_empresa")
    if not sin_empresa and a["fingerprint"] and a["fingerprint"] == b["fingerprint"]:
        return True
    if not _misma_ubicacion(a["loc"], b["loc"]):
        return False

    # No fusionar un aviso Jr con uno Sr de la misma empresa.
    if _nivel_seniority(a["titulo"]) != _nivel_seniority(b["titulo"]):
        return False

    titulo_a, titulo_b = a["titulo"], b["titulo"]
    ratio_titulo = _ratio(titulo_a, titulo_b)

    if sin_empresa:
        # Solo se fusionan avisos anónimos si además la descripción es casi
        # idéntica (el mismo aviso replicado en ZonaJobs y Bumeran).
        if ratio_titulo < 0.92:
            return False
        desc_a, desc_b = a["desc"], b["desc"]
        if len(desc_a) > 200 and len(desc_b) > 200:
            return _ratio(desc_a, desc_b) >= 0.95
        return False

    if ratio_titulo >= 0.92:
        return True

    if ratio_titulo >= 0.80:
        desc_a, desc_b = a["desc"], b["desc"]
        if len(desc_a) > 200 and len(desc_b) > 200:
            return _ratio(desc_a, desc_b) >= 0.92
    return False


def deduplicar() -> dict:
    with conexion() as conn:
        conn.execute("UPDATE jobs SET duplicate_of = NULL")
        filas = conn.execute(
            """
            SELECT id, source_id, title, company_name, location, description,
                   published_at, score, fingerprint
            FROM jobs
            ORDER BY id
            """
        ).fetchall()

        grupos: dict[str, list[dict]] = {}
        for fila in filas:
            empresa = _clave(fila["company_name"])
            sin_empresa = not empresa
            if sin_empresa:
                # Los avisos sin empresa se agrupan por título + ubicación y
                # solo se fusionan si la descripción también coincide.
                empresa = "sin-empresa|{}|{}".format(
                    _clave(fila["title"]), _clave(fila["location"])
                )
            grupos.setdefault(empresa, []).append(
                {
                    "id": fila["id"],
                    "source_id": fila["source_id"],
                    "titulo": _clave(fila["title"]),
                    "loc": _clave(fila["location"]),
                    "desc": normalizar(fila["description"]),
                    "fingerprint": fila["fingerprint"],
                    "score": fila["score"] or 0,
                    "tiene_desc": 1 if fila["description"] else 0,
                    "rango_fuente": _RANGO_FUENTE.get(fila["source_id"], 1),
                    "sin_empresa": sin_empresa,
                }
            )

        ocultos: list[tuple[int, int]] = []
        grupos_con_dupes = 0
        for items in grupos.values():
            if len(items) < 2:
                continue
            items.sort(
                key=lambda x: (
                    -x["tiene_desc"],
                    -x["score"],
                    x["rango_fuente"],
                    x["id"],
                )
            )
            canonicos: list[dict] = []
            ocultos_grupo = 0
            for item in items:
                duplicado_de = None
                for canonico in canonicos:
                    if _son_duplicados(item, canonico):
                        duplicado_de = canonico["id"]
                        break
                if duplicado_de is not None:
                    ocultos.append((duplicado_de, item["id"]))
                    ocultos_grupo += 1
                else:
                    canonicos.append(item)
            if ocultos_grupo:
                grupos_con_dupes += 1

        if ocultos:
            conn.executemany(
                "UPDATE jobs SET duplicate_of = ? WHERE id = ?", ocultos
            )

    return {
        "duplicados": len(ocultos),
        "grupos": grupos_con_dupes,
        "total": len(filas),
    }
