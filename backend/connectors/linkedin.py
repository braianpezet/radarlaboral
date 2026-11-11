# -*- coding: utf-8 -*-
"""Conector de LinkedIn (búsqueda pública, sin login).

Está **apagado por defecto**: los términos de uso de LinkedIn prohíben la
recolección automatizada y el sitio limita rápido (HTTP 429). Se ofrece como
fuente opcional de bajo volumen para que la persona decida activarla desde
Configuración. No usa login, cookies de sesión, proxies ni resolución de
captchas.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from ..config import BUSQUEDAS_LINKEDIN, HEADERS, PAUSA_LINKEDIN
from .base import FuenteBloqueada, JobRaw

CODIGOS_BLOQUEO = {401, 403, 429, 999}


class LinkedInConnector:
    id = "linkedin"
    nombre = "LinkedIn"
    base = "https://ar.linkedin.com"
    busquedas = BUSQUEDAS_LINKEDIN
    pausa_entre_busquedas = PAUSA_LINKEDIN
    ubicacion = "Argentina"
    max_avisos = 30

    def cliente(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=HEADERS,
            timeout=httpx.Timeout(30.0, connect=15.0),
            follow_redirects=True,
        )

    async def buscar(
        self, client: httpx.AsyncClient, consulta: str, pagina: int = 1
    ) -> list[JobRaw]:
        params = {
            "keywords": consulta,
            "location": self.ubicacion,
            "start": max(0, (pagina - 1) * 25),
        }
        respuesta = await client.get(f"{self.base}/jobs/search", params=params)
        self._verificar(respuesta)
        return self._parsear_listado(respuesta.content)

    def _verificar(self, respuesta: httpx.Response) -> None:
        if respuesta.status_code in CODIGOS_BLOQUEO:
            raise FuenteBloqueada(self.nombre, f"HTTP {respuesta.status_code}")
        respuesta.raise_for_status()
        bajo = respuesta.text.lower()
        if "authwall" in bajo:
            raise FuenteBloqueada(self.nombre, "pidió iniciar sesión")

    def _parsear_listado(self, html) -> list[JobRaw]:
        soup = BeautifulSoup(html, "lxml")
        ofertas: list[JobRaw] = []
        vistos: set[str] = set()
        tarjetas = soup.select(".jobs-search__results-list li") or soup.select("li")

        for tarjeta in tarjetas:
            if len(ofertas) >= self.max_avisos:
                break
            enlace = tarjeta.select_one("a.base-card__full-link") or tarjeta.select_one(
                "a[href*='/jobs/view/']"
            )
            if not enlace:
                continue
            href = urljoin(self.base, enlace.get("href") or "").split("?")[0]
            if "/jobs/view/" not in href:
                continue

            external_id = self._external_id(href, tarjeta)
            if not external_id or external_id in vistos:
                continue
            vistos.add(external_id)

            titulo = self._texto(tarjeta, "h3.base-search-card__title")
            if not titulo:
                continue
            empresa = self._texto(tarjeta, "h4.base-search-card__subtitle")
            ubicacion = self._texto(tarjeta, ".job-search-card__location")
            salario = self._texto(tarjeta, ".job-search-card__salary-info")

            fecha_el = tarjeta.select_one("time")
            fecha = None
            if fecha_el:
                fecha = fecha_el.get("datetime") or fecha_el.get_text(" ", strip=True)

            ofertas.append(
                JobRaw(
                    source_id=self.id,
                    external_id=external_id,
                    url=href,
                    title=titulo,
                    company=empresa,
                    location=ubicacion,
                    salary_text=salario,
                    published_text=fecha,
                    modality_hint=ubicacion,
                )
            )
        return ofertas

    @staticmethod
    def _texto(tarjeta, selector: str) -> str | None:
        el = tarjeta.select_one(selector)
        if not el:
            return None
        texto = el.get_text(" ", strip=True)
        return texto or None

    @staticmethod
    def _external_id(href: str, tarjeta) -> str | None:
        urn = tarjeta.select_one("[data-entity-urn]")
        if urn:
            encontrado = re.search(r"(\d{6,})", urn.get("data-entity-urn") or "")
            if encontrado:
                return encontrado.group(1)
        path = urlsplit(href).path.rstrip("/")
        encontrado = re.search(r"-(\d{6,})$", path) or re.search(r"/(\d{6,})$", path)
        return encontrado.group(1) if encontrado else None

    async def detalle(
        self, client: httpx.AsyncClient, url: str
    ) -> tuple[str | None, str | None]:
        """Descripción pública del aviso, solo cuando la persona lo abre."""
        respuesta = await client.get(url)
        if respuesta.status_code in CODIGOS_BLOQUEO:
            raise FuenteBloqueada(self.nombre, f"HTTP {respuesta.status_code}")
        respuesta.raise_for_status()

        soup = BeautifulSoup(respuesta.content, "lxml")
        contenedor = soup.select_one(".show-more-less-html__markup") or soup.select_one(
            ".description__text"
        )
        if not contenedor:
            return None, None
        texto = contenedor.get_text("\n", strip=True)
        texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
        return (texto or None), None
