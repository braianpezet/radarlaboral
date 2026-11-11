# -*- coding: utf-8 -*-
"""Estado y apertura de las sesiones asistidas (ZonaJobs / Bumeran).

La ventana la abre ``assisted/navent.mjs`` con el Edge real y el perfil
persistente. Este módulo solo lanza ese proceso y lee el marcador que el
script deja en ``data/sesion_navent_<sitio>.json``.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from ..config import ASSISTED_DIR, DATA_DIR, SESIONES_ASISTIDAS
from ..connectors import crear_conector

_procesos: dict[str, subprocess.Popen] = {}


class SesionEnCurso(RuntimeError):
    """Ya hay una ventana de sesión abierta (el perfil es uno solo)."""


def _marcador(sitio: str) -> Path:
    return DATA_DIR / f"sesion_navent_{sitio}.json"


def _leer_marcador(sitio: str) -> dict:
    ruta = _marcador(sitio)
    if not ruta.exists():
        return {}
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return datos if isinstance(datos, dict) else {}


def _vivo(proceso: subprocess.Popen | None) -> bool:
    return proceso is not None and proceso.poll() is None


def _proceso_de(sitio: str) -> subprocess.Popen | None:
    proceso = _procesos.get(sitio)
    if proceso is not None and not _vivo(proceso):
        _procesos.pop(sitio, None)
        return None
    return proceso


def _ventana_abierta() -> str | None:
    for sitio, proceso in list(_procesos.items()):
        if _vivo(proceso):
            return sitio
        _procesos.pop(sitio, None)
    return None


def _node() -> str:
    node = shutil.which("node") or shutil.which("node.exe")
    if not node:
        raise RuntimeError(
            "No se encontró Node.js. Es necesario para abrir la sesión "
            "asistida de ZonaJobs y Bumeran."
        )
    return node


def _estado(sitio: str, conector) -> dict:
    marcador = _leer_marcador(sitio)
    proceso = _proceso_de(sitio)
    valido = marcador.get("valid")
    return {
        "sitio": sitio,
        "source_id": conector.id,
        "name": conector.nombre,
        "portal": conector.base,
        "valid": bool(valido) if valido is not None else None,
        "detalle": marcador.get("detalle"),
        "checked_at": marcador.get("checked_at"),
        "ventana_abierta": _vivo(proceso),
    }


def _conector_asistido(source_id: str):
    conector = crear_conector(source_id)
    if conector is None or not getattr(conector, "asistida", False):
        return None
    return conector


def estado_sesiones() -> list[dict]:
    salida = []
    for source_id in SESIONES_ASISTIDAS:
        conector = _conector_asistido(source_id)
        if conector is None:
            continue
        salida.append(_estado(conector.sitio, conector))
    return salida


def abrir_sesion(source_id: str) -> dict:
    conector = _conector_asistido(source_id)
    if conector is None:
        raise KeyError(source_id)

    abierta = _ventana_abierta()
    if abierta and abierta != conector.sitio:
        raise SesionEnCurso(
            "Ya hay una ventana de sesión abierta. Cerrala antes de abrir la "
            "otra: ZonaJobs y Bumeran comparten el mismo perfil de navegador."
        )
    if abierta == conector.sitio:
        return _estado(conector.sitio, conector)

    script = ASSISTED_DIR / "navent.mjs"
    if not script.exists():
        raise RuntimeError(
            f"Falta el script de sesión asistida: {script}. "
            "Instalá las dependencias con `npm install` dentro de assisted/."
        )

    creacion = 0
    if sys.platform == "win32":
        creacion = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    proceso = subprocess.Popen(
        [
            _node(),
            str(script),
            "open",
            "--site",
            conector.sitio,
            "--data-dir",
            str(DATA_DIR),
        ],
        cwd=str(ASSISTED_DIR),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creacion,
    )
    _procesos[conector.sitio] = proceso
    # Si el navegador no pudo abrirse (perfil bloqueado, dependencias faltantes)
    # el proceso muere en seguida: se avisa en vez de mostrar una ventana fantasma.
    time.sleep(1.2)
    if proceso.poll() is not None:
        _procesos.pop(conector.sitio, None)
        raise RuntimeError(
            "No se pudo abrir la ventana de sesión. Verificá que no haya otra "
            "ventana de ZonaJobs/Bumeran abierta y que assisted/ tenga sus "
            "dependencias instaladas (`npm install`)."
        )
    return _estado(conector.sitio, conector)


def resumen() -> dict:
    """Resumen compacto para la cabecera de la app."""
    estados = estado_sesiones()
    return {
        "sesiones": estados,
        "requerida": any(estado["valid"] is False for estado in estados),
        "abierta": _ventana_abierta(),
    }
