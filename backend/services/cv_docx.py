# -*- coding: utf-8 -*-
"""Importación y generación de CV en Word (.docx).

La plantilla es el propio archivo que sube la persona: se conservan la página,
los márgenes, la cabecera (nombre y contacto) y los formatos de los párrafos.
El contenido adaptado se vuelca con esos mismos formatos, sin inventar datos.
"""
from __future__ import annotations

import io
import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass, field

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

MAX_BYTES = 5 * 1024 * 1024

# Claves de sección y las palabras que las identifican en la plantilla.
SECCIONES = {
    "perfil": ("PERFIL", "RESUMEN", "OBJETIVO", "SOBRE MI", "ACERCA"),
    "experiencia": ("EXPERIENCIA", "TRAYECTORIA", "TRABAJO"),
    "educacion": ("EDUCACION", "FORMACION", "ESTUDIOS"),
    "habilidades": (
        "HABILIDADES",
        "SKILLS",
        "CONOCIMIENTOS",
        "TECNOLOGIAS",
        "COMPETENCIAS",
    ),
    "idiomas": ("IDIOMAS", "LENGUAS"),
}

TITULOS_POR_DEFECTO = {
    "perfil": "PERFIL PROFESIONAL",
    "experiencia": "EXPERIENCIA LABORAL",
    "educacion": "EDUCACIÓN",
    "habilidades": "HABILIDADES",
    "idiomas": "IDIOMAS",
}


class PlantillaError(Exception):
    """El archivo de Word no se puede leer o no sirve como plantilla."""


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFD", texto)
    sin_tildes = "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z0-9 ]+", " ", sin_tildes.upper()).strip()


def _clave_heading(linea: str) -> str | None:
    normal = _normalizar(linea)
    if not normal or len(normal) > 60:
        return None
    for clave, palabras in SECCIONES.items():
        for palabra in palabras:
            if normal == palabra or normal.startswith(palabra + " "):
                return clave
            if normal.endswith(" " + palabra):
                return clave
    return None


def _primera_linea(parrafo) -> str:
    for linea in (parrafo.text or "").split("\n"):
        if linea.strip():
            return linea.strip()
    return ""


def _abrir(contenido: bytes) -> Document:
    if not contenido:
        raise PlantillaError("El archivo está vacío.")
    if len(contenido) > MAX_BYTES:
        raise PlantillaError("El Word supera los 5 MB; usá un archivo más chico.")
    if not contenido.startswith(b"PK"):
        raise PlantillaError(
            "El archivo no parece un .docx. Guardalo desde Word como «Documento de Word (.docx)»."
        )
    if b"vbaProject.bin" in contenido:
        raise PlantillaError(
            "El archivo tiene macros (.docm). Guardalo como .docx sin macros y volvé a subirlo."
        )
    try:
        return Document(io.BytesIO(contenido))
    except Exception as exc:  # python-docx lanza varios tipos según el daño
        raise PlantillaError(
            "No se pudo leer el Word. Abrilo en Word, guardalo como .docx y probá de nuevo."
        ) from exc


def extraer_texto(contenido: bytes) -> str:
    """Devuelve el texto del .docx, incluidas las tablas, para revisar y adaptar."""
    doc = _abrir(contenido)
    lineas: list[str] = []
    for parrafo in doc.paragraphs:
        texto = (parrafo.text or "").replace("\xa0", " ").strip()
        if texto:
            lineas.append(texto)
    for tabla in doc.tables:
        for fila in tabla.rows:
            celdas: list[str] = []
            for celda in fila.cells:
                valor = (celda.text or "").replace("\xa0", " ").strip()
                if valor and valor not in celdas:
                    celdas.append(valor)
            if celdas:
                lineas.append(" | ".join(celdas))
    texto = re.sub(r"\n{3,}", "\n\n", "\n".join(lineas)).strip()
    if len(texto) < 40:
        raise PlantillaError(
            "El Word casi no tiene texto. Si tu CV está en imágenes o cuadros, "
            "copialo a mano en el cuadro de texto."
        )
    return texto


@dataclass
class _Prototipo:
    ppr: object | None = None
    rpr: object | None = None


@dataclass
class _Plantilla:
    doc: Document
    header: int = 0
    headings: dict[str, str] = field(default_factory=dict)
    orden: list[str] = field(default_factory=list)
    heading: _Prototipo = field(default_factory=_Prototipo)
    entry: _Prototipo = field(default_factory=_Prototipo)
    body: _Prototipo = field(default_factory=_Prototipo)
    spacer: _Prototipo = field(default_factory=_Prototipo)
    skill_label: _Prototipo = field(default_factory=_Prototipo)
    skill_items: _Prototipo = field(default_factory=_Prototipo)


def _p_pr(parrafo):
    return deepcopy(parrafo._p.pPr) if parrafo._p.pPr is not None else None


def _r_pr(run):
    return deepcopy(run._r.rPr) if run._r.rPr is not None else None


def _analizar(doc: Document) -> _Plantilla:
    parrafos = doc.paragraphs
    plantilla = _Plantilla(doc=doc)
    primer_heading = None

    for indice, parrafo in enumerate(parrafos):
        clave = _clave_heading(_primera_linea(parrafo))
        if not clave:
            continue
        plantilla.headings.setdefault(clave, _primera_linea(parrafo))
        if clave not in plantilla.orden:
            plantilla.orden.append(clave)
        if primer_heading is None:
            primer_heading = indice

    plantilla.header = (
        primer_heading if primer_heading is not None else min(2, len(parrafos))
    )

    if primer_heading is not None:
        prototipo = parrafos[primer_heading]
        plantilla.heading.ppr = _p_pr(prototipo)
        for run in prototipo.runs:
            if run.text.strip():
                plantilla.heading.rpr = _r_pr(run)
                break

    def buscar_parrafo(desde: int, predicado) -> tuple[int, object] | None:
        for posicion in range(max(0, desde), len(parrafos)):
            if predicado(parrafos[posicion]):
                return posicion, parrafos[posicion]
        return None

    indice_experiencia = next(
        (
            indice
            for indice, parrafo in enumerate(parrafos)
            if indice >= plantilla.header
            and _clave_heading(_primera_linea(parrafo)) == "experiencia"
        ),
        None,
    )
    entrada = None
    if indice_experiencia is not None:
        encontrado = buscar_parrafo(
            indice_experiencia + 1, lambda p: bool((p.text or "").strip())
        )
        if encontrado:
            indice_entrada, entrada = encontrado
            plantilla.entry.ppr = _p_pr(entrada)
            for run in entrada.runs:
                if run.text.strip():
                    plantilla.entry.rpr = _r_pr(run)
                    break

    if plantilla.entry.ppr is None:
        for parrafo in parrafos[plantilla.header :]:
            if not (parrafo.text or "").strip():
                continue
            for run in parrafo.runs:
                if run.text.strip() and run.bold:
                    plantilla.entry.ppr = _p_pr(parrafo)
                    plantilla.entry.rpr = _r_pr(run)
                    break
            if plantilla.entry.ppr is not None:
                break

    inicio_cuerpo = (indice_entrada + 1) if entrada is not None else plantilla.header
    encontrado = buscar_parrafo(
        inicio_cuerpo,
        lambda p: any(r.text.strip() and not r.bold for r in p.runs),
    )
    if encontrado:
        _, parrafo_cuerpo = encontrado
        plantilla.body.ppr = _p_pr(parrafo_cuerpo)
        for run in parrafo_cuerpo.runs:
            if run.text.strip() and not run.bold:
                plantilla.body.rpr = _r_pr(run)
                break
    else:
        for parrafo in parrafos[plantilla.header :]:
            for run in parrafo.runs:
                if run.text.strip() and not run.bold:
                    plantilla.body.ppr = _p_pr(parrafo)
                    plantilla.body.rpr = _r_pr(run)
                    break
            if plantilla.body.rpr is not None:
                break

    vacio = buscar_parrafo(
        plantilla.header, lambda p: not (p.text or "").strip()
    )
    plantilla.spacer.ppr = _p_pr(vacio[1]) if vacio else plantilla.body.ppr

    indice_habilidades = next(
        (
            indice
            for indice, parrafo in enumerate(parrafos)
            if indice >= plantilla.header
            and _clave_heading(_primera_linea(parrafo)) == "habilidades"
        ),
        None,
    )
    if indice_habilidades is not None:
        for parrafo in parrafos[indice_habilidades:]:
            runs = [run for run in parrafo.runs if run.text.strip()]
            for posicion, run in enumerate(runs):
                if run.bold and run.font.size is None:
                    plantilla.skill_label.rpr = _r_pr(run)
                    for siguiente in runs[posicion + 1 :]:
                        if not siguiente.bold:
                            plantilla.skill_items.rpr = _r_pr(siguiente)
                            break
                    break
            if plantilla.skill_label.rpr is not None:
                break

    return plantilla


def _documento_nuevo() -> Document:
    doc = Document()
    seccion = doc.sections[0]
    seccion.page_width = Cm(21)
    seccion.page_height = Cm(29.7)
    seccion.left_margin = Cm(3)
    seccion.right_margin = Cm(3)
    seccion.top_margin = Cm(1)
    seccion.bottom_margin = Cm(2.5)
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = 1
    return doc


def _parrafo(doc: Document, prototipo: _Prototipo):
    parrafo = doc.add_paragraph()
    if parrafo._p.pPr is not None:
        parrafo._p.remove(parrafo._p.pPr)
    if prototipo.ppr is not None:
        parrafo._p.insert(0, deepcopy(prototipo.ppr))
    return parrafo


def _run(parrafo, texto: str, prototipo: _Prototipo, *, bold=None, size=None):
    run = parrafo.add_run(texto)
    if prototipo.rpr is not None:
        run._r.insert(0, deepcopy(prototipo.rpr))
    else:
        run.font.name = "Calibri"
        if bold is not None:
            run.bold = bold
        if size is not None:
            run.font.size = Pt(size)
    return run


def _limpiar_cuerpo(plantilla: _Plantilla) -> None:
    doc = plantilla.doc
    body = doc.element.body
    conservar = {p._p for p in doc.paragraphs[: plantilla.header]}
    for hijo in list(body):
        if hijo.tag == qn("w:sectPr"):
            continue
        if hijo in conservar:
            continue
        if hijo.tag in (qn("w:p"), qn("w:tbl")):
            body.remove(hijo)


def _lineas(texto: str) -> list[str]:
    return [linea.strip() for linea in (texto or "").split("\n") if linea.strip()]


def _sin_vineta(texto: str) -> str:
    return re.sub(r"^[-•*·]\s*", "", (texto or "").strip())


def _datos_desde_texto(texto: str) -> dict:
    """Respaldo para adaptaciones viejas sin campos estructurados."""
    datos = {
        "perfil": "",
        "experiencia": [],
        "educacion": [],
        "habilidades": [],
        "idiomas": [],
        "otras": [],
    }
    seccion = None
    entrada = None
    for linea in (texto or "").splitlines():
        limpia = linea.strip()
        if not limpia:
            continue
        clave = _clave_heading(limpia)
        if clave:
            seccion = clave
            entrada = None
            continue
        if seccion == "perfil":
            datos["perfil"] += ("\n" if datos["perfil"] else "") + limpia
        elif seccion == "experiencia":
            es_vineta = limpia.startswith(("-", "•", "*", "·"))
            parece_titulo = " | " in limpia and not es_vineta
            if parece_titulo or entrada is None:
                entrada = {"titulo": limpia, "bullets": []}
                datos["experiencia"].append(entrada)
            else:
                entrada["bullets"].append(_sin_vineta(limpia))
        elif seccion == "educacion":
            datos["educacion"].append(_sin_vineta(limpia))
        elif seccion == "habilidades":
            if ":" in limpia:
                etiqueta, _, items = limpia.partition(":")
                datos["habilidades"].append(
                    {"etiqueta": etiqueta.strip(), "items": items.strip()}
                )
            else:
                datos["habilidades"].append(
                    {"etiqueta": "", "items": _sin_vineta(limpia)}
                )
        elif seccion == "idiomas":
            datos["idiomas"].append(_sin_vineta(limpia))
    return datos


def _normalizar_datos(datos: dict, cv_texto: str) -> dict:
    limpio = {
        "perfil": str(datos.get("perfil") or "").strip(),
        "experiencia": [],
        "educacion": [
            str(linea).strip()
            for linea in datos.get("educacion") or []
            if str(linea).strip()
        ],
        "habilidades": [],
        "idiomas": [
            str(linea).strip()
            for linea in datos.get("idiomas") or []
            if str(linea).strip()
        ],
        "otras": [],
    }
    for entrada in datos.get("experiencia") or []:
        if not isinstance(entrada, dict):
            continue
        titulo = str(entrada.get("titulo") or "").strip()
        bullets = [
            _sin_vineta(str(item))
            for item in entrada.get("bullets") or []
            if str(item).strip()
        ]
        if titulo:
            limpio["experiencia"].append({"titulo": titulo, "bullets": bullets})
    for item in datos.get("habilidades") or []:
        if not isinstance(item, dict):
            continue
        etiqueta = str(item.get("etiqueta") or "").strip()
        items = str(item.get("items") or "").strip()
        if etiqueta or items:
            limpio["habilidades"].append({"etiqueta": etiqueta, "items": items})
    for bloque in datos.get("otras") or []:
        if not isinstance(bloque, dict):
            continue
        titulo = str(bloque.get("titulo") or "").strip()
        lineas = [
            _sin_vineta(str(linea))
            for linea in bloque.get("lineas") or []
            if str(linea).strip()
        ]
        if titulo and lineas:
            limpio["otras"].append({"titulo": titulo, "lineas": lineas})

    if not any(
        (
            limpio["perfil"],
            limpio["experiencia"],
            limpio["educacion"],
            limpio["habilidades"],
            limpio["idiomas"],
        )
    ):
        limpio = _datos_desde_texto(cv_texto)
    return limpio


def _es_mayusculas(texto: str) -> bool:
    letras = [c for c in texto if c.isalpha()]
    return bool(letras) and all(c.isupper() for c in letras)


def _titulo(plantilla: _Plantilla, clave: str) -> str:
    titulo = plantilla.headings.get(clave) or TITULOS_POR_DEFECTO[clave]
    if plantilla.headings and _es_mayusculas(next(iter(plantilla.headings.values()))):
        titulo = titulo.upper()
    return titulo


def _seccion_visible(datos: dict, clave: str) -> bool:
    if clave == "perfil":
        return bool(datos["perfil"])
    return bool(datos.get(clave))


def generar_docx(
    plantilla_bytes: bytes | None,
    datos: dict,
    cv_texto: str = "",
) -> bytes:
    """Genera el .docx adaptado usando la plantilla cargada (o una limpia)."""
    datos = _normalizar_datos(datos, cv_texto)
    if plantilla_bytes:
        doc = _abrir(plantilla_bytes)
        plantilla = _analizar(doc)
        _limpiar_cuerpo(plantilla)
    else:
        doc = _documento_nuevo()
        plantilla = _Plantilla(doc=doc, header=0)
        # Cabecera mínima para un CV sin plantilla: primera línea como nombre.
        lineas = _lineas(cv_texto)
        if lineas:
            nombre = doc.add_paragraph()
            nombre.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _run(nombre, lineas[0], _Prototipo(), bold=True, size=18)
        if len(lineas) > 1:
            contacto = doc.add_paragraph()
            contacto.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _run(contacto, _sin_vineta(lineas[1]), _Prototipo(), size=11)

    def agregar_heading(texto: str) -> None:
        parrafo = _parrafo(doc, plantilla.heading)
        _run(parrafo, texto, plantilla.heading, bold=True, size=14)

    def agregar_cuerpo(texto: str) -> None:
        parrafo = _parrafo(doc, plantilla.body)
        _run(parrafo, texto, plantilla.body, size=11)

    def agregar_separador() -> None:
        _parrafo(doc, plantilla.spacer)

    def agregar_experiencia() -> None:
        entradas = datos["experiencia"]
        for posicion, entrada in enumerate(entradas):
            titulo = _parrafo(doc, plantilla.entry)
            _run(titulo, entrada["titulo"], plantilla.entry, bold=True, size=12)
            agregar_separador()
            for bullet in entrada["bullets"]:
                agregar_cuerpo(bullet)
            if posicion < len(entradas) - 1:
                agregar_separador()

    def agregar_educacion() -> None:
        for linea in datos["educacion"]:
            parrafo = _parrafo(doc, plantilla.entry)
            _run(parrafo, linea, plantilla.entry, bold=True, size=12)

    def agregar_habilidades() -> None:
        for item in datos["habilidades"]:
            parrafo = _parrafo(doc, plantilla.body)
            if item["etiqueta"]:
                _run(
                    parrafo,
                    f"{item['etiqueta']}: ",
                    plantilla.skill_label,
                    bold=True,
                    size=11,
                )
            if item["items"]:
                _run(
                    parrafo,
                    item["items"],
                    plantilla.skill_items or plantilla.body,
                    size=11,
                )

    def agregar_idiomas() -> None:
        for linea in datos["idiomas"]:
            agregar_cuerpo(linea)

    def agregar_otras() -> None:
        for bloque in datos["otras"]:
            agregar_heading(bloque["titulo"])
            for linea in bloque["lineas"]:
                agregar_cuerpo(linea)

    manejadores = {
        "perfil": lambda: [agregar_cuerpo(linea) for linea in _lineas(datos["perfil"])],
        "experiencia": agregar_experiencia,
        "educacion": agregar_educacion,
        "habilidades": agregar_habilidades,
        "idiomas": agregar_idiomas,
    }

    for clave in plantilla.orden:
        if clave in manejadores and _seccion_visible(datos, clave):
            agregar_heading(_titulo(plantilla, clave))
            manejadores[clave]()

    for clave in ("perfil", "experiencia", "educacion", "habilidades", "idiomas"):
        if clave in plantilla.orden or not _seccion_visible(datos, clave):
            continue
        agregar_heading(_titulo(plantilla, clave))
        manejadores[clave]()

    agregar_otras()

    salida = io.BytesIO()
    doc.save(salida)
    return salida.getvalue()
