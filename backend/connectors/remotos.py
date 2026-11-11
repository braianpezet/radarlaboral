# -*- coding: utf-8 -*-
"""Conectores de APIs públicas de empleo remoto (sin clave).

Remotive, RemoteOK, Himalayas y Jobicy publican avisos remotos de todo el
mundo. Acá se descartan los limitados a países que no interesan y se conserva
Argentina, LatAm y el remoto sin restricción de país. La descripción ya viene
en el listado, así que no hace falta pedir el detalle.
"""
from __future__ import annotations

import html as html_lib
import re

import httpx

from ..config import HEADERS
from ..services.text import (
    aceptar_ubicacion,
    html_a_texto,
    limpiar_descripcion,
    normalizar,
    reparar_mojibake,
    texto_salario,
)
from .base import JobRaw

PAGINAS_HIMALAYAS = 3
TAMANO_HIMALAYAS = 20

# Los boards remotos son genéricos: se conservan solo roles de IT o afines.
_ROLES_IT = re.compile(
    r"\b(developer|software|engineer|engineering|programmer|programador|"
    r"programadora|desenvolvedor|desarrollador|desarrolladora|"
    r"data|datos|machine learning|\bml\b|\bai\b|artificial intelligence|"
    r"inteligencia artificial|python|java|javascript|typescript|react|"
    r"angular|vue|node|php|ruby|golang|rust|backend|back-end|frontend|"
    r"front-end|full stack|fullstack|devops|\bsre\b|cloud|aws|azure|gcp|"
    r"kubernetes|docker|\bqa\b|quality assurance|tester|testing|"
    r"analyst|analista|business intelligence|\bbi\b|\betl\b|\bdba\b|"
    r"database|base de datos|support|soporte|help ?desk|service desk|"
    r"sysadmin|system administrator|administrador de sistemas|"
    r"infrastructure|infraestructura|network|redes|security|seguridad|"
    r"cybersecurity|ciberseguridad|architect|arquitecto|tech lead|"
    r"technical lead|lider tecnico|\bcto\b|it operations|computer|"
    r"computacion|sistemas|product manager|project manager|scrum|agile|"
    r"sap|salesforce|\berp\b|\bcrm\b|docente|profesor|tutor|capacitador|"
    r"instructor|teacher)\b"
)
_NO_IT = re.compile(
    r"\b(sales|ventas|account executive|account manager|marketing|growth|"
    r"copywriter|writer|redactor|content|contenido|recruiter|recruiting|"
    r"talent|people operations|human resources|\bhr\b|finance|financial|"
    r"accounting|contable|payroll|clinical|nurse|medical|legal|abogado|"
    r"contracts|property manager|real estate|inmobiliaria|customer success|"
    r"executive assistant|virtual assistant|asistente|receptionist|"
    r"translator|traductor|interpreter|review lead|brand protection|"
    r"supply chain|logistics|logistica|transport|driver|chofer|"
    r"academic dean|operations coordinator|partner operations|"
    r"country manager)\b"
)


def _es_it(titulo: str | None) -> bool:
    """Filtro conservador de relevancia para boards remotos genéricos."""
    t = normalizar(titulo)
    if not t:
        return False
    if _NO_IT.search(t):
        return False
    return bool(_ROLES_IT.search(t))


def _limpio(valor) -> str | None:
    if valor is None:
        return None
    texto = html_lib.unescape(str(valor))
    texto = reparar_mojibake(texto) or ""
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


def _descripcion(valor) -> str | None:
    if not valor:
        return None
    return limpiar_descripcion(html_a_texto(str(valor)))


def _cliente() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={**HEADERS, "Accept": "application/json"},
        timeout=httpx.Timeout(60.0, connect=15.0),
        follow_redirects=True,
    )


class _ConectorAPI:
    """Base común: una sola lista de búsquedas y sin detalle bajo demanda."""

    busquedas = ["recientes"]

    def cliente(self) -> httpx.AsyncClient:
        return _cliente()

    async def detalle(
        self, client: httpx.AsyncClient, url: str
    ) -> tuple[str | None, str | None]:
        return None, None


class RemotiveConnector(_ConectorAPI):
    id = "remotive"
    nombre = "Remotive"
    url = "https://remotive.com/api/remote-jobs?limit=200"

    async def buscar(
        self, client: httpx.AsyncClient, consulta: str, pagina: int = 1
    ) -> list[JobRaw]:
        respuesta = await client.get(self.url)
        respuesta.raise_for_status()
        datos = respuesta.json()
        return self._parsear(datos.get("jobs") or [])

    def _parsear(self, jobs: list[dict]) -> list[JobRaw]:
        ofertas: list[JobRaw] = []
        for job in jobs:
            titulo = _limpio(job.get("title")) or "(sin título)"
            if not _es_it(titulo):
                continue
            ubicacion = _limpio(job.get("candidate_required_location"))
            if not aceptar_ubicacion(ubicacion):
                continue

            descripcion = _descripcion(job.get("description"))
            salario = _limpio(job.get("salary"))
            if salario and "$" in salario and not re.search(r"usd|eur|ars", salario, re.I):
                salario = f"USD {salario}"

            ofertas.append(
                JobRaw(
                    source_id=self.id,
                    external_id=str(job.get("id") or job.get("url")),
                    url=str(job.get("url") or ""),
                    title=titulo,
                    company=_limpio(job.get("company_name")),
                    location=ubicacion,
                    description=descripcion,
                    summary=_resumen(descripcion),
                    salary_text=salario,
                    published_text=_limpio(job.get("publication_date")),
                    contract_type=self._contrato(job.get("job_type")),
                    modality_hint="Remoto",
                )
            )
        return ofertas

    @staticmethod
    def _contrato(tipo: str | None) -> str | None:
        return {
            "full_time": "Full time",
            "part_time": "Part time",
            "contract": "Contrato",
            "freelance": "Freelance",
            "internship": "Pasantía",
            "temporary": "Temporal",
            "other": None,
        }.get((tipo or "").strip().lower())


class RemoteOkConnector(_ConectorAPI):
    id = "remoteok"
    nombre = "RemoteOK"
    url = "https://remoteok.com/api"

    async def buscar(
        self, client: httpx.AsyncClient, consulta: str, pagina: int = 1
    ) -> list[JobRaw]:
        respuesta = await client.get(self.url)
        respuesta.raise_for_status()
        datos = respuesta.json()
        return self._parsear(datos)

    def _parsear(self, datos) -> list[JobRaw]:
        ofertas: list[JobRaw] = []
        if not isinstance(datos, list):
            return ofertas

        for job in datos:
            if not isinstance(job, dict) or not job.get("id"):
                continue
            titulo = _limpio(job.get("position")) or "(sin título)"
            if not _es_it(titulo):
                continue
            ubicacion = _limpio(job.get("location"))
            if not aceptar_ubicacion(ubicacion):
                continue

            descripcion = _descripcion(job.get("description"))
            salario = texto_salario(
                job.get("salary_min"), job.get("salary_max"), "USD", "anual"
            )

            ofertas.append(
                JobRaw(
                    source_id=self.id,
                    external_id=str(job.get("id")),
                    url=str(job.get("url") or ""),
                    title=titulo,
                    company=_limpio(job.get("company")),
                    location=ubicacion,
                    description=descripcion,
                    summary=_resumen(descripcion),
                    salary_text=salario,
                    published_text=_limpio(job.get("date")),
                    modality_hint="Remoto",
                )
            )
        return ofertas


class HimalayasConnector(_ConectorAPI):
    id = "himalayas"
    nombre = "Himalayas"
    url = "https://himalayas.app/jobs/api"

    async def buscar(
        self, client: httpx.AsyncClient, consulta: str, pagina: int = 1
    ) -> list[JobRaw]:
        ofertas: list[JobRaw] = []
        vistos: set[str] = set()

        for indice in range(PAGINAS_HIMALAYAS):
            respuesta = await client.get(
                self.url,
                params={"limit": TAMANO_HIMALAYAS, "offset": indice * TAMANO_HIMALAYAS},
            )
            respuesta.raise_for_status()
            jobs = (respuesta.json() or {}).get("jobs") or []
            if not jobs:
                break
            for oferta in self._parsear(jobs):
                if oferta.external_id not in vistos:
                    vistos.add(oferta.external_id)
                    ofertas.append(oferta)
            if len(jobs) < TAMANO_HIMALAYAS:
                break

        return ofertas

    def _parsear(self, jobs: list[dict]) -> list[JobRaw]:
        ofertas: list[JobRaw] = []
        for job in jobs:
            titulo = _limpio(job.get("title")) or "(sin título)"
            if not _es_it(titulo):
                continue
            ubicacion = job.get("locationRestrictions") or []
            if not aceptar_ubicacion(ubicacion):
                continue

            descripcion = _descripcion(job.get("description"))
            salario = texto_salario(
                job.get("minSalary"),
                job.get("maxSalary"),
                job.get("currency"),
                job.get("salaryPeriod"),
            )
            guid = str(job.get("guid") or job.get("applicationLink") or "")

            ofertas.append(
                JobRaw(
                    source_id=self.id,
                    external_id=guid or _limpio(job.get("title")) or "",
                    url=guid,
                    title=titulo,
                    company=_limpio(job.get("companyName")),
                    location=", ".join(str(x) for x in ubicacion) if ubicacion else "Worldwide",
                    description=descripcion,
                    summary=_limpio(job.get("excerpt")) or _resumen(descripcion),
                    salary_text=salario,
                    published_text=str(job.get("pubDate") or "") or None,
                    contract_type=_limpio(job.get("employmentType")),
                    modality_hint="Remoto",
                )
            )
        return ofertas


class JobicyConnector(_ConectorAPI):
    id = "jobicy"
    nombre = "Jobicy"
    url = "https://jobicy.com/api/v2/remote-jobs"

    async def buscar(
        self, client: httpx.AsyncClient, consulta: str, pagina: int = 1
    ) -> list[JobRaw]:
        respuesta = await client.get(self.url, params={"count": 100})
        respuesta.raise_for_status()
        datos = respuesta.json() or {}
        return self._parsear(datos.get("jobs") or [])

    def _parsear(self, jobs: list[dict]) -> list[JobRaw]:
        ofertas: list[JobRaw] = []
        for job in jobs:
            titulo = _limpio(job.get("jobTitle")) or "(sin título)"
            if not _es_it(titulo):
                continue
            ubicacion = _limpio(job.get("jobGeo"))
            if not aceptar_ubicacion(ubicacion):
                continue

            descripcion = _descripcion(job.get("jobDescription"))
            salario = texto_salario(
                job.get("salaryMin"),
                job.get("salaryMax"),
                job.get("salaryCurrency"),
                job.get("salaryPeriod"),
            )
            tipos = job.get("jobType")
            if isinstance(tipos, list):
                contrato = " · ".join(str(t) for t in tipos if t) or None
            else:
                contrato = _limpio(tipos)

            ofertas.append(
                JobRaw(
                    source_id=self.id,
                    external_id=str(job.get("id") or job.get("jobSlug") or job.get("url")),
                    url=str(job.get("url") or ""),
                    title=titulo,
                    company=_limpio(job.get("companyName")),
                    location=ubicacion,
                    description=descripcion,
                    summary=_limpio(job.get("jobExcerpt")) or _resumen(descripcion),
                    salary_text=salario,
                    published_text=_limpio(job.get("pubDate")),
                    contract_type=contrato,
                    modality_hint="Remoto",
                )
            )
        return ofertas
