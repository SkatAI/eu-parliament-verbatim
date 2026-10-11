"""Code tables for the EU Publications Office authority URIs used by the API."""

# http://publications.europa.eu/resource/authority/language/XXX -> ISO 639-1
LANGUAGES = {
    "BUL": "bg", "CES": "cs", "DAN": "da", "DEU": "de", "ELL": "el", "ENG": "en",
    "EST": "et", "FIN": "fi", "FRA": "fr", "GLE": "ga", "HRV": "hr", "HUN": "hu",
    "ITA": "it", "LAV": "lv", "LIT": "lt", "MLT": "mt", "NLD": "nl", "POL": "pl",
    "POR": "pt", "RON": "ro", "SLK": "sk", "SLV": "sl", "SPA": "es", "SWE": "sv",
}

# http://publications.europa.eu/resource/authority/country/XXX -> English name
COUNTRIES = {
    "AUT": "Austria", "BEL": "Belgium", "BGR": "Bulgaria", "HRV": "Croatia",
    "CYP": "Cyprus", "CZE": "Czechia", "DNK": "Denmark", "EST": "Estonia",
    "FIN": "Finland", "FRA": "France", "DEU": "Germany", "GRC": "Greece",
    "HUN": "Hungary", "IRL": "Ireland", "ITA": "Italy", "LVA": "Latvia",
    "LTU": "Lithuania", "LUX": "Luxembourg", "MLT": "Malta", "NLD": "Netherlands",
    "POL": "Poland", "PRT": "Portugal", "ROU": "Romania", "SVK": "Slovakia",
    "SVN": "Slovenia", "ESP": "Spain", "SWE": "Sweden", "GBR": "United Kingdom",
}


def last_segment(uri: str | None) -> str | None:
    """'http://.../language/POL' -> 'POL', 'person/197514' -> '197514', 'def/ep-roles/CHAIR' -> 'CHAIR'."""
    return uri.rstrip("/").rsplit("/", 1)[-1] if uri else None


def language_code(uri: str) -> str:
    code = last_segment(uri)
    return LANGUAGES.get(code, code.lower())


def country(uri: str | None) -> dict | None:
    code = last_segment(uri)
    return {"code": code, "name": COUNTRIES.get(code, code)} if code else None
