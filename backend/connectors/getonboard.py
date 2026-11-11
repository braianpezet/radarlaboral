# -*- coding: utf-8 -*-
"""Conector de GetOnBoard (HTML público, solo lectura).

GetOnBoard es un portal tech de Latam. El listado se recorre por categorías
(no por texto libre) y cada tarjeta ya trae título, empresa, ubicación,
modalidad, salario y fecha. La descripción completa se pide bajo demanda.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

from ..config import HEADERS
from ..services.text import normalizar
from .base import JobRaw

# Categorías relevantes para el perfil (slugs de GetOnBoard).
CATEGORIAS = [
    "programacion",
    "data-science-analytics",
    "sysadmin-devops-qa",
    "desarrollo-mobile",
]

# Ubicaciones que no sirven para Argentina (presencial/híbrido en otro país).
_UBICACION_AR = re.compile(
    r"argentin|buenos aires|caba|capital federal|gba|gran buenos aires|"
    r"cordoba|rosario|mendoza|la plata|mar del plata|tucuman|salta|neuquen"
)
_REMOTO = re.compile(r"\bremoto\b|\bremote\b")


_RUIDO = re.compile(
    r"^(oferta exclusiva de getonbrd\.com\.?|"
    r"aplica directamente en el sitio original en get on board\.?|"
    r"postula sin intermediarios a través de get on board\.?|"
    r"encuentra esta vacante en get on board\.?|"
    r"este empleo es publicado por getonbrd\.com\.?)$",
    re.I,
)


class GetOnBoardConnector:
    id = "getonboard"
    nombre = "GetOnBoard"
    base = "https://www.getonbrd.com"
    busquedas = CATEGORIAS

    def cliente(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=HEADERS,
            timeout=httpx.Timeout(40.0, connect=15.0),
            follow_redirects=True,
        )

    async def buscar(
        self, client: httpx.AsyncClient, consulta: str, pagina: int = 1
    ) -> list[JobRaw]:
        url = f"{self.base}/empleos/{consulta}"
        respuesta = await client.get(url)
        respuesta.raise_for_status()
        return self._parsear_listado(respuesta.text)

    # ------------------------------------------------------------------ listado
    def _parsear_listado(self, html: str) -> list[JobRaw]:
        soup = BeautifulSoup(html, "lxml")
        ofertas: list[JobRaw] = []
        vistos: set[str] = set()

        for enlace in soup.select("a.results-item[href]"):
            url = urljoin(self.base, enlace["href"])
            partes = urlsplit(url)
            if "/empleos/" not in partes.path and "/jobs/" not in partes.path:
                continue

            slug = partes.path.rstrip("/").split("/")[-1]
            if not slug or slug in vistos:
                continue
            vistos.add(slug)

            info = enlace.select_one(".results-list-info")
            if not info:
                continue

            titulo_el = info.select_one("h4.results-list-title strong")
            if not titulo_el:
                continue
            titulo = self._texto_limpio(titulo_el)
            if not titulo:
                continue

            empresa = None
            ubicacion = None
            fila = info.select_one(".size0")
            if fila:
                empresa_el = fila.find("strong")
                if empresa_el:
                    empresa = empresa_el.get_text(" ", strip=True) or None
                ubicacion = self._texto_ubicacion(fila)

            if not self._ubicacion_relevante(ubicacion):
                continue

            ofertas.append(
                JobRaw(
                    source_id=self.id,
                    external_id=slug,
                    url=url,
                    title=titulo,
                    company=empresa,
                    location=ubicacion,
                    salary_text=self._salario(enlace),
                    published_text=self._fecha(enlace),
                    contract_type=self._contrato(info),
                    modality_hint=ubicacion,
                    summary=(enlace.get("title") or "").strip().lstrip("✨").strip()
                    or None,
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

        contenedor = None
        for candidato in soup.select("div.gb-container--medium"):
            if candidato.select_one("div.mb4 .gb-rich-txt"):
                contenedor = candidato
                break

        bloques: list[str] = []
        if contenedor:
            for bloque in contenedor.find_all("div", class_="mb4", recursive=False):
                rich = bloque.select_one(".gb-rich-txt")
                if not rich:
                    continue
                cuerpo = rich.get_text("\n", strip=True)
                cuerpo = "\n".join(
                    linea
                    for linea in cuerpo.splitlines()
                    if not _RUIDO.match(linea.strip())
                ).strip()
                if not cuerpo:
                    continue
                encabezado = bloque.find(["h2", "h3", "h4"])
                titulo_seccion = (
                    encabezado.get_text(" ", strip=True) if encabezado else ""
                )
                if titulo_seccion and titulo_seccion not in cuerpo:
                    bloques.append(f"{titulo_seccion}\n{cuerpo}")
                else:
                    bloques.append(cuerpo)

            politica = self._politica_remota(contenedor)
            if politica:
                bloques.append(politica)

        contrato_el = soup.select_one('span[itemprop="employmentType"]')
        contrato = None
        if contrato_el:
            contrato = {
                "FULL_TIME": "Full time",
                "PART_TIME": "Part time",
                "CONTRACTOR": "Contrato",
                "TEMPORARY": "Temporal",
                "INTERN": "Pasantía",
            }.get(contrato_el.get_text(strip=True).upper())

        descripcion = "\n\n".join(b for b in bloques if b) or None
        return descripcion, contrato

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _texto_limpio(el) -> str:
        copia = BeautifulSoup(str(el), "lxml")
        for ruido in copia.select("i, .badge"):
            ruido.decompose()
        return re.sub(r"\s+", " ", copia.get_text(" ", strip=True)).strip()

    @staticmethod
    def _texto_ubicacion(fila) -> str | None:
        loc = fila.select_one(".location")
        if not loc:
            return None
        copia = BeautifulSoup(str(loc), "lxml")
        for tooltip in copia.select(".location-tooltip-content"):
            tooltip.decompose()
        for icono in copia.select("i"):
            icono.decompose()
        texto = re.sub(r"\s+", " ", copia.get_text(" ", strip=True)).strip()
        return texto or None

    @staticmethod
    def _ubicacion_relevante(ubicacion: str | None) -> bool:
        """Descarta presencial/híbrido fuera de Argentina; conserva remotos."""
        if not ubicacion:
            return True
        t = normalizar(ubicacion)
        if _REMOTO.search(t):
            return True
        return bool(_UBICACION_AR.search(t))

    @staticmethod
    def _salario(enlace) -> str | None:
        badges = enlace.select_one(".gb-results-list__badges")
        if not badges:
            return None
        icono = badges.select_one(".icon-money-bill")
        if not icono or not icono.parent:
            return None
        return icono.parent.get_text(" ", strip=True) or None

    @staticmethod
    def _fecha(enlace) -> str | None:
        fechas = enlace.select("div.opacity-half.size0")
        if fechas:
            return fechas[-1].get_text(" ", strip=True) or None
        return None

    @staticmethod
    def _contrato(info) -> str | None:
        el = info.select_one("h4.results-list-title .opacity-half")
        if not el:
            return None
        return el.get_text(" ", strip=True) or None

    @staticmethod
    def _politica_remota(contenedor) -> str | None:
        encabezado = contenedor.find(
            "h2", string=lambda s: s and "Política de trabajo remoto" in s
        )
        if not encabezado:
            return None
        partes: list[str] = [encabezado.get_text(" ", strip=True)]
        for hermano in encabezado.next_siblings:
            nombre = getattr(hermano, "name", None)
            if nombre in ("h1", "h2", "h3", "h4"):
                break
            if nombre not in (None, "div", "p", "span"):
                continue
            texto = (
                hermano.strip()
                if isinstance(hermano, str)
                else hermano.get_text(" ", strip=True)
            )
            if texto:
                partes.append(re.sub(r"\s+", " ", texto).strip())
        return "\n".join(partes) if len(partes) > 1 else None
