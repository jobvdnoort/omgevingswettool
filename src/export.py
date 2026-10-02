"""GeoPackage-export en ZIP-verpakking."""
from __future__ import annotations

import csv
import json
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any
import geopandas as gpd
import pandas as pd
from shapely.geometry import shape
from src.geometry_utils import RD_CRS, split_by_geometry_type

LOG = logging.getLogger(__name__)


def _safe_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for record in records:
        row = {}
        for key, value in record.items():
            if key == "geometry":
                continue
            row[key] = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
        rows.append(row)
    return pd.DataFrame(rows)


def export_results(
    output_dir: Path, search_geometry: Any, documents: list[dict[str, Any]],
    geometries: list[dict[str, Any]], warnings: list[str],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    doc_gpkg = output_dir / "01_documenten.gpkg"
    geom_gpkg = output_dir / "02_inhoudelijke_geometrie.gpkg"
    for path in (doc_gpkg, geom_gpkg):
        path.unlink(missing_ok=True)
    gpd.GeoDataFrame({"type": ["zoekgebied"]}, geometry=[search_geometry], crs=RD_CRS).to_file(doc_gpkg, layer="zoekgebied", driver="GPKG")
    if documents:
        contoured = [r for r in documents if r.get("geometry") is not None]
        if contoured:
            gpd.GeoDataFrame(_safe_frame(contoured), geometry=[r["geometry"] for r in contoured], crs=RD_CRS).to_file(doc_gpkg, layer="documentcontouren", driver="GPKG")
        _safe_frame(documents).to_sql("documenten_metadata", __import__("sqlite3").connect(doc_gpkg), if_exists="replace", index=False)
    groups = split_by_geometry_type(geometries)
    for name, rows in groups.items():
        if rows:
            gpd.GeoDataFrame(_safe_frame(rows), geometry=[r["geometry"] for r in rows], crs=RD_CRS).to_file(geom_gpkg, layer=f"locaties_{name}s", driver="GPKG")
    if geometries:
        relations = [{k: r.get(k) for k in ("document_id", "object_identificatie", "locatie_identificatie", "geometrie_identificatie", "object_type")} for r in geometries]
        _safe_frame(relations).to_sql("object_document_relaties", __import__("sqlite3").connect(geom_gpkg), if_exists="replace", index=False)
    (output_dir / "metadata.json").write_text(
        json.dumps(
            {
                "aantal_documenten": len(documents),
                "aantal_geometrieën": len(geometries),
                "waarschuwingen": warnings,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    with (output_dir / "export_log.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["bestand", "status", "toelichting"])
        writer.writerows(
            [
                ("01_documenten.gpkg", "aangemaakt", f"{len(documents)} documenten"),
                ("02_inhoudelijke_geometrie.gpkg", "aangemaakt", f"{len(geometries)} geometrieën"),
                ("metadata.json", "aangemaakt", f"{len(warnings)} waarschuwingen"),
            ]
        )
    zip_path = output_dir / "omgevingswettool_resultaat.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in output_dir.rglob("*"):
            if path.is_file() and path != zip_path:
                archive.write(path, path.relative_to(output_dir))
    return zip_path
