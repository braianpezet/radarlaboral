# -*- coding: utf-8 -*-
"""Configuración central de Radar Laboral."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _cargar_env(ruta: Path) -> None:
    """Carga pares CLAVE=valor de un .env local sin dependencias externas.

    Las variables ya definidas en el entorno tienen prioridad, así se puede
    sobrescribir la clave sin editar el archivo.
    """
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        clave = clave.strip()
        valor = valor.strip().strip('"').strip("'")
        if clave and clave not in os.environ:
            os.environ[clave] = valor


_cargar_env(BASE_DIR / ".env")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("RADAR_DATA_DIR", str(BASE_DIR / "data"))).resolve()
DB_PATH = DATA_DIR / "radar.db"
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

HOST = "127.0.0.1"
PORT = int(os.environ.get("RADAR_PORT", "8765"))

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}

# Búsquedas por fuente. Cada conector expone además su propia lista.
BUSQUEDAS = [
    "programador",
    "machine learning",
    "analista funcional",
    "soporte técnico",
]

# ZonaJobs y Bumeran (Navent). Comparten la API de avisos y están detrás de
# Cloudflare. La consulta se hace con una ventana real de Edge y perfil
# persistente: la app no resuelve captchas, solo reutiliza la sesión que la
# persona valida a mano.
ASSISTED_DIR = BASE_DIR / "assisted"
SESIONES_ASISTIDAS = ["zonajobs", "bumeran"]
PAUSA_NAVENT = 2.0
NAVENT_MAX_PAGINAS = 2
# Segundos que la ventana espera a que la persona resuelva el desafío.
NAVENT_ESPERA_SESION = 120
# Tope duro por corrida (abrir navegador + consultas).
NAVENT_TIMEOUT = 420

# BuscoJobs AR. El portal está detrás de un WAF (AWS): ritmo muy lento y una
# sola página por búsqueda para reducir el riesgo de bloqueo.
BUSQUEDAS_BUSCOJOBS = [
    "programador",
    "machine learning",
    "analista funcional",
    "soporte tecnico",
]
PAUSA_BUSCOJOBS = 12.0

# LinkedIn (búsqueda pública, sin login). Apagado por defecto: sus términos de
# uso prohíben la recolección automatizada y el sitio limita rápido (HTTP 429).
# Si se activa, se consultan pocas búsquedas y con pausas largas.
BUSQUEDAS_LINKEDIN = [
    "desarrollador junior",
    "machine learning",
    "soporte técnico",
]
PAUSA_LINKEDIN = 8.0

# Categorías de GetOnBoard que se recorren en cada actualización.
CATEGORIAS_GETONBOARD = [
    "programacion",
    "data-science-analytics",
    "sysadmin-devops-qa",
    "desarrollo-mobile",
]

# Categorías de Empleos IT (Argentina) alineadas a los perfiles P1–P5.
CATEGORIAS_EMPLEOSIT = [
    "otros-desarrollador",
    "soporte-tecnico",
    "desarrollador-java",
    "desarrollador-backend",
    "desarrollador-full-stack",
    "soporte-help-desk",
    "devops",
    "analista-funcional",
    "otros-sistemas-or-tecnologia",
    "desarrollador-python",
    "administrador-de-infraestructura",
    "analista-de-sistemas",
    "analista-tecnico",
    "desarrollador-react",
    "soporte-de-aplicaciones",
    "lider-tecnico",
    "project-manager",
    "product-manager-or-owner",
    "ciberseguridad--or--seguridad-informatica",
]

# Tamaño de página que acepta el listado de Empleos IT.
EMPLEOSIT_POR_PAGINA = 100

# Si una fuente quedó bloqueada por WAF/captcha, no se reintenta antes de este
# tiempo aunque el usuario pida una actualización manual.
PAUSA_BLOQUEO_MINUTOS = 30

# Avisos con más de estos días se eliminan en cada actualización, salvo que
# estén guardados, postulados, valorados o tengan una nota.
DIAS_RETENCION = 30

# Portales de empresas con ATS público. Cada board se consulta por su API JSON
# oficial (Lever, Greenhouse o Ashby), sin scraping ni credenciales. El token es
# el slug que aparece en la URL del board: jobs.lever.co/<token>,
# job-boards.greenhouse.io/<token> o jobs.ashbyhq.com/<token>.
ATS_EMPRESAS = [
    {"ats": "lever", "token": "despegar", "nombre": "Despegar"},
    {"ats": "lever", "token": "aleph", "nombre": "Aleph"},
    {"ats": "greenhouse", "token": "santex", "nombre": "Santex"},
    {"ats": "greenhouse", "token": "clara", "nombre": "Clara"},
    {"ats": "greenhouse", "token": "quintoandar", "nombre": "QuintoAndar"},
    {"ats": "greenhouse", "token": "dept", "nombre": "DEPT"},
    {"ats": "greenhouse", "token": "gofundme", "nombre": "GoFundMe"},
    {"ats": "greenhouse", "token": "greenhouse", "nombre": "Greenhouse"},
    {"ats": "ashby", "token": "whippy", "nombre": "Whippy"},
    {"ats": "ashby", "token": "mural", "nombre": "Mural"},
    {"ats": "ashby", "token": "nubank", "nombre": "Nubank"},
    {"ats": "ashby", "token": "canals", "nombre": "Canals"},
    {"ats": "ashby", "token": "homevision", "nombre": "HomeVision"},
    {"ats": "ashby", "token": "stensul", "nombre": "Stensul"},
    {"ats": "ashby", "token": "profound", "nombre": "Profound"},
    {"ats": "ashby", "token": "rehire", "nombre": "Rehire"},
    {"ats": "ashby", "token": "arq", "nombre": "ARQ"},
]

# Jooble. API oficial con clave gratuita (se pide en jooble.org/api/about y
# llega por mail). La clave vive en el .env local, nunca en el código.
# Se consulta por palabras clave con location=Argentina.
JOOBLE_API_KEY = os.environ.get("JOOBLE_API_KEY", "").strip()
# Cada país de Jooble usa su propio dominio y su propia clave. La clave de
# jooble.org (EE. UU.) no devuelve avisos argentinos: para Argentina hay que
# pedirla en https://ar.jooble.org/api/about.
JOOBLE_DOMINIO = os.environ.get("JOOBLE_DOMINIO", "ar.jooble.org").strip()
JOOBLE_UBICACION = os.environ.get("JOOBLE_UBICACION", "Argentina").strip()
# El plan gratuito tiene 500 consultas en total por clave: se agrupan los
# términos en dos consultas (Jooble acepta varios términos separados por coma)
# y se pide una sola página con hasta 100 avisos por búsqueda.
JOOBLE_POR_PAGINA = 100
BUSQUEDAS_JOOBLE = [
    "programador, machine learning",
    "analista funcional, soporte técnico",
]
PAUSA_JOOBLE = 1.5

# Asistente de CV. Usa la Gemini API (Google AI Studio) con una clave propia,
# distinta de la suscripción de la app Gemini. La clave vive en el .env local.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
# Vacío = se elige el primer modelo Flash-Lite disponible al consultar la API.
GEMINI_MODELO = os.environ.get("GEMINI_MODELO", "").strip()
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_TIMEOUT = 120.0

# Límites de cortesía con los portales.
PAUSA_ENTRE_BUSQUEDAS = 1.2
PAUSA_ENTRE_FUENTES = 2.5
PAUSA_ENTRE_DETALLES = 0.6
MAX_DETALLES_POR_CORRIDA = 25
