# -*- coding: utf-8 -*-
"""Filtros de relevancia compartidos entre portales.

Algunos portales mezclan búsquedas de software con puestos industriales
("programador CNC", "mantenimiento industrial"). Se descartan los títulos
claramente industriales salvo que además traigan una señal tecnológica.
"""
from __future__ import annotations

import re

from ..services.text import normalizar

_TERMINOS_INDUSTRIALES = re.compile(
    r"\b(cnc|torno|fresado|fresadora|mecanizado|soldadura|soldador|"
    r"obra|construccion|plc|scada|dcs|logistic[oa]|logistica|"
    r"produccion|mantenimiento|industrial|electricista|electromecanic[oa]|"
    r"automatizacion industrial|matriceria|inyeccion|montaje)\b"
)
_TERMINOS_IT = re.compile(
    r"\b(software|web|front|frontend|front-end|back|backend|back-end|"
    r"full ?stack|java|python|javascript|typescript|react|angular|node|"
    r"datos|data|machine learning|\bml\b|\bia\b|inteligencia artificial|"
    r"sistemas|aplicaciones|aplicacion|sql|base de datos|\bbi\b|"
    r"business intelligence|cloud|devops|\bqa\b|testing|tester|soporte|"
    r"help ?desk|redes|seguridad|ciberseguridad|infraestructura|sysadmin|"
    r"analista funcional|desarrollador|developer)\b"
)


def es_relevante(titulo: str | None) -> bool:
    """True si el título parece un puesto de IT y no uno industrial."""
    t = normalizar(titulo)
    if not t:
        return False
    if _TERMINOS_INDUSTRIALES.search(t) and not _TERMINOS_IT.search(t):
        return False
    return True
