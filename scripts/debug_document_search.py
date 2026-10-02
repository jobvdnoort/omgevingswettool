#!/usr/bin/env python3
"""Lokale diagnose van POST /documenten/_zoek met polygon- en puntrequest.

Gebruik:
  export DSO_API_KEY='...'
  python3 scripts/debug_document_search.py pad/naar/zoekgebied.geojson

Schrijft responses naar debug_output/ zonder API-key.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import geopandas as gpd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.geometry_utils import (  # noqa: E402
    bounding_box_rd,
    prepare_search_geometry,
    representative_point_geojson,
    rounded_geojson,
)

ENDPOINT = (
    "https://service.omgevingswet.overheid.nl/publiek/omgevingsinformatie/"
    "api/ontsluiten/v2/documenten/_zoek"
)
CRS_URI = "http://www.opengis.net/def/crs/EPSG/0/28992"


def _count_docs(payload: object) -> tuple[int, str | None]:
    if not isinstance(payload, dict):
        return -1, None
    embedded = payload.get("_embedded")
    if isinstance(embedded, dict) and isinstance(embedded.get("documenten"), list):
        return len(embedded["documenten"]), "_embedded.documenten"
    for key in ("documenten", "content", "results"):
        if isinstance(payload.get(key), list):
            return len(payload[key]), key
    return -1, None


def _safe_headers() -> dict[str, str]:
    key = os.getenv("DSO_API_KEY")
    if not key:
        print("FOUT: DSO_API_KEY ontbreekt in de omgeving.", file=sys.stderr)
        sys.exit(2)
    return {
        "x-api-key": key,
        "Content-Type": "application/json",
        "Accept": "application/hal+json",
        "Content-Crs": CRS_URI,
    }


def _do_request(body: dict, out_dir: Path, label: str) -> None:
    params = {"page": 0, "size": 20}
    headers = _safe_headers()
    started = time.perf_counter()
    response = requests.post(ENDPOINT, params=params, json=body, headers=headers, timeout=60)
    elapsed = (time.perf_counter() - started) * 1000
    request_dump = {
        "endpoint": ENDPOINT,
        "method": "POST",
        "query_params": params,
        "headers": {
            "Content-Type": "application/json",
            "Accept": "application/hal+json",
            "Content-Crs": CRS_URI,
            "x-api-key": "[INGESTELD]",
        },
        "body": body,
    }
    (out_dir / f"request_{label}.json").write_text(
        json.dumps(request_dump, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {"_raw_text": (response.text or "")[:5000]}
    response_dump = {
        "http_status": response.status_code,
        "duration_ms": elapsed,
        "headers": {
            k: v
            for k, v in response.headers.items()
            if k.lower() in {"content-type", "content-crs", "date"} or k.lower().startswith("x-")
            if k.lower() != "x-api-key"
        },
        "body": payload,
    }
    (out_dir / f"response_{label}.json").write_text(
        json.dumps(response_dump, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    count, path = _count_docs(payload)
    print(f"[{label}] HTTP {response.status_code} · documenten={count} · array={path} · {elapsed:.0f} ms")
    if response.status_code >= 400:
        detail = payload.get("detail") if isinstance(payload, dict) else payload
        print(f"[{label}] fout: {detail}")


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Gebruik: {sys.argv[0]} pad/naar/zoekgebied.geojson", file=sys.stderr)
        return 2
    if not os.getenv("DSO_API_KEY"):
        print("FOUT: DSO_API_KEY ontbreekt in de omgeving.", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Bestand niet gevonden: {path}", file=sys.stderr)
        return 2

    frame = gpd.read_file(path)
    search, _ = prepare_search_geometry(frame)
    polygon = rounded_geojson(search)
    point = representative_point_geojson(search)
    bbox = bounding_box_rd(search)

    print(f"Endpoint: {ENDPOINT}")
    print(f"Geometrietype: {polygon['type']}")
    print(f"BBOX RD: {bbox}")
    print(f"Representatief punt RD: {point['coordinates']}")
    print(f"Content-Crs: {CRS_URI}")
    print("Minimale queryparams: page=0 size=20 (geen optionele filters)")

    out_dir = Path("debug_output")
    out_dir.mkdir(parents=True, exist_ok=True)
    _do_request({"geometrie": polygon}, out_dir, "polygon")
    _do_request({"geometrie": point}, out_dir, "point")
    print(f"Responses geschreven naar {out_dir.resolve()} (zonder API-key).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
