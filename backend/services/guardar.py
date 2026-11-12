# -*- coding: utf-8 -*-
"""Diálogo nativo de Windows para elegir dónde guardar un archivo.

Se usa la API clásica ``GetSaveFileNameW`` de comdlg32 para que la ventana sea
la de Windows y no una descarga automática del navegador. El diálogo se puede
abrir desde el hilo del servidor; no necesita COM ni el hilo de la interfaz.
"""
from __future__ import annotations

import ctypes
import re
from pathlib import Path

from ctypes import wintypes

MAX_NOMBRE = 100
EXTENSIONES = {"docx", "md"}

OFN_OVERWRITEPROMPT = 0x00000002
OFN_NOCHANGEDIR = 0x00000008
OFN_PATHMUSTEXIST = 0x00000800
OFN_EXPLORER = 0x00080000
OFN_ENABLESIZING = 0x00800000
OFN_DONTADDTORECENT = 0x02000000


class GuardarError(Exception):
    """No se pudo elegir el destino o escribir el archivo."""


class _OpenFileNameW(ctypes.Structure):
    _fields_ = [
        ("lStructSize", wintypes.DWORD),
        ("hwndOwner", wintypes.HWND),
        ("hInstance", wintypes.HINSTANCE),
        ("lpstrFilter", wintypes.LPCWSTR),
        ("lpstrCustomFilter", wintypes.LPWSTR),
        ("nMaxCustFilter", wintypes.DWORD),
        ("nFilterIndex", wintypes.DWORD),
        ("lpstrFile", wintypes.LPWSTR),
        ("nMaxFile", wintypes.DWORD),
        ("lpstrFileTitle", wintypes.LPWSTR),
        ("nMaxFileTitle", wintypes.DWORD),
        ("lpstrInitialDir", wintypes.LPCWSTR),
        ("lpstrTitle", wintypes.LPCWSTR),
        ("Flags", wintypes.DWORD),
        ("nFileOffset", wintypes.WORD),
        ("nFileExtension", wintypes.WORD),
        ("lpstrDefExt", wintypes.LPCWSTR),
        ("lCustData", wintypes.LPARAM),
        ("lpfnHook", wintypes.LPVOID),
        ("lpTemplateName", wintypes.LPCWSTR),
        ("pvReserved", wintypes.LPVOID),
        ("dwReserved", wintypes.DWORD),
        ("FlagsEx", wintypes.DWORD),
    ]


def _validar_extension(extension: str) -> str:
    limpia = (extension or "").strip().lower().lstrip(".")
    if limpia not in EXTENSIONES:
        raise GuardarError("Extensión de archivo no admitida.")
    return limpia


def nombre_seguro(nombre: str, extension: str) -> str:
    """Nombre que Windows acepta, con la extensión correcta."""
    extension = _validar_extension(extension)
    base = (nombre or "").strip()
    sufijo = f".{extension}"
    if base.lower().endswith(sufijo):
        base = base[: -len(sufijo)]
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", base)
    base = re.sub(r"\s+", " ", base).strip(" .")[:MAX_NOMBRE].strip()
    return f"{base or 'cv-adaptado'}{sufijo}"


def _filtros(extension: str) -> str:
    if extension == "docx":
        descripcion = "Documento de Word"
    else:
        descripcion = "Documento Markdown"
    return (
        f"{descripcion} (*.{extension})\0*.{extension}\0"
        "Todos los archivos (*.*)\0*.*\0\0"
    )


def _ventana_de_la_app() -> int:
    """HWND de Radar Laboral, para que el diálogo quede encima de la app."""
    try:
        return int(ctypes.windll.user32.FindWindowW(None, "Radar Laboral") or 0)
    except Exception:
        return 0


def elegir_ruta(nombre: str, extension: str) -> str | None:
    """Abre «Guardar como» y devuelve la ruta elegida, o None si se canceló."""
    extension = _validar_extension(extension)
    nombre = nombre_seguro(nombre, extension)

    archivo = ctypes.create_unicode_buffer(1024)
    archivo.value = nombre
    filtros = ctypes.create_unicode_buffer(_filtros(extension))
    titulo = ctypes.create_unicode_buffer("Guardar como")

    datos = _OpenFileNameW()
    datos.lStructSize = ctypes.sizeof(_OpenFileNameW)
    datos.hwndOwner = _ventana_de_la_app()
    datos.lpstrFilter = ctypes.cast(filtros, wintypes.LPCWSTR)
    datos.nFilterIndex = 1
    datos.lpstrFile = ctypes.cast(archivo, wintypes.LPWSTR)
    datos.nMaxFile = len(archivo)
    datos.lpstrTitle = ctypes.cast(titulo, wintypes.LPCWSTR)
    datos.lpstrDefExt = extension
    datos.Flags = (
        OFN_OVERWRITEPROMPT
        | OFN_NOCHANGEDIR
        | OFN_PATHMUSTEXIST
        | OFN_EXPLORER
        | OFN_ENABLESIZING
        | OFN_DONTADDTORECENT
    )

    try:
        ok = ctypes.windll.comdlg32.GetSaveFileNameW(ctypes.byref(datos))
    except Exception as exc:
        raise GuardarError(f"Windows no pudo abrir el diálogo: {exc}") from exc

    if not ok:
        error = ctypes.windll.comdlg32.CommDlgExtendedError()
        if not error:
            return None
        raise GuardarError(f"Windows no pudo abrir el diálogo (error {error}).")
    return archivo.value or None


def guardar_como(nombre: str, contenido: bytes, extension: str) -> dict:
    """Pide la ubicación con el diálogo de Windows y escribe los bytes."""
    ruta = elegir_ruta(nombre, extension)
    if not ruta:
        return {"guardado": False, "cancelado": True}
    try:
        Path(ruta).write_bytes(contenido)
    except OSError as exc:
        raise GuardarError(f"No se pudo escribir el archivo: {exc}") from exc
    return {"guardado": True, "ruta": ruta}
