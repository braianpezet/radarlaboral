# -*- coding: utf-8 -*-
"""Conector de Jooble (API REST oficial, clave gratuita).

Cada dominio de país de Jooble usa su propia clave: la de ``ar.jooble.org``
devuelve solo avisos de Argentina. La clave se lee del ``.env`` local
(``JOOBLE_API_KEY``) y nunca se escribe en el código. El plan gratuito tiene un
tope vitalicio de 500 consultas por clave, así que se pide una sola página de
hasta 100 avisos por búsqueda.

La API entrega un resumen (``snippet``) y el enlace a Jooble, no la descripción
completa: el aviso se abre en el portal original desde la app.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import httpx

from ..config import (
    BUSQUEDAS_JOOBLE,
    DIAS_RETENCION,
    JOOBLE_API_KEY,
    JOOBLE_DOMINIO,
    JOOBLE_POR_PAGINA,
    JOOBLE_UBICACION,
    PAUSA_JOOBLE,
)
from ..services.text import (
    detectar_modalidad,
    html_a_texto,
    limpiar_descripcion,
    normalizar,
    parsear_fecha,
)
from .base import FuenteBloqueada, JobRaw
from .filtros import es_relevante

# Mismas reglas de zona que la fuente de empresas: Argentina, remoto LatAm
# explícito o remoto global. Una sede presencial en otro país no sirve.
_ZONA_AR = re.compile(
    r"argentin|buenos aires|caba|capital federal|gba|gran buenos aires|"
    r"cordoba|rosario|mendoza|la plata|mar del plata|tucuman|salta|neuquen|"
    r"santa fe|entre rios|misiones|chaco|corrientes|jujuy|san juan|"
    r"san luis|la pampa|chubut|rio negro|santa cruz|tierra del fuego"
)
_ZONA_LATAM = re.compile(
    r"latin america|latam|lat-am|america latina|south america|sudamerica|"
    r"centroamerica|central america|caribbean|caribe|americas\b"
)
_ZONA_GLOBAL = re.compile(
    r"worldwide|world wide|anywhere|global|remote worldwide|"
    r"international|internacional|sin restriccion|no restriction"
)
_SOLO_REMOTO = re.compile(
    r"^(remote|remoto|remote only|fully remote|teletrabajo|trabajo remoto|"
    r"home office|remoto argentina)$"
)

# Jooble devuelve avisos de cualquier rubro: se descartan los títulos que no
# son técnicos aunque contengan una palabra clave ("desarrollador de negocios").
_NO_ROL = re.compile(
    r"\b(ventas|sales|comercial|business development|desarrollador de negocios|"
    r"marketing|growth|recruiter|recruiting|talent|finance|financial|"
    r"contable|accounting|payroll|legal|abogado|customer success|"
    r"asistente|administrativo|deposito|almacen|warehouse|logistica|"
    r"logistics|enfermero|enfermeria|chofer|operario|operador de maquinaria)\b"
)


def _texto(valor) -> str | None:
    if valor is None:
        return None
    crudo = str(valor)
    if "<" in crudo or "&" in crudo:
        texto = html_a_texto(crudo) or ""
    else:
        texto = crudo
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto or None


def _resumen(texto: str | None, largo: int = 240) -> str | None:
    if not texto:
        return None
    plano = re.sub(r"\s+", " ", texto).strip()
    if len(plano) <= largo:
        return plano or None
    corte = plano[:largo].rsplit(" ", 1)[0]
    return f"{corte}…"


def _zona_aceptada(ubicacion: str | None, remoto: bool) -> bool:
    t = normalizar(ubicacion)
    if not t:
        return remoto
    if _ZONA_AR.search(t):
        return True
    if _ZONA_GLOBAL.search(t):
        return True
    if _ZONA_LATAM.search(t):
        return remoto or "remote" in t or "remoto" in t
    return bool(_SOLO_REMOTO.fullmatch(t))


def _vigente(publicado: str | None) -> bool:
    """Descarta avisos que la limpieza de retención borraría igual."""
    fecha = parsear_fecha(publicado)
    if fecha is None:
        return True
    return fecha >= datetime.now(timezone.utc) - timedelta(days=DIAS_RETENCION)


class JoobleConnector:
    id = "jooble"
    nombre = "Jooble"
    busquedas = BUSQUEDAS_JOOBLE
    pausa_entre_busquedas = PAUSA_JOOBLE

    def cliente(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={"Accept": "application/json"},
            timeout=httpx.Timeout(45.0, connect=15.0),
            follow_redirects=True,
        )

    async def buscar(
        self, client: httpx.AsyncClient, consulta: str, pagina: int = 1
    ) -> list[JobRaw]:
        if not JOOBLE_API_KEY:
            return []

        cuerpo = {
            "keywords": consulta,
            "location": JOOBLE_UBICACION,
            "page": str(pagina),
            "ResultOnPage": str(JOOBLE_POR_PAGINA),
        }
        respuesta = await client.post(
            f"https://{JOOBLE_DOMINIO}/api/{JOOBLE_API_KEY}", json=cuerpo
        )
        if respuesta.status_code in (401, 403, 429):
            raise FuenteBloqueada(
                self.nombre, f"HTTP {respuesta.status_code} en {JOOBLE_DOMINIO}"
            )
        if respuesta.status_code == 404:
            return []
        respuesta.raise_for_status()

        datos = respuesta.json()
        trabajos = datos.get("jobs") if isinstance(datos, dict) else None
        if not isinstance(trabajos, list):
            return []

        ofertas: list[JobRaw] = []
        for job in trabajos:
            if not isinstance(job, dict):
                continue
            oferta = self._mapear(job)
            if oferta is not None:
                ofertas.append(oferta)
        return ofertas

    def _mapear(self, job: dict) -> JobRaw | None:
        titulo = _texto(job.get("title"))
        enlace = _texto(job.get("link"))
        if not titulo or not enlace:
            return None
        if _NO_ROL.search(normalizar(titulo)) or not es_relevante(titulo):
            return None

        ubicacion = _texto(job.get("location"))
        remoto = bool(
            re.search(r"\b(remote|remoto|home office|teletrabajo)\b", normalizar(ubicacion))
        )
        if not _zona_aceptada(ubicacion, remoto):
            return None

        snippet = _texto(job.get("snippet"))
        descripcion = limpiar_descripcion(snippet)
        publicado = _texto(job.get("updated"))
        if not _vigente(publicado):
            return None

        external_id = str(job.get("id") or "").strip()
        if not external_id:
            coincidencia = re.search(r"/desc/([^/?#]+)", enlace)
            external_id = coincidencia.group(1) if coincidencia else enlace

        return JobRaw(
            source_id=self.id,
            external_id=external_id,
            url=enlace,
            title=titulo,
            company=_texto(job.get("company")),
            location=ubicacion,
            description=descripcion,
            summary=_resumen(snippet),
            salary_text=_texto(job.get("salary")),
            published_text=publicado,
            contract_type=_texto(job.get("type")),
            modality_hint=(
                detectar_modalidad(f"{titulo} {ubicacion} {snippet}")
                or ("Remoto" if remoto else None)
            ),
        )

    async def detalle(
        self, client: httpx.AsyncClient, url: str
    ) -> tuple[str | None, str | None]:
        """Jooble no expone el detalle completo: se conserva el resumen."""
        return None, None
