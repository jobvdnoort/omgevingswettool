"""Configuratie en veilige API-key toegang."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ApiConfig:
    ontsluiten: str = "https://service.omgevingswet.overheid.nl/publiek/omgevingsinformatie/api/ontsluiten/v2"
    presenteren: str = "https://service.omgevingswet.overheid.nl/publiek/omgevingsdocumenten/api/presenteren/v8"
    geometrie: str = "https://service.omgevingswet.overheid.nl/publiek/omgevingsdocumenten/api/geometrieopvragen/v1"
    timeout: float = 30.0
    retries: int = 3
    page_size: int = 20  # OpenAPI default; maximum 200


def get_api_key() -> str | None:
    """Lees de sleutel uit de omgeving of Streamlit secrets."""
    key = os.getenv("DSO_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets.get("DSO_API_KEY")
    except (ImportError, FileNotFoundError, KeyError, TypeError):
        return None
