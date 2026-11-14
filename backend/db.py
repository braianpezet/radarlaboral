# -*- coding: utf-8 -*-
"""SQLite: esquema, conexión y utilidades."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from .config import DATA_DIR, DB_PATH
from .services.profiles import sembrar_perfiles

ESQUEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    type          TEXT NOT NULL,              -- api | html | rss
    reliability   TEXT NOT NULL,              -- alta | media | baja
    enabled       INTEGER NOT NULL DEFAULT 1,
    requires_key  INTEGER NOT NULL DEFAULT 0,
    last_run_at   TEXT,
    last_error    TEXT
);

CREATE TABLE IF NOT EXISTS companies (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL,
    name_norm TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS profiles (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    priority      INTEGER NOT NULL,
    enabled       INTEGER NOT NULL DEFAULT 1,
    roles         TEXT,
    core_skills   TEXT,
    extra_skills  TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id      TEXT NOT NULL REFERENCES sources(id),
    external_id    TEXT NOT NULL,
    url            TEXT NOT NULL,
    title          TEXT NOT NULL,
    company_id     INTEGER REFERENCES companies(id),
    company_name   TEXT,
    description    TEXT,
    summary        TEXT,
    location       TEXT,
    modality       TEXT,
    seniority      TEXT,
    contract_type  TEXT,
    salary_text    TEXT,
    salary_min     REAL,
    salary_max     REAL,
    currency       TEXT,
    period         TEXT,
    language       TEXT,
    zone           TEXT,                -- caba | remoto_ar | remoto_latam | remoto_global
    published_at   TEXT,
    fetched_at     TEXT NOT NULL,
    fingerprint    TEXT,
    content_hash   TEXT,
    status         TEXT NOT NULL DEFAULT 'nuevo',
    note           TEXT,
    status_updated_at TEXT,
    UNIQUE (source_id, external_id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_published ON jobs (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status    ON jobs (status);
CREATE INDEX IF NOT EXISTS idx_jobs_source    ON jobs (source_id);
CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint ON jobs (fingerprint);

CREATE TABLE IF NOT EXISTS feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    profile_id TEXT,
    vote       INTEGER NOT NULL,              -- +1 interesa | -1 no interesa
    motivos    TEXT,                          -- JSON con los motivos elegidos
    score_base INTEGER,
    features   TEXT,                          -- snapshot del score_detail
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_feedback_job ON feedback (job_id, id DESC);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL DEFAULT 'running',   -- running | ok | error
    found       INTEGER NOT NULL DEFAULT 0,
    new         INTEGER NOT NULL DEFAULT 0,
    updated     INTEGER NOT NULL DEFAULT 0,
    errors      INTEGER NOT NULL DEFAULT 0,
    message     TEXT
);

CREATE TABLE IF NOT EXISTS run_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     INTEGER NOT NULL,
    source_id  TEXT,
    level      TEXT NOT NULL DEFAULT 'info',   -- info | warn | error
    message    TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_run_logs_run ON run_logs (run_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_run_logs_created ON run_logs (created_at);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- CV base para el asistente ('' = CV general; también admite P1…P5).
CREATE TABLE IF NOT EXISTS cv_documentos (
    profile_id     TEXT PRIMARY KEY,
    contenido      TEXT NOT NULL,
    actualizado_at TEXT NOT NULL,
    plantilla         BLOB,                -- .docx original que se usa como plantilla
    plantilla_nombre  TEXT,
    plantilla_at      TEXT
);

-- Adaptaciones generadas por el LLM, una por aviso y versión.
CREATE TABLE IF NOT EXISTS cv_adaptaciones (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    profile_id TEXT,
    modelo     TEXT,
    resultado  TEXT NOT NULL,              -- JSON: cv, resumen, cambios, faltantes
    instrucciones TEXT,                    -- pedido extra de la persona, si hubo
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cv_adapt_job ON cv_adaptaciones (job_id, id DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS jobs_fts USING fts5(
    title,
    description,
    company_name,
    content='jobs',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS jobs_ai AFTER INSERT ON jobs BEGIN
    INSERT INTO jobs_fts (rowid, title, description, company_name)
    VALUES (new.id, new.title, new.description, new.company_name);
END;

CREATE TRIGGER IF NOT EXISTS jobs_ad AFTER DELETE ON jobs BEGIN
    INSERT INTO jobs_fts (jobs_fts, rowid, title, description, company_name)
    VALUES ('delete', old.id, old.title, old.description, old.company_name);
END;

CREATE TRIGGER IF NOT EXISTS jobs_au AFTER UPDATE ON jobs BEGIN
    INSERT INTO jobs_fts (jobs_fts, rowid, title, description, company_name)
    VALUES ('delete', old.id, old.title, old.description, old.company_name);
    INSERT INTO jobs_fts (rowid, title, description, company_name)
    VALUES (new.id, new.title, new.description, new.company_name);
END;
"""

FUENTES_INICIALES = [
    ("computrabajo", "Computrabajo AR", "html", "alta", 1, 0),
    ("getonboard", "GetOnBoard", "html", "alta", 1, 0),
    ("empleosit", "Empleos IT", "html", "alta", 1, 0),
    ("remotive", "Remotive", "api", "media", 1, 0),
    ("remoteok", "RemoteOK", "api", "media", 1, 0),
    ("himalayas", "Himalayas", "api", "media", 1, 0),
    ("jobicy", "Jobicy", "api", "media", 1, 0),
    ("buscojobs", "BuscoJobs AR", "html", "media", 1, 0),
    ("zonajobs", "ZonaJobs AR", "api", "media", 1, 0),
    ("bumeran", "Bumeran AR", "api", "media", 1, 0),
    # Boards públicos de empresas argentinas y con operación local.
    ("empresas", "Empresas (ATS)", "api", "alta", 1, 0),
    # Jooble: API oficial con clave gratuita por país. Apagada hasta tener una
    # clave del dominio ar.jooble.org (la de jooble.org solo trae EE. UU.).
    ("jooble", "Jooble", "api", "media", 0, 1),
    # Apagada por defecto: ToS de LinkedIn + riesgo de bloqueo de IP.
    ("linkedin", "LinkedIn", "html", "baja", 0, 0),
]

# Columnas agregadas después de la Fase 0 (migración suave).
COLUMNAS_NUEVAS = {
    "summary": "TEXT",
    "score": "INTEGER",
    "profile_id": "TEXT",
    "score_detail": "TEXT",
    "duplicate_of": "INTEGER",
    "excluded": "INTEGER DEFAULT 0",
    "zone": "TEXT",
}


def _migrar(conn) -> None:
    existentes = {fila["name"] for fila in conn.execute("PRAGMA table_info(jobs)")}
    for columna, tipo in COLUMNAS_NUEVAS.items():
        if columna not in existentes:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {columna} {tipo}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs (score DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_profile ON jobs (profile_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_duplicate ON jobs (duplicate_of)"
    )
    cv_existentes = {
        fila["name"] for fila in conn.execute("PRAGMA table_info(cv_documentos)")
    }
    for columna, tipo in (
        ("plantilla", "BLOB"),
        ("plantilla_nombre", "TEXT"),
        ("plantilla_at", "TEXT"),
    ):
        if columna not in cv_existentes:
            conn.execute(f"ALTER TABLE cv_documentos ADD COLUMN {columna} {tipo}")
    adapt_existentes = {
        fila["name"] for fila in conn.execute("PRAGMA table_info(cv_adaptaciones)")
    }
    if "instrucciones" not in adapt_existentes:
        conn.execute("ALTER TABLE cv_adaptaciones ADD COLUMN instrucciones TEXT")
    # Zona para el filtro de la lista. Se recalcula una vez por versión de la
    # regla y después la mantiene la ingesta.
    from .services.text import clave_zona

    marca = conn.execute(
        "SELECT value FROM settings WHERE key = 'zonas_version'"
    ).fetchone()
    if not marca or marca["value"] != "2":
        for fila in conn.execute("SELECT id, location, modality FROM jobs").fetchall():
            conn.execute(
                "UPDATE jobs SET zone = ? WHERE id = ?",
                (clave_zona(fila["location"], fila["modality"]), fila["id"]),
            )
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('zonas_version', '2') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )


@contextmanager
def conexion():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with conexion() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(ESQUEMA)
        _migrar(conn)
        sembrar_perfiles(conn)
        for fuente in FUENTES_INICIALES:
            conn.execute(
                "INSERT OR IGNORE INTO sources "
                "(id, name, type, reliability, enabled, requires_key) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                fuente,
            )
        n_jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        n_fts = conn.execute("SELECT COUNT(*) FROM jobs_fts").fetchone()[0]
        if n_jobs != n_fts:
            conn.execute("INSERT INTO jobs_fts (jobs_fts) VALUES ('rebuild')")


def fila_a_dict(fila: sqlite3.Row | None) -> dict | None:
    return dict(fila) if fila is not None else None
