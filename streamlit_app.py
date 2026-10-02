"""Streamlit-interface voor de Omgevingswet GIS Extractor."""
from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path

import fiona
import geopandas as gpd
import pandas as pd
import streamlit as st
from shapely.geometry import shape

from src.api.base_client import DSOApiError
from src.api.geometrie import GeometrieClient
from src.api.ontsluiten import OntsluitenClient
from src.api.presenteren import PresenterenClient
from src.config import ApiConfig, get_api_key
from src.export import export_results
from src.file_reader import read_uploaded_file
from src.geometry_utils import (
    bounding_box_rd,
    geometry_flags,
    prepare_search_geometry,
    representative_point_geojson,
    rounded_geojson,
    RD_CRS,
)
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
        st.write({"bounding_box_rd": bounding_box_rd(search), "gedetecteerd_crs": str(frame.crs)})
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
        try:
            status.info("Documenten zoeken…")
            geometry = rounded_geojson(search)
            point = representative_point_geojson(search)
            bbox = bounding_box_rd(search)
            output = Path(tmp) / "output"
            raw = output / "raw"
            client = OntsluitenClient(ApiConfig().ontsluiten, key)
            # Eerst minimaal request (geen optionele queryfilters); page is 0-based per OpenAPI.
            search_result = client.search_documents(
                geometry,
                valid_on=valid_on,
                include_future=include_future,
                regulation_only=regulation_only,
                max_documents=int(max_documents),
                raw_dir=raw / "documenten",
                minimal=True,
                representative_point=point,
                bbox_rd=bbox,
            )
            docs = search_result.documents
            warnings.extend(search_result.warnings)
            if debug:
                with st.expander("DSO documentzoekactie", expanded=True):
                    dbg = search_result.debug.as_dict()
                    st.json(dbg)
                    st.caption(
                        f"Polygonresultaten: {dbg.get('polygon_result_count')} · "
                        f"Puntresultaten: {dbg.get('point_result_count')} · "
                        f"Arraylocatie: {dbg.get('documents_array_path')}"
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
                        object_raw = raw / "objecten"
                        object_raw.mkdir(parents=True, exist_ok=True)
                        (object_raw / f"{doc.document_id}.json").write_text(
                            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                        )
                        ids = presenter.find_geometry_identifiers(payload)
                        for gid in ids:
                            if gid in seen:
                                continue
                            seen.add(gid)
                            raw_path = raw / "geometrieen"
                            raw_path.mkdir(parents=True, exist_ok=True)
                            geojson = geometry_client.get_geometry(gid)
                            (raw_path / f"{len(seen)}.json").write_text(
                                json.dumps(geojson, ensure_ascii=False), encoding="utf-8"
                            )
                            geom = shape(geojson.get("geometry", geojson))
                            if not geom.intersects(search):
                                continue
                            row = {
                                "document_id": doc.document_id,
                                "document_identificatie": doc.identificatie,
                                "expression_id": doc.expression_id,
                                "geometrie_identificatie": gid,
                                "object_type": None,
                                "bron": "Presenteren + Geometrie Opvragen",
                                "geometry": geom,
                            }
                            row.update(geometry_flags(geom, search))
                            content_rows.append(row)
                    except DSOApiError as exc:
                        warnings.append(f"{doc.document_id}: {exc}")
                    progress.progress(35 + int((index + 1) / max(len(docs), 1) * 50))
            status.info("GeoPackage en ZIP maken…")
            zip_path = export_results(output, search, document_rows, content_rows, warnings)
            progress.progress(100)
            st.success(f"Klaar: {len(docs)} documenten en {len(content_rows)} unieke geometrieën.")
            if warnings:
                st.warning("\n".join(warnings[:20]))
            st.download_button(
                "5. Resultaat downloaden",
                zip_path.read_bytes(),
                "omgevingswettool_resultaat.zip",
                "application/zip",
            )
        except DSOApiError as exc:
            status_code = getattr(exc, "status_code", None)
            if status_code:
                st.error(f"HTTP {status_code}: {exc}")
            else:
                st.error(str(exc))
            if debug and getattr(exc, "response_body", None) is not None:
                with st.expander("DSO foutresponse", expanded=False):
                    st.json(exc.response_body)
            st.stop()
