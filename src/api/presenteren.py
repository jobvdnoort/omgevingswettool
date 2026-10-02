"""Client voor de actuele Omgevingsdocumenten Presenteren API v8."""
from __future__ import annotations
from typing import Any
from src.api.base_client import BaseClient


class PresenterenClient(BaseClient):
    def get_regulation(self, uri_identificatie: str, geldig_op: str) -> dict[str, Any]:
        return self.json("GET", f"/regelingen/{uri_identificatie}", params={"geldigOp": geldig_op, "_expand": "true"})

    def get_document_structure(self, uri_identificatie: str, geldig_op: str) -> dict[str, Any]:
        return self.json("GET", f"/regelingen/{uri_identificatie}/documentstructuur", params={"geldigOp": geldig_op, "_expand": "true"})

    def find_geometry_identifiers(self, payload: Any) -> list[str]:
        """Vind uitsluitend expliciet benoemde geometrieIdentificatie-waarden."""
        found: list[str] = []
        def walk(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "geometrieIdentificatie" and isinstance(item, str):
                        found.append(item)
                    else:
                        walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
        walk(payload)
        return list(dict.fromkeys(found))
