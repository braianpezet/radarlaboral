# -*- coding: utf-8 -*-
"""Utilidades de texto: normalización, fechas, salario, idioma, modalidad."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

MESES_ABREV = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "sept": 9, "set": 9, "oct": 10,
    "nov": 11, "dic": 12,
    # inglés (GetOnBoard muestra "Nov 04", "Oct 22")
    "jan": 1, "apr": 4, "aug": 8, "dec": 12,
}

STOP_ES = set("""
el la los las un una unos unas de del al a en y o que se su sus por para con
sin sobre entre como mas pero es son fue ser esta este esto estos estas
tiene tienen desde hasta cuando donde muy tu tus nuestro nuestra
""".split())

STOP_EN = set("""
the and of to in for with is are on at this that from your you will be an as
or by we our they their it its have has not can will would should about into
""".split())


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt else None


def normalizar(texto: str | None) -> str:
    """Minúsculas, sin acentos y con espacios colapsados."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r"\s+", " ", t)
    return t.strip()


# Zonas que sí interesan: Argentina, remoto LatAm y remoto sin restricción.
_UBICACION_AR = re.compile(
    r"argentin|buenos aires|caba|capital federal|gba|gran buenos aires|"
    r"cordoba|rosario|mendoza|la plata|mar del plata|tucuman|salta|neuquen|"
    r"santa fe|entre rios|misiones|chaco|corrientes|jujuy|san juan|"
    r"san luis|la pampa|chubut|rio negro|santa cruz|tierra del fuego"
)
_UBICACION_LATAM = re.compile(
    r"latin america|latam|lat-am|america latina|south america|sudamerica|"
    r"centroamerica|central america|caribbean|caribe|americas\b|"
    r"mexico|brazil|brasil|chile|colombia|peru|uruguay|paraguay|bolivia|"
    r"ecuador|venezuela|panama|costa rica|guatemala|honduras|"
    r"el salvador|nicaragua|dominican republic|republica dominicana|cuba"
)
_UBICACION_GLOBAL = re.compile(
    r"worldwide|world wide|anywhere|global|remote worldwide|"
    r"international|internacional|sin restriccion|no restriction"
)
# Países/regiones que no sirven si el aviso está limitado a ellos.
_UBICACION_EXCLUIDA = re.compile(
    r"united states|\busa\b|\bus\b|\bu\.s\.|canada|europe|\beu\b|\buk\b|"
    r"united kingdom|germany|france|spain|portugal|italy|ireland|"
    r"netherlands|poland|sweden|norway|denmark|finland|switzerland|"
    r"india|asia|africa|australia|new zealand|japan|china|singapore|"
    r"emea|apac|middle east|saudi arabia|israel|turkey|russia|ukraine"
)


def aceptar_ubicacion(ubicacion: str | list | tuple | None) -> bool:
    """True si la ubicación incluye Argentina/LatAm o es remoto sin país fijo."""
    if isinstance(ubicacion, (list, tuple)):
        texto = ", ".join(str(x) for x in ubicacion if x)
    else:
        texto = str(ubicacion or "")
    t = normalizar(texto)
    if not t:
        # Sin dato: se deja pasar y se revisa al abrir el aviso.
        return True
    if _UBICACION_GLOBAL.search(t):
        return True
    if _UBICACION_AR.search(t):
        return True
    if _UBICACION_EXCLUIDA.search(t):
        return False
    if _UBICACION_LATAM.search(t):
        return True
    if re.search(r"\b(remote|remoto|teletrabajo|home office)\b", t):
        return True
    return False


def clasificar_zona(
    ubicacion: str | list | tuple | None, modalidad: str | None
) -> tuple[int, str]:
    """Devuelve (puntos 0–10, etiqueta) según zona y modalidad."""
    if isinstance(ubicacion, (list, tuple)):
        texto = ", ".join(str(x) for x in ubicacion if x)
    else:
        texto = str(ubicacion or "")
    t = normalizar(texto)
    remoto = normalizar(modalidad) == "remoto"

    es_ar = bool(_UBICACION_AR.search(t))
    es_latam = bool(_UBICACION_LATAM.search(t))
    es_global = bool(_UBICACION_GLOBAL.search(t)) or bool(
        re.search(r"\b(remote|remoto)\b", t)
    )

    if remoto:
        if es_ar:
            return 10, "Remoto Argentina"
        if es_latam:
            return 8, "Remoto LatAm"
        if not t or es_global:
            return 6, "Remoto global"
        return 4, "Remoto"

    if es_ar:
        return 10, "Argentina"
    if not t:
        return 5, "Sin ubicación"
    if es_latam:
        return 6, "LatAm"
    if es_global:
        return 4, "Global"
    return 0, "Otra ubicación"


def clave_zona(
    ubicacion: str | list | tuple | None, modalidad: str | None
) -> str:
    """Zona resumida que se guarda y usa para filtrar la lista."""
    puntos, etiqueta = clasificar_zona(ubicacion, modalidad)
    if etiqueta == "Remoto Argentina":
        return "remoto_ar"
    if etiqueta == "Remoto LatAm":
        return "remoto_latam"
    if etiqueta in ("Remoto global", "Remoto"):
        return "remoto_global"
    if etiqueta == "Argentina":
        if isinstance(ubicacion, (list, tuple)):
            texto = ", ".join(str(x) for x in ubicacion if x)
        else:
            texto = str(ubicacion or "")
        t = normalizar(texto)
        if "fuera de gba" in t:
            return "argentina"
        if re.search(r"\b(caba|capital federal|gba|gran buenos aires)\b", t):
            return "caba"
        if "buenos aires" in t:
            return "caba"
        return "argentina"
    return ""


def html_a_texto(html: str | None) -> str | None:
    """Convierte el HTML de una descripción en texto legible."""
    if not html:
        return None
    soup = BeautifulSoup(str(html), "lxml")
    for ruido in soup.select("script, style, noscript, iframe, form"):
        ruido.decompose()
    for salto in soup.select("br"):
        salto.replace_with("\n")
    for bloque in soup.find_all(
        ["p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section"]
    ):
        bloque.append("\n")
    texto = soup.get_text(" ", strip=False)
    texto = texto.replace("\xa0", " ")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r" *\n *", "\n", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    texto = re.sub(r"\n(?=[a-záéíóúñ,.;])", " ", texto)
    return reparar_mojibake(texto.strip()) or None


def reparar_mojibake(texto: str | None) -> str | None:
    """Corrige textos que llegan doblemente codificados (RemoteOK, por ejemplo).

    'HÃ¤user' → 'Häuser', 'What Youâ€™ll' → 'What You’ll'.
    """
    if not texto or not re.search(r"[ÃÂâã]", texto):
        return texto
    try:
        return texto.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto



def texto_salario(
    minimo: float | int | None,
    maximo: float | int | None,
    moneda: str | None = None,
    periodo: str | None = None,
) -> str | None:
    """Arma un texto de salario normalizado a partir de campos numéricos."""
    valores = []
    for valor in (minimo, maximo):
        try:
            numero = float(valor or 0)
        except (TypeError, ValueError):
            numero = 0.0
        if numero > 0 and numero not in valores:
            valores.append(numero)
    if not valores:
        return None
    etiqueta = (moneda or "").strip().upper()
    rango = " - ".join(f"{v:,.0f}".replace(",", ".") for v in valores)
    sufijo = {
        "anual": "/año",
        "annual": "/año",
        "yearly": "/año",
        "year": "/año",
        "mensual": "/mes",
        "monthly": "/mes",
        "month": "/mes",
        "hora": "/hora",
        "hourly": "/hora",
        "hour": "/hora",
        "dia": "/día",
        "daily": "/día",
        "day": "/día",
    }.get((periodo or "").strip().lower(), "")
    partes = [p for p in (etiqueta, rango) if p]
    base = " ".join(partes)
    return f"{base} {sufijo}" if sufijo else base


def detectar_idioma(texto: str | None) -> str:
    palabras = re.findall(r"[a-z]+", normalizar(texto))
    if not palabras:
        return "es"
    es = sum(1 for p in palabras if p in STOP_ES)
    en = sum(1 for p in palabras if p in STOP_EN)
    if es == 0 and en == 0:
        return "es"
    return "es" if es >= en else "en"


def detectar_modalidad(texto: str | None) -> str | None:
    t = normalizar(texto)
    if not t:
        return None
    remoto = bool(re.search(r"\b(remoto|remote|teletrabajo|home office|homeoffice|desde casa)\b", t))
    presencial = bool(re.search(r"\b(presencial|on site|onsite)\b", t))
    hibrido = bool(re.search(r"\b(hibrido|hybrid|mixto)\b", t))
    if hibrido or (remoto and presencial):
        return "hibrido"
    if remoto:
        return "remoto"
    if presencial:
        return "presencial"
    return None


def detectar_seniority(texto: str | None) -> str | None:
    t = normalizar(texto)
    if re.search(r"\b(trainee|pasante|pasantia|practicante)\b", t):
        return "trainee"
    if re.search(r"\b(semi[\s-]?senior|semi[\s-]?sr|ssr)\b", t):
        return "semi-senior"
    if re.search(r"\b(junior|jr|sin experiencia|primer empleo)\b", t):
        return "junior"
    if re.search(r"\b(senior|sr|lead|lider|arquitecto|principal)\b", t):
        return "senior"

    m = re.search(r"(\d{1,2})\s*(?:\+|mas)?\s*anos?\s*(?:de\s*)?experiencia", t)
    if not m:
        m = re.search(r"experiencia\s*(?:de\s*)?(\d{1,2})\s*(?:\+|mas)?\s*anos?", t)
    if m:
        n = int(m.group(1))
        if n <= 1:
            return "junior"
        if n <= 4:
            return "semi-senior"
        return "senior"
    return None


def parsear_fecha(texto: str | None, ahora: datetime | None = None) -> datetime | None:
    """Interpreta 'Hace 33 minutos', 'Ayer', '27 de octubre' o 'nov 04'."""
    if not texto:
        return None
    ahora = ahora or ahora_utc()
    t = texto.strip()

    # Epoch en segundos (Himalayas usa pubDate numérico).
    if re.fullmatch(r"\d{10}", t):
        try:
            return datetime.fromtimestamp(int(t), tz=timezone.utc)
        except (ValueError, OSError):
            return None

    # Fecha argentina "03/11/2026" (Empleos IT).
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", t)
    if m:
        dia, mes, anio = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if mes > 12 and dia <= 12:
            dia, mes = mes, dia
        try:
            return datetime(anio, mes, dia, 15, 0, tzinfo=timezone.utc)
        except ValueError:
            return None

    # Fecha ISO completa (la usa GetOnBoard en el detalle).
    m = re.match(
        r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?",
        t,
    )
    if m:
        anio, mes, dia = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hora = int(m.group(4) or 0)
        minuto = int(m.group(5) or 0)
        segundo = int(m.group(6) or 0)
        try:
            return datetime(anio, mes, dia, hora, minuto, segundo, tzinfo=timezone.utc)
        except ValueError:
            return None

    tl = normalizar(t)

    m = re.search(r"hace\s+(\d+)\s*(minuto|min|hora|dia|semana|mes)", tl)
    if m:
        n = int(m.group(1))
        unidad = m.group(2)
        if unidad.startswith("min"):
            delta = timedelta(minutes=n)
        elif unidad == "hora":
            delta = timedelta(hours=n)
        elif unidad.startswith("dia"):
            delta = timedelta(days=n)
        elif unidad == "semana":
            delta = timedelta(weeks=n)
        else:
            delta = timedelta(days=30 * n)
        return ahora - delta

    if re.search(r"\b(hoy|recien|ahora)\b", tl):
        return ahora
    if re.search(r"\bayer\b", tl):
        return ahora - timedelta(days=1)

    # "27 de octubre (actualizada)"
    m = re.search(r"(\d{1,2})\s+de\s+([a-z]+)", tl)
    if m:
        dia = int(m.group(1))
        mes = MESES.get(m.group(2))
        if mes:
            anio = ahora.year
            # Argentina es UTC-3: se asume publicación al mediodía local.
            candidato = datetime(anio, mes, dia, 15, 0, tzinfo=timezone.utc)
            if candidato > ahora + timedelta(days=1):
                candidato = candidato.replace(year=anio - 1)
            return candidato

    # "nov 04" / "04 nov" (abreviatura de mes)
    m = re.match(r"^([a-z]{3,4})\.?\s+(\d{1,2})(?:,?\s+(\d{4}))?$", tl)
    if not m:
        m = re.match(r"^(\d{1,2})\s+([a-z]{3,4})\.?(?:,?\s+(\d{4}))?$", tl)
        if m:
            dia, mes_txt, anio_txt = int(m.group(1)), m.group(2), m.group(3)
        else:
            dia = None
    else:
        mes_txt, dia, anio_txt = m.group(1), int(m.group(2)), m.group(3)

    if dia is not None:
        mes = MESES_ABREV.get(mes_txt)
        if mes:
            anio = int(anio_txt) if anio_txt else ahora.year
            candidato = datetime(anio, mes, dia, 15, 0, tzinfo=timezone.utc)
            if candidato > ahora + timedelta(days=1):
                candidato = candidato.replace(year=anio - 1)
            return candidato

    return None


def _numero_salario(texto: str) -> float | None:
    """Convierte '2.222,00', '1.200.000', '2800', '20k' o '3.5k' a float."""
    numero = texto.strip().lower().replace(" ", "")
    if not numero:
        return None
    multiplicador = 1.0
    if numero.endswith("k"):
        multiplicador = 1000.0
        numero = numero[:-1]
    if "," in numero:
        numero = numero.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", numero):
        # Separador de miles: 1.200.000
        numero = numero.replace(".", "")
    # Si no, los puntos se interpretan como decimales: 3.5
    try:
        return float(numero) * multiplicador
    except ValueError:
        return None


def parsear_salario(texto: str | None) -> dict | None:
    if not texto:
        return None
    t = texto.strip()
    tl = normalizar(t)

    moneda = None
    if any(x in tl for x in ("usd", "u$s", "us$", "dolar", "dolares", "usd/mes")):
        moneda = "USD"
    elif "eur" in tl or "€" in t:
        moneda = "EUR"
    elif "$" in t:
        moneda = "ARS"

    periodo = None
    if re.search(r"\b(mensual|mes|month|monthly|/mes|/month)\b", tl):
        periodo = "mensual"
    elif re.search(r"\b(anual|ano|year|yearly|/ano|/year)\b", tl):
        periodo = "anual"
    elif re.search(r"\b(hora|hour|hourly|/hora|/hour)\b", tl):
        periodo = "hora"
    elif re.search(r"\b(dia|day|daily|/dia|/day)\b", tl):
        periodo = "dia"

    numeros = re.findall(r"\d[\d.,]*\s*[kK]?", t)
    valores = [v for v in (_numero_salario(n) for n in numeros) if v is not None]
    if not valores:
        return None

    return {
        "min": min(valores),
        "max": max(valores),
        "moneda": moneda,
        "periodo": periodo,
        "texto": t,
    }


def huella(*partes: str | None) -> str:
    base = "|".join(normalizar(p) for p in partes)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def hash_contenido(texto: str | None) -> str | None:
    if not texto:
        return None
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()


def limpiar_descripcion(texto: str | None) -> str | None:
    if not texto:
        return None
    t = texto.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip() or None
