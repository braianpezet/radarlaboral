# -*- coding: utf-8 -*-
"""Registro de conectores disponibles."""
from __future__ import annotations

from .buscojobs import BuscoJobsConnector
from .computrabajo import ComputrabajoConnector
from .empleosit import EmpleosITConnector
from .empresas import EmpresasConnector
from .getonboard import GetOnBoardConnector
from .jooble import JoobleConnector
from .linkedin import LinkedInConnector
from .navent import BumeranConnector, ZonaJobsConnector
from .remotos import (
    HimalayasConnector,
    JobicyConnector,
    RemotiveConnector,
    RemoteOkConnector,
)

CONECTORES = {
    ComputrabajoConnector.id: ComputrabajoConnector,
    GetOnBoardConnector.id: GetOnBoardConnector,
    EmpleosITConnector.id: EmpleosITConnector,
    RemotiveConnector.id: RemotiveConnector,
    RemoteOkConnector.id: RemoteOkConnector,
    HimalayasConnector.id: HimalayasConnector,
    JobicyConnector.id: JobicyConnector,
    BuscoJobsConnector.id: BuscoJobsConnector,
    ZonaJobsConnector.id: ZonaJobsConnector,
    BumeranConnector.id: BumeranConnector,
    LinkedInConnector.id: LinkedInConnector,
    EmpresasConnector.id: EmpresasConnector,
    JoobleConnector.id: JoobleConnector,
}


def crear_conector(source_id: str):
    """Devuelve una instancia del conector o None si no existe."""
    clase = CONECTORES.get(source_id)
    return clase() if clase else None
