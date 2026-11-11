# -*- coding: utf-8 -*-
"""Conector de ZonaJobs y Bumeran (plataforma Navent, Argentina).

Ambos portales comparten la API ``/api/avisos/searchV2`` y están detrás de
Cloudflare. No se automatiza ningún desafío: la consulta se delega a
``assisted/navent.mjs``, que abre una ventana real de Edge con perfil
persistente para que la persona resuelva la verificación a mano y luego
consulta la API desde la misma pestaña.

Si la sesión no está validada, se lanza :class:`SesionAsistidaRequerida` y la
ingesta detiene la fuente sin reintentar.
"""
from __future__ import annotations

import asyncio
import json
import shutil
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from ..config import (
    ASSISTED_DIR,
    BUSQUEDAS,
    DATA_DIR,
    NAVENT_ESPERA_SESION,
    NAVENT_MAX_PAGINAS,
    NAVENT_TIMEOUT,
    PAUSA_NAVENT,
)
from ..services.text import html_a_texto, limpiar_descripcion
from .base import JobRaw, SesionAsistidaRequerida
from .filtros import es_relevante

_ZONA_AR = timezone(timedelta(hours=-3))


def _fecha(valor) -> str | None:
    """Normaliza ``DD-MM-YYYY HH:MM:SS`` (o epoch ms) a ISO en UTC."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float)):
        numero = float(valor)
        if numero > 1e12:  # epoch en milisegundos
            numero /= 1000
        try:
            return datetime.fromtimestamp(numero, tz=timezone.utc).isoformat(
                timespec="seconds"
            )
        except (ValueError, OSError, OverflowError):
            return None
    texto = str(valor).strip()
    for formato in ("%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            local = datetime.strptime(texto, formato).replace(tzinfo=_ZONA_AR)
            return local.astimezone(timezone.utc).isoformat(timespec="seconds")
        except ValueError:
            continue
    return texto


class NaventConnector:
    """Base compartida: una sola corrida del navegador para todas las búsquedas."""

    id = ""
    nombre = ""
    base = ""
    sitio = ""  # clave que usa assisted/navent.mjs
    site_id = ""  # cabecera x-site-id de la API Navent
    busquedas = BUSQUEDAS
    pausa_entre_busquedas = PAUSA_NAVENT
    asistida = True

    def __init__(self) -> None:
        self._cache: dict[str, list[JobRaw]] | None = None

    @asynccontextmanager
    async def cliente(self):
        # No hay cliente HTTP: la sesión la maneja el navegador asistido.
        yield self

    async def buscar(
        self, client, consulta: str, pagina: int = 1
    ) -> list[JobRaw]:
        if pagina > 1:
            return []
        if self._cache is None:
            await self._consultar_todo()
        return self._cache.get(consulta, []) if self._cache else []

    async def detalle(self, client, url: str) -> tuple[str | None, str | None]:
        # El listado ya trae la descripción completa.
        return None, None

    async def _consultar_todo(self) -> None:
        script = ASSISTED_DIR / "navent.mjs"
        if not script.exists():
            raise RuntimeError(
                f"Falta el script de sesión asistida: {script}. "
                "Instalá las dependencias con `npm install` dentro de assisted/."
            )
        node = shutil.which("node") or shutil.which("node.exe")
        if not node:
            raise RuntimeError(
                "No se encontró Node.js. Es necesario para la sesión asistida "
                "de ZonaJobs y Bumeran."
            )

        argumentos = [
            node,
            str(script),
            "fetch",
            "--site",
            self.sitio,
            "--data-dir",
            str(DATA_DIR),
            "--pages",
            str(NAVENT_MAX_PAGINAS),
            "--espera-sesion",
            str(NAVENT_ESPERA_SESION),
        ]
        for consulta in self.busquedas:
            argumentos.extend(["--query", consulta])

        proceso = await asyncio.create_subprocess_exec(
            *argumentos,
            cwd=str(ASSISTED_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            salida, error = await asyncio.wait_for(
                proceso.communicate(), timeout=NAVENT_TIMEOUT
            )
        except asyncio.TimeoutError:
            proceso.kill()
            await proceso.wait()
            raise RuntimeError(
                "La sesión asistida superó el tiempo máximo de espera. "
                "Cerrá la ventana del portal y volvé a intentar."
            )

        datos = self._json_salida(salida)
        if not datos:
            detalle = (error or b"").decode("utf-8", "replace").strip()[-400:]
            raise RuntimeError(
                "La sesión asistida no devolvió datos"
                + (f": {detalle}" if detalle else ".")
            )

        if not datos.get("ok"):
            if datos.get("error") == "sesion_requerida":
                raise SesionAsistidaRequerida(
                    self.nombre, str(datos.get("detalle") or "")
                )
            raise RuntimeError(
                str(datos.get("detalle") or datos.get("error") or "error desconocido")
            )

        cache: dict[str, list[JobRaw]] = {}
        for consulta, items in (datos.get("resultados") or {}).items():
            ofertas: list[JobRaw] = []
            for item in items or []:
                if not isinstance(item, dict):
                    continue
                oferta = self._mapear(item)
                if oferta is not None:
                    ofertas.append(oferta)
            cache[consulta] = ofertas
        self._cache = cache

    @staticmethod
    def _json_salida(salida: bytes) -> dict | None:
        for linea in reversed((salida or b"").decode("utf-8", "replace").splitlines()):
            linea = linea.strip()
            if not linea.startswith("{"):
                continue
            try:
                return json.loads(linea)
            except json.JSONDecodeError:
                continue
        return None

    def _mapear(self, item: dict) -> JobRaw | None:
        external_id = str(item.get("id") or "").strip()
        titulo = str(item.get("titulo") or "").strip()
        if not external_id or not titulo or not es_relevante(titulo):
            return None

        empresa = None
        if not item.get("confidencial"):
            empresa = str(item.get("empresa") or "").strip() or None

        descripcion = limpiar_descripcion(html_a_texto(item.get("detalle")))
        ubicacion = str(item.get("localizacion") or "").strip() or None
        modalidad = str(item.get("modalidadTrabajo") or "").strip() or None
        contrato = str(item.get("tipoTrabajo") or "").strip() or None
        fecha = _fecha(item.get("fechaHoraPublicacion") or item.get("fechaPublicacion"))

        return JobRaw(
            source_id=self.id,
            external_id=external_id,
            url=f"{self.base}/empleos/aviso-{external_id}.html",
            title=titulo,
            company=empresa,
            location=ubicacion,
            description=descripcion,
            published_text=fecha,
            contract_type=contrato,
            modality_hint=modalidad,
        )


class ZonaJobsConnector(NaventConnector):
    id = "zonajobs"
    nombre = "ZonaJobs AR"
    base = "https://www.zonajobs.com.ar"
    sitio = "zonajobs"
    site_id = "ZJAR"


class BumeranConnector(NaventConnector):
    id = "bumeran"
    nombre = "Bumeran AR"
    base = "https://www.bumeran.com.ar"
    sitio = "bumeran"
    site_id = "BMAR"
