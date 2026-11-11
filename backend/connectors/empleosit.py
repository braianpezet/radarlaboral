# -*- coding: utf-8 -*-
"""Conector de Empleos IT (Argentina, HTML público, solo lectura).

El listado se recorre por categorías; cada tarjeta trae título, empresa,
ubicación y fecha. La descripción completa y la modalidad se piden bajo
demanda desde la página del aviso.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from ..config import CATEGORIAS_EMPLEOSIT, EMPLEOSIT_POR_PAGINA, HEADERS
from ..services.text import html_a_texto, aceptar_ubicacion
from .base import JobRaw

_RUIDO_BRIEF = re.compile(r"^\s*descripci[oó]n del empleo\s*:\s*", re.I)


class EmpleosITConnector:
    id = "empleosit"
    nombre = "Empleos IT"
    base = "https://www.empleosit.com.ar"
    busquedas = CATEGORIAS_EMPLEOSIT

    def cliente(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=HEADERS,
            timeout=httpx.Timeout(40.0, connect=15.0),
            follow_redirects=True,
        )

    async def buscar(
        self, client: httpx.AsyncClient, consulta: str, pagina: int = 1
    ) -> list[JobRaw]:
        url = (
            f"{self.base}/categoria/{consulta}/"
            f"?view=list&listings_per_page={EMPLEOSIT_POR_PAGINA}&page={pagina}"
        )
        respuesta = await client.get(url)
        respuesta.raise_for_status()
        return self._parsear_listado(respuesta.text)

    # ------------------------------------------------------------------ listado
    def _parsear_listado(self, html: str) -> list[JobRaw]:
        soup = BeautifulSoup(html, "lxml")
        ofertas: list[JobRaw] = []
        vistos: set[str] = set()

        for tarjeta in soup.select("div.listing-section"):
            enlace = tarjeta.select_one('div.listing-title a[href*="display-job"]')
            if not enlace:
                continue

            url = urljoin(self.base, enlace["href"])
            partes = urlsplit(url)
            coincidencia = re.search(r"/display-job/(\d+)/", partes.path)
            external_id = coincidencia.group(1) if coincidencia else partes.path
            if not external_id or external_id in vistos:
                continue
            vistos.add(external_id)

            titulo = enlace.get_text(" ", strip=True)
            if not titulo:
                continue

            ubicacion = self._texto(tarjeta.select_one(".location-ico"))
            if not aceptar_ubicacion(ubicacion):
                continue

            fecha = self._texto(tarjeta.select_one(".posted-ico"))
            resumen = self._texto(tarjeta.select_one(".show-brief"))
            if resumen:
                resumen = _RUIDO_BRIEF.sub("", resumen).strip() or None

            ofertas.append(
                JobRaw(
                    source_id=self.id,
                    external_id=external_id,
                    url=url.split("?")[0],
                    title=titulo,
                    company=self._texto(tarjeta.select_one(".company-ico a"))
                    or self._texto(tarjeta.select_one(".company-ico")),
                    location=ubicacion,
                    summary=resumen,
                    published_text=fecha,
                    modality_hint=ubicacion,
                )
            )

        return ofertas

    # ------------------------------------------------------------------ detalle
    async def detalle(
        self, client: httpx.AsyncClient, url: str
    ) -> tuple[str | None, str | None]:
        respuesta = await client.get(url)
        respuesta.raise_for_status()
        soup = BeautifulSoup(respuesta.text, "lxml")

        info = soup.select_one("div.listingInfo")
        if not info:
            return None, None

        campos: dict[str, str] = {}
        for bloque in info.select("div.displayFieldBlock"):
            encabezado = bloque.find(["h3", "h2"])
            if not encabezado:
                continue
            clave = encabezado.get_text(" ", strip=True).rstrip(":").strip()
            valor = self._texto(bloque.select_one(".displayField"))
            if clave and valor and clave not in campos:
                campos[clave] = valor

        descripcion = None
        contenedor_desc = info.select_one("#col-wide .displayField")
        if contenedor_desc:
            descripcion = html_a_texto(str(contenedor_desc))
        if not descripcion:
            for clave, valor in campos.items():
                if "descripci" in clave.lower():
                    descripcion = valor
                    break

        ficha: list[str] = []
        etiquetas = (
            ("Ubicación", "Ubicación"),
            ("Categoría", "Categoría"),
            ("Modalidad de trabajo", "Modalidad"),
            ("Tipo de Trabajo", "Tipo de trabajo"),
            ("Publicado", "Publicado"),
        )
        for origen, destino in etiquetas:
            valor = campos.get(origen)
            if valor:
                ficha.append(f"{destino}: {valor}")

        partes = []
        if ficha:
            partes.append("\n".join(ficha))
        if descripcion:
            partes.append(descripcion)

        contrato = " · ".join(
            valor
            for valor in (campos.get("Modalidad de trabajo"), campos.get("Tipo de Trabajo"))
            if valor
        ) or None

        return ("\n\n".join(partes) or None), contrato

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _texto(el) -> str | None:
        if el is None:
            return None
        texto = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
        return texto or None
