# -*- coding: utf-8 -*-
"""Perfiles de búsqueda y scoring de avisos (P1–P5)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from .text import (
    clasificar_zona,
    detectar_seniority,
    normalizar,
)

# --------------------------------------------------------------------------- perfiles
PERFILES = [
    {
        "id": "P1",
        "name": "ML / Visión",
        "priority": 1,
        "roles": [
            "machine learning", "ml engineer", "mlops", "data scientist",
            "data science", "computer vision", "vision por computadora",
            "vision computacional", "vision artificial", "ai engineer",
            "artificial intelligence", "inteligencia artificial",
            "deep learning", "nlp", "llm", "research engineer", "investigador",
            "cientifico de datos", "analista de datos", "data engineer",
            "data analyst",
        ],
        "core": [
            "python", "pytorch", "tensorflow", "opencv", "yolo", "numpy",
            "scikit-learn", "pandas", "keras", "machine learning",
            "computer vision", "deep learning", "nlp", "llm", "transformers",
        ],
        "extra": [
            "sql", "git", "docker", "aws", "linux", "c++", "matlab", "openai",
            "hugging face", "power bi", "tableau", "spark", "big data",
        ],
    },
    {
        "id": "P2",
        "name": "Backend / Full Stack",
        "priority": 2,
        "roles": [
            "backend", "back-end", "back end", "full stack", "fullstack",
            "full-stack", "frontend", "front-end", "front end", "developer",
            "desarrollador", "software engineer", "ingeniero de software",
            "programador", "java", "spring", "node", "react", "php",
            "python developer", "mobile", "android", "ios", "devops",
            "site reliability",
        ],
        "core": [
            "java", "spring", "spring boot", "node", "react", "javascript",
            "typescript", "sql", "aws", "git", "docker", "rest", "api", "php",
            "laravel", "mysql", "postgresql", "mongodb", "microservices", "next",
        ],
        "extra": [
            "html", "css", "kubernetes", "jenkins", "angular", "vue", "python",
            "django", "flask", "graphql", "redis", "kafka", "ci/cd", "scrum",
            ".net", "c#", "kotlin", "go",
        ],
    },
    {
        "id": "P3",
        "name": "Analista Funcional",
        "priority": 3,
        "roles": [
            "analista funcional", "functional analyst", "business analyst",
            "analista de negocio", "analista de negocios", "product owner",
            "project manager", "jefe de proyecto", "scrum master",
            "analista de sistemas", "analista tecnico", "analista de procesos",
            "analista de requerimientos", "qa analyst", "analista qa",
        ],
        "core": [
            "relevamiento", "requerimientos", "uml", "sql", "scrum", "testing",
            "jira", "casos de uso", "user stories", "documentacion",
            "analisis funcional", "business analysis", "gestion de proyectos",
        ],
        "extra": [
            "power bi", "excel", "agile", "metodologias agiles", "kanban",
            "confluence", "stakeholder", "procesos", "bpmn", "tableau", "visio",
        ],
    },
    {
        "id": "P5",
        "name": "Docencia / Educación IT",
        "priority": 4,
        "roles": [
            "docente", "profesor", "profesora", "tutor", "tutora",
            "capacitador", "instructor", "teacher", "jtp", "educacion",
            "formador",
        ],
        "core": [
            "docencia", "planificacion", "evaluacion", "programacion",
            "inteligencia artificial", "educacion", "didactica", "ensenanza",
            "python", "java", "robotica",
        ],
        "extra": [
            "scrum", "git", "sql", "metodologias", "taller", "curricular",
            "pedagogia", "virtual", "moodle",
        ],
    },
    {
        "id": "P4",
        "name": "Soporte IT",
        "priority": 5,
        "roles": [
            "soporte", "support", "helpdesk", "help desk", "service desk",
            "mesa de ayuda", "sysadmin", "system administrator",
            "administrador de sistemas", "infraestructura", "infrastructure",
            "redes", "network", "tecnico", "it support", "desktop support",
            "soporte tecnico",
        ],
        "core": [
            "windows", "linux", "redes", "office 365", "active directory",
            "sql", "troubleshooting", "itil", "vpn", "hardware",
            "soporte tecnico", "service desk", "help desk",
        ],
        "extra": [
            "azure", "aws", "powershell", "python", "scripting", "firewall",
            "cisco", "vmware", "backup", "monitoring",
        ],
    },
]

ALIASES = {
    "node": ["node", "node.js", "nodejs"],
    "next": ["next", "next.js", "nextjs"],
    "react": ["react", "react.js", "reactjs"],
    "scikit-learn": ["scikit-learn", "scikit learn", "sklearn"],
    "machine learning": [
        "machine learning", "aprendizaje automatico", "aprendizaje automático",
        "ml",
    ],
    "computer vision": [
        "computer vision", "vision por computadora", "visión por computadora",
        "vision computacional", "vision artificial", "opencv",
    ],
    "deep learning": ["deep learning", "aprendizaje profundo"],
    "nlp": ["nlp", "procesamiento de lenguaje natural"],
    "llm": ["llm", "large language model", "modelos de lenguaje"],
    "spring boot": ["spring boot", "springboot"],
    "spring": ["spring", "spring framework", "spring mvc"],
    "rest": ["rest", "restful", "api rest"],
    "api": ["api", "apis"],
    "power bi": ["power bi", "powerbi"],
    "office 365": ["office 365", "microsoft 365", "o365"],
    "active directory": ["active directory"],
    "gestion de proyectos": ["gestion de proyectos", "gestión de proyectos"],
    "analisis funcional": ["analisis funcional", "análisis funcional"],
    "soporte tecnico": ["soporte tecnico", "soporte técnico", "technical support"],
    "help desk": ["help desk", "helpdesk"],
    "service desk": ["service desk", "mesa de ayuda"],
    "ci/cd": ["ci/cd", "ci cd", "integracion continua", "integracion contínua"],
}

# Títulos que no encajan con ninguno de los perfiles.
_NO_RELEVANTE = re.compile(
    r"(?<!\w)(vendedor|vendedora|ventas|sales|call center|telemarketing|"
    r"chofer|repartidor|cobrador|promotor|ejecutivo comercial|"
    r"account executive|recepcionista|administrativo|administrativa)(?!\w)"
)

_STOPWORDS = {
    "de", "del", "la", "las", "el", "los", "y", "o", "en", "para", "con",
    "por", "a", "al", "un", "una", "the", "and", "of", "to", "for", "with",
    "jr", "sr", "ssr", "semi", "senior", "junior", "trainee",
}

_SENIORITY_PUNTOS = {
    "trainee": 10,
    "junior": 10,
    "semi-senior": 6,
    "senior": 0,
    None: 5,
}
_SENIORITY_AJUSTE = {
    "trainee": 10,
    "junior": 10,
    "semi-senior": 0,
    "senior": -30,
    None: 0,
}


def _patron(frase: str) -> re.Pattern:
    return re.compile(r"(?<!\w)" + re.escape(normalizar(frase)) + r"(?!\w)")


def _patron_alias(canonico: str) -> re.Pattern:
    alias = ALIASES.get(canonico, [canonico])
    opciones = "|".join(re.escape(normalizar(a)) for a in dict.fromkeys(alias))
    return re.compile(r"(?<!\w)(?:" + opciones + r")(?!\w)")


def _compilar(perfil: dict) -> dict:
    return {
        "id": perfil["id"],
        "name": perfil["name"],
        "priority": perfil["priority"],
        "roles": [(r, _patron(r)) for r in perfil["roles"]],
        "core": [(s, _patron_alias(s)) for s in perfil["core"]],
        "extra": [(s, _patron_alias(s)) for s in perfil["extra"]],
    }


def cargar_perfiles(conn) -> list[dict]:
    """Devuelve los perfiles activos desde la base, compilados para puntuar."""
    filas = conn.execute(
        "SELECT * FROM profiles WHERE enabled = 1 ORDER BY priority"
    ).fetchall()
    perfiles = []
    for fila in filas:
        try:
            roles = json.loads(fila["roles"] or "[]")
            core = json.loads(fila["core_skills"] or "[]")
            extra = json.loads(fila["extra_skills"] or "[]")
        except (TypeError, ValueError):
            continue
        perfiles.append(
            _compilar(
                {
                    "id": fila["id"],
                    "name": fila["name"],
                    "priority": fila["priority"],
                    "roles": roles,
                    "core": core,
                    "extra": extra,
                }
            )
        )
    return perfiles


def sembrar_perfiles(conn) -> None:
    for perfil in PERFILES:
        conn.execute(
            """
            INSERT INTO profiles (id, name, priority, enabled, roles, core_skills, extra_skills)
            VALUES (?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                priority = excluded.priority,
                roles = excluded.roles,
                core_skills = excluded.core_skills,
                extra_skills = excluded.extra_skills
            """,
            (
                perfil["id"],
                perfil["name"],
                perfil["priority"],
                json.dumps(perfil["roles"], ensure_ascii=False),
                json.dumps(perfil["core"], ensure_ascii=False),
                json.dumps(perfil["extra"], ensure_ascii=False),
            ),
        )


# --------------------------------------------------------------------------- scoring
def _puntaje_skills(texto: str, perfil: dict) -> tuple[int, list[str], list[str]]:
    core = [nombre for nombre, patron in perfil["core"] if patron.search(texto)]
    extra = [nombre for nombre, patron in perfil["extra"] if patron.search(texto)]
    cobertura_core = min(1.0, len(core) / 3.0)
    cobertura_extra = min(1.0, len(extra) / 4.0)
    puntos = round(40 * (0.8 * cobertura_core + 0.2 * cobertura_extra))
    faltantes = [
        nombre for nombre, _ in perfil["core"] if nombre not in core
    ][:4]
    return puntos, core[:6], faltantes


def _puntaje_rol(titulo: str, descripcion: str, perfil: dict) -> tuple[int, str | None]:
    for frase, patron in perfil["roles"]:
        if patron.search(titulo):
            return 20, frase
    tokens_titulo = set(titulo.split()) - _STOPWORDS
    if tokens_titulo:
        for frase, _ in perfil["roles"]:
            tokens_rol = set(frase.split()) - _STOPWORDS
            if not tokens_rol:
                continue
            solapamiento = len(tokens_titulo & tokens_rol) / len(tokens_rol)
            if solapamiento >= 0.6:
                return 10, frase
    for frase, patron in perfil["roles"]:
        if patron.search(descripcion):
            return 5, frase
    return 0, None


def _puntaje_recencia(publicado: str | None, ahora: datetime) -> tuple[int, str]:
    if not publicado:
        return 3, "sin fecha"
    try:
        fecha = datetime.fromisoformat(publicado.replace("Z", "+00:00"))
    except ValueError:
        return 3, "sin fecha"
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    delta = ahora - fecha
    if delta < timedelta(0):
        return 10, "recién"
    horas = delta.total_seconds() / 3600
    if horas < 24:
        return 10, "menos de 24 h"
    if horas < 72:
        return 8, "menos de 3 días"
    if horas < 168:
        return 6, "menos de 7 días"
    if horas < 336:
        return 4, "menos de 14 días"
    if horas < 720:
        return 2, "menos de 30 días"
    return 0, "más de 30 días"


def puntuar(job: dict, perfil: dict, ahora: datetime) -> dict:
    titulo = normalizar(job.get("title"))
    descripcion = normalizar(
        " ".join(
            parte
            for parte in (job.get("summary"), job.get("description"))
            if parte
        )
    )
    texto = f"{titulo} {descripcion}"

    excluded = bool(_NO_RELEVANTE.search(titulo))

    skills, core_hits, faltantes = _puntaje_skills(texto, perfil)
    rol, rol_hit = _puntaje_rol(titulo, descripcion, perfil)

    seniority = job.get("seniority") or detectar_seniority(f"{titulo} {descripcion}")
    seniority_puntos = _SENIORITY_PUNTOS.get(seniority, 5)
    ajuste = _SENIORITY_AJUSTE.get(seniority, 0)

    zona, zona_etiqueta = clasificar_zona(job.get("location"), job.get("modality"))
    idioma = {"es": 10, "en": 4}.get(job.get("language"), 6)
    recencia, recencia_etiqueta = _puntaje_recencia(job.get("published_at"), ahora)

    total = (
        skills + rol + seniority_puntos + zona + idioma + recencia + ajuste
        if not excluded
        else 0
    )
    total = max(0, min(100, total))

    razones: list[str] = []
    if core_hits:
        razones.append("Coincide en " + ", ".join(core_hits[:4]))
    if rol_hit:
        razones.append(f"Rol afín: {rol_hit}")
    if seniority in ("trainee", "junior"):
        razones.append("Seniority inicial")
    elif seniority == "senior":
        razones.append("Pide seniority senior")
    if zona >= 8:
        razones.append(zona_etiqueta)
    if job.get("language") == "en":
        razones.append("Aviso en inglés")

    return {
        "profile_id": perfil["id"],
        "profile_name": perfil["name"],
        "priority": perfil["priority"],
        "score": total,
        "excluded": excluded,
        "skills": {
            "score": skills,
            "matched": core_hits,
            "missing": faltantes,
        },
        "role": {"score": rol, "matched": rol_hit},
        "seniority": {
            "value": seniority,
            "score": seniority_puntos,
            "adjustment": ajuste,
        },
        "zone": {"score": zona, "label": zona_etiqueta},
        "language": {"value": job.get("language"), "score": idioma},
        "recency": {"score": recencia, "label": recencia_etiqueta},
        "reasons": razones[:5],
    }


def elegir_mejor(job: dict, perfiles: list[dict], ahora: datetime) -> dict:
    resultados = [puntuar(job, perfil, ahora) for perfil in perfiles]
    if not resultados:
        return {
            "profile_id": None,
            "profile_name": None,
            "priority": 99,
            "score": 0,
            "excluded": False,
            "reasons": [],
        }
    mejor = max(resultados, key=lambda r: (r["score"], -r["priority"]))
    mejor["todos"] = {r["profile_id"]: r["score"] for r in resultados}
    return mejor
