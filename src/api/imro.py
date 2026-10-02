"""Geïsoleerde IMRO-module.

De officiële DSO geometrie-opvraag-API ondersteunt geen IMRO-detailgeometrieën.
IMRO-documenten blijven daarom metadata in het MVP.
"""
from __future__ import annotations
from typing import Any


class IMROClient:
    """Placeholder zonder verzonnen Ruimtelijke Plannen-endpoints."""

    def plan_contour(self, document: dict[str, Any]) -> None:
        return None
