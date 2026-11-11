# -*- coding: utf-8 -*-
"""Conector de BuscoJobs Argentina (HTML público con datos Next.js).

El portal está detrás de un WAF de AWS. Se lee el JSON incrustado en
``__NEXT_DATA__`` con un ritmo muy lento y sin navegador. Si aparece el
desafío anti-bot se lanza :class:`FuenteBloqueada` y la ingesta detiene la
fuente; no se intenta resolverlo automáticamente.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from urllib.parse import urljoin

import httpx

from ..config import BUSQUEDAS_BUSCOJOBS, HEADERS, PAUSA_BUSCOJOBS
from ..services.text import normalizar
from .base import FuenteBloqueada, JobRaw
from .filtros import es_relevante

_NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S
)
_CODIGO_BLOQUEO = (403, 405, 429)
_MARCAS_BLOQUEO = (
    "human verification",
    "aws-waf",
)


def _next_data(html: str) -> dict | None:
    """Extrae y decodifica el JSON de Next.js incrustado en la página."""
    encontrado = _NEXT_DATA.search(html)
    if not encontrado:
        return None
    try:
        return json.loads(encontrado.group(1))
    except (json.JSONDecodeError, ValueError):
        return None


def _texto(valor) -> str | None:
    if valor is None:
        return None
    texto = html_lib.unescape(str(valor))
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto or None


def _nombre(valor) -> str | None:
    """Nombre de una ciudad/departamento/pais, que puede venir como dict."""
    if isinstance(valor, dict):
        return _texto(valor.get("Nombre") or valor.get("Descripcion"))
    return _texto(valor)


def _descripcion(valor) -> str | None:
    """Descripción conservando saltos de línea (sin colapsar párrafos)."""
    if not valor:
        return None
    texto = html_lib.unescape(str(valor))
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip() or None


def _resumen(texto: str | None, largo: int = 240) -> str | None:
    plano = _texto(texto)
    if not plano:
        return None
    if len(plano) <= largo:
        return plano
    corte = plano[:largo].rsplit(" ", 1)[0]
    return f"{corte}…"


def _slug_busqueda(consulta: str) -> str:
    """'machine learning' -> 'machine-learning'; el slug usa guiones."""
    base = re.sub(r"[^a-z0-9]+", "-", normalizar(consulta))
    return base.strip("-")


# BuscoJobs mezcla "programador" de software con programadores industriales.
# El filtro compartido descarta los títulos claramente industriales salvo que
# también traigan una señal tecnológica fuerte.


class BuscoJobsConnector:
    id = "buscojobs"
    nombre = "BuscoJobs AR"
    base = "https://www.buscojobs.com.ar"
    busquedas = BUSQUEDAS_BUSCOJOBS
    pausa_entre_busquedas = PAUSA_BUSCOJOBS

    def cliente(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=HEADERS,
            timeout=httpx.Timeout(35.0, connect=15.0),
            follow_redirects=True,
        )

    async def buscar(
        self, client: httpx.AsyncClient, consulta: str, pagina: int = 1
    ) -> list[JobRaw]:
        slug = _slug_busqueda(consulta)
        if not slug:
            return []
        url = f"{self.base}/ofertas/{slug}_"
        if pagina > 1:
            url = f"{url}/{pagina}"

        respuesta = await client.get(url)
        self._verificar_bloqueo(respuesta)
        if respuesta.status_code == 404:
            return []
        respuesta.raise_for_status()

        data = _next_data(respuesta.text)
        if not data:
            return []
        page_props = (data.get("props") or {}).get("pageProps") or {}
        resultados = page_props.get("resultadosIniciales") or {}
        ofertas = resultados.get("ofertas") or []
        urls = self._urls_por_id(respuesta.text)

        salida: list[JobRaw] = []
        for oferta in ofertas:
            if not isinstance(oferta, dict):
                continue
            job = self._mapear(oferta, urls)
            if job is not None:
                salida.append(job)
        return salida

    def _mapear(self, oferta: dict, urls: dict[str, str]) -> JobRaw | None:
        external_id = str(oferta.get("IdOferta") or "").strip()
        titulo = _texto(oferta.get("CargoVacante"))
        if not external_id or not titulo or not es_relevante(titulo):
            return None

        url = urls.get(external_id)
        if not url:
            url = self._url_detalle(oferta, external_id)

        empresa = None
        if str(oferta.get("Confidencial") or 0) not in ("1", "True", "true"):
            empresa = _nombre(oferta.get("NombreEmpresa")) or _nombre(
                oferta.get("Empresa")
            )

        ubicacion = self._ubicacion(oferta)

        modalidad = None
        if oferta.get("PermiteTeletrabajo"):
            modalidad = "Teletrabajo"
        elif oferta.get("PermiteTrabajoHibrido"):
            modalidad = "Híbrido"

        return JobRaw(
            source_id=self.id,
            external_id=external_id,
            url=url,
            title=titulo,
            company=empresa,
            location=ubicacion,
            description=None,  # el detalle completo se pide bajo demanda
            summary=_resumen(oferta.get("Descripcion")),
            published_text=_texto(oferta.get("FechaInicio")),
            modality_hint=modalidad,
        )

    @staticmethod
    def _ubicacion(oferta: dict) -> str | None:
        ciudad = _nombre(oferta.get("Ciudad"))
        departamento = _nombre(oferta.get("Departamento"))
        pais = _nombre(oferta.get("Pais"))

        partes: list[str] = []
        if ciudad:
            partes.append(ciudad)
        if departamento and departamento != ciudad:
            partes.append(departamento)
        if not partes and pais:
            partes.append(pais)
        return ", ".join(partes) or None

    @staticmethod
    def _url_detalle(oferta: dict, external_id: str) -> str:
        """Arma la URL cuando el listado no trae el enlace (fallback)."""
        titulo = normalizar(_texto(oferta.get("CargoVacante")))
        ciudad = normalizar(_nombre(oferta.get("Ciudad")))
        partes = [
            re.sub(r"[^a-z0-9]+", "-", parte).strip("-")
            for parte in (titulo, ciudad)
            if parte
        ]
        slug = "-en-".join(parte for parte in partes if parte)
        if not slug:
            slug = "oferta"
        return f"https://www.buscojobs.com.ar/{slug}-ID-{external_id}"

    def _urls_por_id(self, html: str) -> dict[str, str]:
        """Mapea IdOferta -> URL usando los enlaces reales del listado."""
        mapa: dict[str, str] = {}
        for ruta, ident in re.findall(
            r'href="(/[^"]*-ID-(\d+))"', html, re.I
        ):
            mapa.setdefault(ident, urljoin(self.base, ruta))
        return mapa

    def _verificar_bloqueo(self, respuesta: httpx.Response) -> None:
        if respuesta.status_code in _CODIGO_BLOQUEO:
            raise FuenteBloqueada(self.id, f"HTTP {respuesta.status_code}")

        muestra = respuesta.text[:5000].lower()
        if any(marca in muestra for marca in _MARCAS_BLOQUEO):
            raise FuenteBloqueada(self.id, "desafío anti-bot")

    async def detalle(
        self, client: httpx.AsyncClient, url: str
    ) -> tuple[str | None, str | None]:
        """Devuelve (descripción, tipo de contrato) del aviso."""
        respuesta = await client.get(url)
        self._verificar_bloqueo(respuesta)
        respuesta.raise_for_status()

        data = _next_data(respuesta.text)
        if not data:
            return None, None
        page_props = (data.get("props") or {}).get("pageProps") or {}
        oferta = page_props.get("oferta") or {}
        if not isinstance(oferta, dict):
            return None, None

        descripcion = _descripcion(oferta.get("Descripcion"))
        contrato = oferta.get("TipoContrato")
        contrato = _texto(contrato) if isinstance(contrato, str) else None

        # Ficha útil del detalle, sin inventar moneda ni formato de sueldo.
        extras: list[str] = []
        for etiqueta, clave in (
            ("Ubicación", "Ciudad"),
            ("Modalidad", "TipoTrabajo"),
        ):
            valor = _nombre(oferta.get(clave))
            if valor:
                extras.append(f"{etiqueta}: {valor}")

        partes = [descripcion] if descripcion else []
        if extras:
            partes.append("\n".join(extras))
        return ("\n\n".join(partes) or None), contrato
