"""Streamlit-interface voor de Omgevingswet GIS Extractor."""
from __future__ import annotations

import io
import json
import tempfile
from datetime import date
from pathlib import Path
import geopandas as gpd
import pandas as pd
import streamlit as st
import fiona
from shapely.geometry import shape

from src.api.base_client import DSOApiError
from src.api.geometrie import GeometrieClient
from src.api.ontsluiten import OntsluitenClient
from src.api.presenteren import PresenterenClient
from src.config import ApiConfig, get_api_key
from src.export import export_results
from src.file_reader import read_uploaded_file
from src.geometry_utils import geometry_flags, prepare_search_geometry, rounded_geojson, RD_CRS
from src.logging_config import configure_logging

st.set_page_config(page_title="Omgevingswet GIS Extractor", layout="wide")
configure_logging(False)
st.title("Omgevingswet GIS Extractor")
st.caption("Upload een onderzoeksgebied en download de rakende omgevingsdocumenten en regelgeometrieën.")

st.subheader("1. Onderzoeksgebied uploaden")
uploaded = st.file_uploader("GeoJSON, GeoPackage of Shapefile als ZIP", type=["geojson", "json", "gpkg", "zip"])
frame = None
search = None
if uploaded:
    try:
        frame = read_uploaded_file(uploaded.name, uploaded.getvalue())
        search, valid = prepare_search_geometry(frame)
        st.success(f"{uploaded.name} gelezen: {len(valid)} object(en), CRS {frame.crs}, {search.area / 10_000:.2f} ha.")
        st.write({"bounding_box_rd": [round(v, 3) for v in search.bounds], "gedetecteerd_crs": str(frame.crs)})
        centroid = gpd.GeoDataFrame(geometry=[search], crs=RD_CRS).to_crs(4326).geometry.iloc[0].centroid
        st.map(pd.DataFrame({"lat": [centroid.y], "lon": [centroid.x]}), zoom=10)
    except (ValueError, OSError, fiona.errors.FionaError) as exc:
        st.error(str(exc))

st.subheader("2. Zoekinstellingen")
valid_on = st.date_input("Geldig op", value=date.today())
include_future = st.checkbox("Inclusief toekomstige documenten")
regulation_only = st.radio("Documenttypen", ["Alle documenten", "Alleen regelgeving"]) == "Alleen regelgeving"
content_geometry = st.checkbox("Ook inhoudelijke geometrieën ophalen", value=True)
max_documents = st.number_input("Maximum aantal documenten", min_value=1, max_value=500, value=50)
debug = st.checkbox("Debugmodus")

if st.button("3. Documenten ophalen en 4. Geometrieën verwerken", type="primary", disabled=search is None):
    key = get_api_key()
    if not key:
        st.error("Geen DSO API-key gevonden. Stel DSO_API_KEY in als omgevingsvariabele of in Streamlit secrets.")
        st.stop()
    progress = st.progress(0)
    status = st.empty()
    warnings: list[str] = []
    with tempfile.TemporaryDirectory(prefix="owtool-session-") as tmp:
        raw = Path(tmp) / "raw"
        try:
            status.info("Documenten zoeken…")
            docs = OntsluitenClient(ApiConfig().ontsluiten, key).search_documents(
                rounded_geojson(search), valid_on, include_future, regulation_only, int(max_documents), raw / "documenten"
            )
            progress.progress(35)
            status.info(f"{len(docs)} documenten gevonden; contouren worden verwerkt…")
            document_rows = [d.as_dict() for d in docs]
            content_rows: list[dict] = []
            if content_geometry:
                presenter = PresenterenClient(ApiConfig().presenteren, key)
                geometry_client = GeometrieClient(ApiConfig().geometrie, key)
                seen: set[str] = set()
                for index, doc in enumerate(docs):
                    if not doc.uri_identificatie or doc.regelgeving_of_overig == "OVERIG":
                        continue
                    try:
                        payload = presenter.get_document_structure(str(doc.uri_identificatie), valid_on.isoformat())
                        ids = presenter.find_geometry_identifiers(payload)
                        for gid in ids:
                            if gid in seen:
                                continue
                            seen.add(gid)
                            raw_path = raw / "geometrieen"
                            raw_path.mkdir(parents=True, exist_ok=True)
                            geojson = geometry_client.get_geometry(gid)
                            (raw_path / f"{len(seen)}.json").write_text(json.dumps(geojson, ensure_ascii=False), encoding="utf-8")
                            geom = shape(geojson.get("geometry", geojson))
                            if not geom.intersects(search):
                                continue
                            row = {"document_id": doc.document_id, "document_identificatie": doc.identificatie, "expression_id": doc.expression_id, "geometrie_identificatie": gid, "object_type": None, "bron": "Presenteren + Geometrie Opvragen", "geometry": geom}
                            row.update(geometry_flags(geom, search))
                            content_rows.append(row)
                    except DSOApiError as exc:
                        warnings.append(f"{doc.document_id}: {exc}")
                    progress.progress(35 + int((index + 1) / max(len(docs), 1) * 50))
            status.info("GeoPackage en ZIP maken…")
            output = Path(tmp) / "output"
            zip_path = export_results(output, search, document_rows, content_rows, warnings)
            progress.progress(100)
            st.success(f"Klaar: {len(docs)} documenten en {len(content_rows)} unieke geometrieën.")
            if warnings:
                st.warning("\n".join(warnings[:10]))
            st.download_button("5. Resultaat downloaden", zip_path.read_bytes(), "omgevingswettool_resultaat.zip", "application/zip")
        except DSOApiError as exc:
            st.error(str(exc))
