# -*- coding: utf-8 -*-
"""Portales de empresas con ATS públicos (Lever, Greenhouse y Ashby).

Cada board se consulta por su API JSON oficial, sin scraping de HTML ni
credenciales. Se conservan solo avisos de Argentina o remotos LatAm/globales,
con roles afines a los perfiles de la app (IT, datos, producto, soporte técnico
y docencia). La lista de empresas vive en ``config.ATS_EMPRESAS`` y se puede
ampliar sin tocar este archivo.
"""
from __future__ import annotations

import html as html_lib
import re
from datetime import datetime, timedelta, timezone

import httpx

from ..config import ATS_EMPRESAS, DIAS_RETENCION, HEADERS
from ..services.text import (
    detectar_modalidad,
    html_a_texto,
    limpiar_descripcion,
    normalizar,
    parsear_fecha,
    reparar_mojibake,
    texto_salario,
)
from .base import FuenteBloqueada, JobRaw

# Zonas que interesan: Argentina, remoto LatAm explícito y remoto global.
# No alcanza con que la ubicación sea LatAm: una sede presencial en México o
# Brasil no sirve, y un remoto limitado a un solo país tampoco.
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
_SOLO_REMOTO = re.compile(r"^(remote|remoto|remote only|fully remote)$")

# Roles que sí encajan con P1–P5. Es más estricto que el filtro genérico de
# los boards remotos: acá no sirve cualquier título con "analyst" o "support".
_ROL = re.compile(
    r"\b(developer|software|engineer|engineering|programmer|programador|"
    r"desarrollador|full ?stack|front ?end|back ?end|backend|frontend|"
    r"data|datos|machine learning|\bml\b|artificial intelligence|"
    r"inteligencia artificial|python|java|javascript|typescript|react|"
    r"angular|vue|node|php|ruby|golang|rust|devops|\bsre\b|cloud|aws|"
    r"azure|gcp|kubernetes|docker|\bqa\b|quality assurance|tester|testing|"
    r"business analyst|functional analyst|analista funcional|"
    r"analista de sistemas|analista tecnico|analista qa|qa analyst|"
    r"data analyst|analista de datos|product owner|project manager|"
    r"scrum master|product manager|technical support|it support|"
    r"help ?desk|service desk|soporte tecnico|sysadmin|system administrator|"
    r"administrador de sistemas|infrastructure|infraestructura|network|"
    r"redes|security|seguridad|cybersecurity|ciberseguridad|architect|"
    r"arquitecto|tech lead|technical lead|\bcto\b|computer|computacion|"
    r"sistemas|docente|profesor|tutor|capacitador|instructor|teacher)\b"
)
_NO_ROL = re.compile(
    r"\b(ventas|sales|comercial|business development|desarrollador de negocios|"
    r"marketing|growth|recruiter|recruiting|talent|finance|financial|"
    r"contable|accounting|payroll|legal|abogado|customer success|"
    r"customer project manager|support specialist|asistente|administrativo|"
    r"deposito|almacen|warehouse|logistica|logistics)\b"
)


def _texto(valor) -> str | None:
    if valor is None:
        return None
    texto = reparar_mojibake(str(valor)) or ""
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


def _ubicaciones(valores) -> str | None:
    """Une location + allLocations/secondaryLocations sin repetir."""
    partes: list[str] = []
    for valor in valores:
        if isinstance(valor, (list, tuple)):
            partes.extend(str(x).strip() for x in valor if x)
        elif valor:
            partes.append(str(valor).strip())
    vistas: set[str] = set()
    salida: list[str] = []
    for parte in partes:
        clave = normalizar(parte)
        if clave and clave not in vistas:
            vistas.add(clave)
            salida.append(parte)
    return ", ".join(salida) or None


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


def _es_rol(titulo: str | None) -> bool:
    t = normalizar(titulo)
    if not t or _NO_ROL.search(t):
        return False
    return bool(_ROL.search(t))


def _fecha(valor) -> str | None:
    """Normaliza epoch en milisegundos (Lever) o ISO (Greenhouse/Ashby)."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        segundos = valor / 1000 if valor > 100_000_000_000 else valor
        try:
            return datetime.fromtimestamp(segundos, tz=timezone.utc).isoformat(
                timespec="seconds"
            )
        except (ValueError, OSError):
            return None
    return _texto(valor)


def _vigente(publicado: str | None) -> bool:
    """Descarta avisos que la limpieza de retención borraría igual."""
    fecha = parsear_fecha(publicado)
    if fecha is None:
        return True
    return fecha >= datetime.now(timezone.utc) - timedelta(days=DIAS_RETENCION)


def _descripcion_plana(html: str | None) -> str | None:
    if not html:
        return None
    return limpiar_descripcion(html_a_texto(html_lib.unescape(str(html))))


def _descripcion_lever(job: dict) -> str | None:
    partes = [
        _texto(job.get("descriptionPlain")) or _descripcion_plana(job.get("description"))
    ]
    for lista in job.get("lists") or []:
        encabezado = _texto(lista.get("text"))
        contenido = _descripcion_plana(lista.get("content")) or _texto(
            lista.get("content")
        )
        if encabezado:
            partes.append(encabezado)
        if contenido:
            partes.append(contenido)
    return limpiar_descripcion("\n\n".join(p for p in partes if p))


def _descripcion_ashby(job: dict) -> str | None:
    return limpiar_descripcion(
        _texto(job.get("descriptionPlain"))
        or _descripcion_plana(job.get("descriptionHtml"))
    )


def _salario_lever(job: dict) -> str | None:
    rango = job.get("salaryRange") or {}
    if not isinstance(rango, dict):
        return None
    if not (rango.get("min") or rango.get("max")):
        return None
    return texto_salario(
        rango.get("min"), rango.get("max"), rango.get("currency"), rango.get("interval")
    )


class EmpresasConnector:
    """Un board por consulta, para que un error no corte las demás empresas."""

    id = "empresas"
    nombre = "Empresas (ATS)"
    pausa_entre_busquedas = 1.0

    def __init__(self) -> None:
        self._boards = {
            (board["ats"], board["token"]): board["nombre"] for board in ATS_EMPRESAS
        }
        self.busquedas = [
            f"{board['ats']}:{board['token']}" for board in ATS_EMPRESAS
        ]

    def cliente(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={**HEADERS, "Accept": "application/json"},
            timeout=httpx.Timeout(90.0, connect=15.0),
            follow_redirects=True,
        )

    async def _pedir(self, client: httpx.AsyncClient, url: str) -> dict | list:
        respuesta = await client.get(url)
        if respuesta.status_code in (403, 429):
            raise FuenteBloqueada(
                self.nombre, f"HTTP {respuesta.status_code} en {url}"
            )
        respuesta.raise_for_status()
        return respuesta.json()

    async def buscar(
        self, client: httpx.AsyncClient, consulta: str, pagina: int = 1
    ) -> list[JobRaw]:
        ats, _, token = consulta.partition(":")
        if not token:
            return []
        if ats == "lever":
            return await self._lever(client, token)
        if ats == "greenhouse":
            return await self._greenhouse(client, token)
        if ats == "ashby":
            return await self._ashby(client, token)
        return []

    async def _lever(self, client: httpx.AsyncClient, token: str) -> list[JobRaw]:
        datos = await self._pedir(
            client, f"https://api.lever.co/v0/postings/{token}?mode=json"
        )
        if not isinstance(datos, list):
            return []

        ofertas: list[JobRaw] = []
        for job in datos:
            categorias = job.get("categories") or {}
            ubicacion = _ubicaciones(
                [categorias.get("location"), categorias.get("allLocations")]
            )
            remoto = (job.get("workplaceType") or "").lower() == "remote"
            titulo = _texto(job.get("text")) or "(sin título)"
            if not _zona_aceptada(ubicacion, remoto) or not _es_rol(titulo):
                continue
            publicado = _fecha(job.get("createdAt"))
            if not _vigente(publicado):
                continue

            descripcion = _descripcion_lever(job)
            ofertas.append(
                JobRaw(
                    source_id=self.id,
                    external_id=f"lever:{token}:{job.get('id')}",
                    url=str(job.get("hostedUrl") or job.get("applyUrl") or ""),
                    title=titulo,
                    company=self._boards.get(("lever", token)),
                    location=ubicacion,
                    description=descripcion,
                    summary=_resumen(descripcion),
                    salary_text=_salario_lever(job),
                    published_text=publicado,
                    contract_type=_texto(categorias.get("commitment")),
                    modality_hint=detectar_modalidad(
                        "Remoto" if remoto else job.get("workplaceType")
                    ),
                )
            )
        return ofertas

    async def _greenhouse(
        self, client: httpx.AsyncClient, token: str
    ) -> list[JobRaw]:
        datos = await self._pedir(
            client,
            f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true",
        )
        if not isinstance(datos, dict):
            return []

        ofertas: list[JobRaw] = []
        for job in datos.get("jobs") or []:
            ubicacion = _texto((job.get("location") or {}).get("name"))
            remoto = "remote" in normalizar(ubicacion)
            titulo = _texto(job.get("title")) or "(sin título)"
            if not _zona_aceptada(ubicacion, remoto) or not _es_rol(titulo):
                continue
            publicado = _fecha(
                job.get("first_published") or job.get("updated_at")
            )
            if not _vigente(publicado):
                continue

            descripcion = _descripcion_plana(job.get("content"))
            ofertas.append(
                JobRaw(
                    source_id=self.id,
                    external_id=f"greenhouse:{token}:{job.get('id')}",
                    url=str(job.get("absolute_url") or ""),
                    title=titulo,
                    company=_texto(job.get("company_name"))
                    or self._boards.get(("greenhouse", token)),
                    location=ubicacion,
                    description=descripcion,
                    summary=_resumen(descripcion),
                    published_text=publicado,
                    modality_hint=detectar_modalidad(f"{titulo} {ubicacion}"),
                )
            )
        return ofertas

    async def _ashby(self, client: httpx.AsyncClient, token: str) -> list[JobRaw]:
        datos = await self._pedir(
            client,
            "https://api.ashbyhq.com/posting-api/job-board/"
            f"{token}?includeCompensation=true",
        )
        if not isinstance(datos, dict):
            return []

        ofertas: list[JobRaw] = []
        for job in datos.get("jobs") or []:
            secundarias = job.get("secondaryLocations") or []
            ubicacion = _ubicaciones(
                [job.get("location")]
                + [x.get("location") for x in secundarias if x.get("location")]
            )
            remoto = bool(job.get("isRemote"))
            titulo = _texto(job.get("title")) or "(sin título)"
            if not _zona_aceptada(ubicacion, remoto) or not _es_rol(titulo):
                continue
            publicado = _fecha(job.get("publishedAt"))
            if not _vigente(publicado):
                continue

            descripcion = _descripcion_ashby(job)
            compensacion = job.get("compensation") or {}
            ofertas.append(
                JobRaw(
                    source_id=self.id,
                    external_id=f"ashby:{token}:{job.get('id')}",
                    url=str(job.get("jobUrl") or job.get("applyUrl") or ""),
                    title=titulo,
                    company=self._boards.get(("ashby", token)),
                    location=ubicacion,
                    description=descripcion,
                    summary=_resumen(descripcion),
                    salary_text=_texto(
                        compensacion.get("compensationTierSummary")
                    ),
                    published_text=publicado,
                    contract_type=_texto(job.get("employmentType")),
                    modality_hint=detectar_modalidad(f"{titulo} {ubicacion}")
                    or ("Remoto" if remoto else None),
                )
            )
        return ofertas

    async def detalle(
        self, client: httpx.AsyncClient, url: str
    ) -> tuple[str | None, str | None]:
        """Descripción de respaldo cuando el listado no la trajo."""
        match = re.search(r"jobs\.lever\.co/([^/]+)/([^/?#]+)", url)
        if match:
            token, job_id = match.groups()
            datos = await self._pedir(
                client, f"https://api.lever.co/v0/postings/{token}/{job_id}"
            )
            if isinstance(datos, dict):
                return (
                    _descripcion_lever(datos),
                    _texto((datos.get("categories") or {}).get("commitment")),
                )
            return None, None

        match = re.search(r"job-boards\.greenhouse\.io/([^/]+)/jobs/(\d+)", url)
        if match:
            token, job_id = match.groups()
            datos = await self._pedir(
                client,
                f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{job_id}",
            )
            if isinstance(datos, dict):
                return _descripcion_plana(datos.get("content")), None
            return None, None

        match = re.search(r"jobs\.ashbyhq\.com/([^/]+)/([^/?#]+)", url)
        if match:
            token, job_id = match.groups()
            datos = await self._pedir(
                client, "https://api.ashbyhq.com/posting-api/job-board/" + token
            )
            if isinstance(datos, dict):
                for job in datos.get("jobs") or []:
                    if str(job.get("id")) == job_id:
                        return (
                            _descripcion_ashby(job),
                            _texto(job.get("employmentType")),
                        )
        return None, None
