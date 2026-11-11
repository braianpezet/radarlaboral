# -*- coding: utf-8 -*-
"""Modelo común de una oferta cruda, antes de normalizar."""
from __future__ import annotations

from dataclasses import dataclass


class FuenteBloqueada(RuntimeError):
    """El portal respondió con un desafío anti-bot (WAF/captcha) o un límite.

    No se intenta resolver el desafío: solo se informa y se corta la fuente
    para no agravar el bloqueo. La resolución queda en manos del usuario.
    """

    def __init__(self, fuente: str, detalle: str = "") -> None:
        self.fuente = fuente
        self.detalle = detalle
        mensaje = f"{fuente} bloqueó o limitó la consulta (WAF/captcha)"
        if detalle:
            mensaje = f"{mensaje}: {detalle}"
        super().__init__(
            mensaje + ". Se pausa la fuente para no agravar el bloqueo."
        )


class SesionAsistidaRequerida(RuntimeError):
    """El portal pide una verificación que solo puede resolver la persona.

    No se automatiza la resolución. La app abre el portal en una ventana
    real con perfil persistente para que el usuario la resuelva y luego
    reutiliza esa sesión.
    """

    def __init__(self, fuente: str, detalle: str = "") -> None:
        self.fuente = fuente
        self.detalle = detalle
        mensaje = (
            f"{fuente} necesita una sesión asistida (Cloudflare). "
            "Abrí el portal desde la app, resolvé la verificación manualmente "
            "y volvé a actualizar."
        )
        if detalle:
            mensaje = f"{mensaje} Detalle: {detalle}"
        super().__init__(mensaje)


@dataclass
class JobRaw:
    source_id: str
    external_id: str
    url: str
    title: str
    company: str | None = None
    location: str | None = None
    description: str | None = None
    salary_text: str | None = None
    published_text: str | None = None
    contract_type: str | None = None
    modality_hint: str | None = None
    summary: str | None = None
