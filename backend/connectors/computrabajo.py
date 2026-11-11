# -*- coding: utf-8 -*-
"""Conector de Computrabajo Argentina (HTML público, solo lectura)."""
from __future__ import annotations

import re
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

from ..config import BUSQUEDAS, HEADERS
from .base import JobRaw


class ComputrabajoConnector:
    id = "computrabajo"
    nombre = "Computrabajo AR"
    base = "https://ar.computrabajo.com"
    busquedas = BUSQUEDAS

    def cliente(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=HEADERS,
            timeout=httpx.Timeout(30.0, connect=15.0),
            follow_redirects=True,
        )

    async def buscar(self, client: httpx.AsyncClient, consulta: str, pagina: int = 1) -> list[JobRaw]:
        url = f"{self.base}/ofertas-de-trabajo/?q={quote(consulta)}&p={pagina}"
        respuesta = await client.get(url)
        respuesta.raise_for_status()
        return self._parsear_listado(respuesta.text)

    def _parsear_listado(self, html: str) -> list[JobRaw]:
        soup = BeautifulSoup(html, "lxml")
        ofertas: list[JobRaw] = []
        for art in soup.select("article.box_offer"):
            enlace = art.select_one("h2 a.js-o-link")
            if not enlace:
                continue
            external_id = (art.get("data-id") or "").strip()
            if not external_id:
                continue

            href = enlace.get("href") or ""
            partes = urlsplit(urljoin(self.base, href))
            url = urlunsplit((partes.scheme, partes.netloc, partes.path, partes.query, ""))

            titulo = enlace.get_text(" ", strip=True)
            empresa_el = art.select_one("a[offer-grid-article-company-url]")
            empresa = empresa_el.get_text(" ", strip=True) if empresa_el else None

            ubicacion = None
            for p in art.find_all("p", class_="fs16"):
                if not p.find("a"):
                    ubicacion = p.get_text(" ", strip=True)
                    break

            salario = None
            modalidad_hint = None
            for span in art.select("div.fs13.mt15 span.dIB"):
                texto_span = span.get_text(" ", strip=True)
                if span.select_one(".i_salary"):
                    salario = texto_span
                elif modalidad_hint is None:
                    modalidad_hint = texto_span

            fecha_el = art.select_one("p.fs13.fc_aux.mt15")
            fecha = fecha_el.get_text(" ", strip=True) if fecha_el else None

            ofertas.append(JobRaw(
                source_id=self.id,
                external_id=external_id,
                url=url,
                title=titulo,
                company=empresa,
                location=ubicacion,
                salary_text=salario,
                published_text=fecha,
                modality_hint=modalidad_hint,
            ))
        return ofertas

    async def detalle(self, client: httpx.AsyncClient, url: str) -> tuple[str | None, str | None]:
        """Devuelve (descripción, contrato/jornada) de la página de la oferta."""
        respuesta = await client.get(url)
        respuesta.raise_for_status()
        soup = BeautifulSoup(respuesta.text, "lxml")

        contenedor = soup.select_one('div[div-link="oferta"]')
        if not contenedor:
            return None, None

        titulo = contenedor.find("h2")
        if titulo:
            titulo.decompose()

        etiquetas = [
            t.get_text(" ", strip=True)
            for t in contenedor.select("div.mbB span.tag")
        ]
        contrato = " · ".join(dict.fromkeys(etiquetas)) if etiquetas else None

        texto = contenedor.get_text("\n", strip=True)
        texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
        return (texto or None), contrato
