"""Veilig inlezen van ondersteunde GIS-formaten."""
from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path
import geopandas as gpd


def read_uploaded_file(filename: str, content: bytes) -> gpd.GeoDataFrame:
    """Lees GeoJSON, GeoPackage of een Shapefile-zip uit bytes."""
    suffix = Path(filename).suffix.lower()
    with tempfile.TemporaryDirectory(prefix="owtool-") as tmp:
        root = Path(tmp)
        if suffix == ".zip":
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    members = [Path(n) for n in archive.namelist()]
                    if any(p.is_absolute() or ".." in p.parts for p in members):
                        raise ValueError("De ZIP bevat een onveilige bestandsnaam.")
                    archive.extractall(root)
            except zipfile.BadZipFile as exc:
                raise ValueError("Het shapefile-zipbestand kan niet worden gelezen.") from exc
            shp = next(root.rglob("*.shp"), None)
            if shp is None:
                raise ValueError("De ZIP bevat geen .shp-bestand.")
            return gpd.read_file(shp)
        path = root / Path(filename).name
        path.write_bytes(content)
        if suffix not in {".geojson", ".json", ".gpkg"}:
            raise ValueError("Ondersteunde invoer: GeoJSON, GeoPackage of Shapefile als ZIP.")
        return gpd.read_file(path)
