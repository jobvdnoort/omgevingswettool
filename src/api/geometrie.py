"""Client voor geometrieën opvragen v1."""
from __future__ import annotations
from typing import Any
from src.api.base_client import BaseClient

RD_CRS_URI = "http://www.opengis.net/def/crs/EPSG/0/28992"


class GeometrieClient(BaseClient):
    def get_geometry(self, identifier: str) -> dict[str, Any]:
        return self.json("GET", f"/geometrieen/{identifier}", params={"crs": RD_CRS_URI})
