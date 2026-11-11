# -*- coding: utf-8 -*-
"""Modelos de entrada de la API."""
from __future__ import annotations

from pydantic import BaseModel, field_validator

ESTADOS_VALIDOS = {"nuevo", "visto", "guardado", "descartado", "postulado"}

MOTIVOS_FEEDBACK = {
    "seniority",
    "stack",
    "zona",
    "modalidad",
    "empresa",
    "idioma",
    "tareas",
    "salario",
}


class FeedbackCreate(BaseModel):
    job_id: int
    vote: int
    motivos: list[str] = []

    @field_validator("vote")
    @classmethod
    def validar_voto(cls, valor: int) -> int:
        if valor not in (-1, 1):
            raise ValueError("El voto debe ser 1 (me interesa) o -1 (no me interesa)")
        return valor

    @field_validator("motivos")
    @classmethod
    def validar_motivos(cls, valores: list[str]) -> list[str]:
        limpios = []
        for valor in valores:
            if valor not in MOTIVOS_FEEDBACK:
                raise ValueError(f"Motivo inválido: {valor}")
            if valor not in limpios:
                limpios.append(valor)
        return limpios


class JobUpdate(BaseModel):
    status: str | None = None
    note: str | None = None

    @field_validator("status")
    @classmethod
    def validar_status(cls, valor: str | None) -> str | None:
        if valor is not None and valor not in ESTADOS_VALIDOS:
            raise ValueError(f"Estado inválido: {valor}")
        return valor


class SourceUpdate(BaseModel):
    enabled: bool
