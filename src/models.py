"""Datamodellen voor genormaliseerde DSO-resultaten."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from typing import Any


DOCUMENT_FIELDS = [
    "document_id", "identificatie", "uri_identificatie", "expression_id",
    "technisch_id", "titel", "document_type", "bron_type",
    "regelgeving_of_overig", "bestuurslaag", "bevoegd_gezag", "status",
    "geldig_vanaf", "geldig_tot", "beschikbaar_op", "document_url",
    "api_detail_url", "download_url", "ophaaldatum",
]


@dataclass
class DocumentRecord:
    document_id: str
    identificatie: Any = None
    uri_identificatie: Any = None
    expression_id: Any = None
    technisch_id: Any = None
    titel: Any = None
    document_type: Any = None
    bron_type: Any = None
    regelgeving_of_overig: Any = None
    bestuurslaag: Any = None
    bevoegd_gezag: Any = None
    status: Any = None
    geldig_vanaf: Any = None
    geldig_tot: Any = None
    beschikbaar_op: Any = None
    document_url: Any = None
    api_detail_url: Any = None
    download_url: Any = None
    ophaaldatum: Any = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GeometryRecord:
    document_id: str
    document_identificatie: Any = None
    expression_id: Any = None
    object_identificatie: Any = None
    locatie_identificatie: Any = None
    geometrie_identificatie: Any = None
    object_type: Any = None
    naam: Any = None
    tekstdeel_identificatie: Any = None
    regeltekst_id: Any = None
    api_detail_url: Any = None
    document_url: Any = None
    bron: Any = None
    ophaaldatum: Any = None
    raakt_zoekgebied: Any = None
    volledig_binnen: Any = None
    geometry: Any = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
