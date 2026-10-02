"""Tests voor documentzoekactie, geometrie-nesting en HTTP-foutafhandeling."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import responses
from shapely.geometry import MultiPolygon, Polygon

from src.api.base_client import BaseClient, DSOApiError, redact_request_headers
from src.api.ontsluiten import (
    ACCEPT_HAL_JSON,
    RD_CRS_URI,
    OntsluitenClient,
    find_documents_array,
    normalize_documents,
)
from src.config import get_api_key
from src.geometry_utils import rounded_geojson

BASE = "https://service.omgevingswet.overheid.nl/publiek/omgevingsinformatie/api/ontsluiten/v2"
ZOEK = f"{BASE}/documenten/_zoek"

SAMPLE_DOC = {
    "uriIdentificatie": "/akn/nl/act/gm0301/2020/omgevingsplan",
    "identificatie": "/akn/nl/act/gm0301/2020/omgevingsplan",
    "titel": "Omgevingsplan Zutphen",
    "type": "Omgevingsplan",
    "versie": 1,
    "aangeleverdDoorEen": {"bestuurslaag": "GEMEENTE", "code": "gm0301", "naam": "gemeente Zutphen"},
    "omgevingsdocumentMetadata": {"expressionId": "expr-1", "publicatieUrl": "https://example.nl"},
    "geometrieIdentificaties": [],
    "heeftVectorTiles": False,
    "beschikbaarVanaf": "2024-01-01",
    "_links": {"self": {"href": "https://example"}},
}


def _page_payload(docs, *, number=0, total_pages=1, total_elements=None):
    return {
        "_embedded": {"documenten": docs},
        "_links": {"self": {"href": ZOEK}},
        "page": {
            "size": 20,
            "totalElements": total_elements if total_elements is not None else len(docs),
            "totalPages": total_pages,
            "number": number,
        },
    }


@pytest.fixture
def client():
    return OntsluitenClient(BASE, "test-key")


@responses.activate
def test_http_200_with_documents_in_embedded(client, tmp_path):
    responses.add(responses.POST, ZOEK, json=_page_payload([SAMPLE_DOC]), status=200)
    result = client.search_documents(
        {"type": "Point", "coordinates": [155000.0, 463000.0]},
        max_documents=10,
        raw_dir=tmp_path,
        representative_point=None,
    )
    assert len(result.documents) == 1
    assert result.documents[0].titel == "Omgevingsplan Zutphen"
    assert result.debug.documents_array_path == "_embedded.documenten"
    assert result.debug.http_status == 200
    assert (tmp_path / "request_page_1.json").exists()
    assert (tmp_path / "response_page_1.json").exists()
    request_body = json.loads((tmp_path / "request_page_1.json").read_text())
    dumped = json.dumps(request_body)
    assert "test-key" not in dumped
    assert request_body["headers"].get("x-api-key") == "[INGESTELD]"
    assert request_body["query_params"]["page"] == 0
    assert request_body["headers"]["Content-Crs"] == RD_CRS_URI
    assert request_body["headers"]["Accept"] == ACCEPT_HAL_JSON
    assert request_body["headers"]["Content-Type"] == "application/json"
    assert not request_body["headers"]["Content-Crs"].endswith(",")
    assert result.debug.request_headers.get("x-api-key") == "[INGESTELD]"


@responses.activate
def test_http_200_empty_documents_array(client, tmp_path):
    responses.add(responses.POST, ZOEK, json=_page_payload([]), status=200)
    result = client.search_documents(
        {"type": "Polygon", "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]]},
        max_documents=10,
        raw_dir=tmp_path,
        representative_point=None,
    )
    assert result.documents == []
    assert result.debug.http_status == 200
    assert result.debug.documents_array_path == "_embedded.documenten"
    assert any("lege documentenarray" in w for w in result.warnings)


@responses.activate
def test_http_400_with_error_body(client, tmp_path):
    responses.add(
        responses.POST,
        ZOEK,
        json={"title": "Bad Request", "detail": "Ongeldige parameter", "status": 400},
        status=400,
    )
    with pytest.raises(DSOApiError) as exc:
        client.search_documents({"type": "Point", "coordinates": [1, 2]}, raw_dir=tmp_path)
    assert exc.value.status_code == 400
    assert "400" in str(exc.value)
    assert (tmp_path / "response_page_1.json").exists()


@responses.activate
@pytest.mark.parametrize("status", [401, 403])
def test_http_401_or_403(client, status, tmp_path):
    responses.add(
        responses.POST,
        ZOEK,
        json={"title": "Forbidden", "detail": "Geen toegang", "status": status},
        status=status,
    )
    with pytest.raises(DSOApiError) as exc:
        client.search_documents({"type": "Point", "coordinates": [1, 2]}, raw_dir=tmp_path)
    assert exc.value.status_code == status


@responses.activate
def test_http_422_invalid_geometry(client, tmp_path):
    responses.add(
        responses.POST,
        ZOEK,
        json={"title": "Unprocessable Entity", "detail": "Ongeldige geometrie", "status": 422},
        status=422,
    )
    with pytest.raises(DSOApiError) as exc:
        client.search_documents({"type": "Point", "coordinates": [1]}, raw_dir=tmp_path)
    assert exc.value.status_code == 422
    assert "Ongeldige geometrie" in str(exc.value)


def test_unexpected_json_structure_raises(client):
    with pytest.raises(DSOApiError, match="geen herkenbare documentenarray"):
        find_documents_array({"page": {"number": 0}, "_links": {}})


def test_polygon_nesting_is_correct():
    poly = Polygon([(155000, 463000), (155100, 463000), (155100, 463100), (155000, 463000)])
    geo = rounded_geojson(poly)
    assert geo["type"] == "Polygon"
    assert isinstance(geo["coordinates"], list)
    assert isinstance(geo["coordinates"][0], list)
    assert isinstance(geo["coordinates"][0][0], list)
    assert len(geo["coordinates"][0][0]) == 2
    assert geo["coordinates"][0][0] == geo["coordinates"][0][-1]


def test_multipolygon_nesting_is_correct():
    multi = MultiPolygon(
        [
            Polygon([(155000, 463000), (155050, 463000), (155050, 463050), (155000, 463000)]),
            Polygon([(155100, 463100), (155150, 463100), (155150, 463150), (155100, 463100)]),
        ]
    )
    geo = rounded_geojson(multi)
    assert geo["type"] == "MultiPolygon"
    assert isinstance(geo["coordinates"][0][0][0], list)
    assert len(geo["coordinates"][0][0][0]) == 2


def test_content_crs_header_has_no_trailing_comma(client):
    assert RD_CRS_URI == "http://www.opengis.net/def/crs/EPSG/0/28992"
    assert not RD_CRS_URI.endswith(",")


def test_missing_api_key_raises():
    with pytest.raises(DSOApiError, match="API-key ontbreekt"):
        OntsluitenClient(BASE, "")


def test_missing_api_key_env(monkeypatch):
    monkeypatch.delenv("DSO_API_KEY", raising=False)
    assert get_api_key() is None


@responses.activate
def test_polygon_zero_point_has_results(client, tmp_path):
    polygon = {
        "type": "Polygon",
        "coordinates": [[[155000.0, 463000.0], [155100.0, 463000.0], [155100.0, 463100.0], [155000.0, 463000.0]]],
    }
    point = {"type": "Point", "coordinates": [155050.0, 463050.0]}

    def request_callback(request):
        body = json.loads(request.body.decode())
        geom = body["geometrie"]
        if geom["type"] == "Polygon":
            return (200, {}, json.dumps(_page_payload([])))
        return (200, {}, json.dumps(_page_payload([SAMPLE_DOC])))

    responses.add_callback(responses.POST, ZOEK, callback=request_callback, content_type="application/json")
    result = client.search_documents(
        polygon,
        max_documents=10,
        raw_dir=tmp_path,
        representative_point=point,
    )
    assert result.documents == []
    assert result.debug.polygon_result_count == 0
    assert result.debug.point_result_count == 1
    assert any("Polygonrequest: 0" in w for w in result.warnings)
    assert (tmp_path / "request_point_page_1.json").exists()


def test_missing_response_fields_do_not_crash():
    payload = _page_payload([{"uriIdentificatie": "only-uri"}])
    docs = normalize_documents(payload, "now")
    assert len(docs) == 1
    assert docs[0].titel is None
    assert docs[0].document_type is None
    assert docs[0].uri_identificatie == "only-uri"


def test_normalize_deduplicates():
    payload = _page_payload([{"uriIdentificatie": "a"}, {"uriIdentificatie": "a"}])
    assert len(normalize_documents(payload, "now")) == 1


@responses.activate
def test_minimal_request_omits_optional_filters(client):
    responses.add(responses.POST, ZOEK, json=_page_payload([SAMPLE_DOC]), status=200)
    client.search_documents({"type": "Point", "coordinates": [155000, 463000]}, minimal=True)
    assert len(responses.calls) == 1
    qs = responses.calls[0].request.params
    # responses may expose params differently; inspect URL.
    url = responses.calls[0].request.url
    assert "page=0" in url
    assert "geldigOp" not in url
    assert "inclusiefToekomstigGeldig" not in url
    assert "beschikbaarOp" not in url
    assert responses.calls[0].request.headers["Content-Crs"] == RD_CRS_URI
    body = json.loads(responses.calls[0].request.body)
    assert set(body.keys()) == {"geometrie"}


@responses.activate
def test_document_search_sends_hal_accept_and_json_content_type(client):
    responses.add(responses.POST, ZOEK, json=_page_payload([SAMPLE_DOC]), status=200)
    client.search_documents({"type": "Point", "coordinates": [155000.0, 463000.0]})
    assert len(responses.calls) == 1
    headers = responses.calls[0].request.headers
    assert headers["Accept"] == "application/hal+json"
    assert headers["Content-Type"] == "application/json"
    assert headers["Content-Crs"] == "http://www.opengis.net/def/crs/EPSG/0/28992"
    assert headers["Accept"] == ACCEPT_HAL_JSON
    assert headers["Content-Crs"] == RD_CRS_URI


@responses.activate
def test_base_client_does_not_override_hal_accept_with_application_json():
    """Regressie: globale/sessie-Accept mag HAL niet terugzetten naar application/json."""
    client = OntsluitenClient(BASE, "test-key")
    # Simuleer een verkeerde globale default die eerder 406 veroorzaakte.
    client.session.headers["Accept"] = "application/json"
    responses.add(responses.POST, ZOEK, json=_page_payload([SAMPLE_DOC]), status=200)
    client.search_documents({"type": "Point", "coordinates": [155000.0, 463000.0]})
    assert responses.calls[0].request.headers["Accept"] == "application/hal+json"
    assert responses.calls[0].request.headers["Content-Type"] == "application/json"
    assert client.accept == ACCEPT_HAL_JSON


def test_redact_request_headers_hides_api_key():
    redacted = redact_request_headers(
        {
            "Accept": ACCEPT_HAL_JSON,
            "Content-Type": "application/json",
            "Content-Crs": RD_CRS_URI,
            "x-api-key": "super-geheim",
        }
    )
    assert redacted["x-api-key"] == "[INGESTELD]"
    assert redacted["Accept"] == ACCEPT_HAL_JSON
    assert "super-geheim" not in redacted.values()


def test_ontsluiten_client_default_accept_is_hal():
    client = OntsluitenClient(BASE, "test-key")
    assert client.accept == ACCEPT_HAL_JSON
    assert client.session.headers["Accept"] == ACCEPT_HAL_JSON
    # Andere clients behouden JSON-accept tenzij anders geconfigureerd.
    other = BaseClient(BASE, "test-key")
    assert other.accept == "application/json"


@responses.activate
def test_pagination_uses_zero_based_pages(client):
    responses.add(responses.POST, ZOEK, json=_page_payload([SAMPLE_DOC], number=0, total_pages=2, total_elements=2), status=200)
    doc2 = dict(SAMPLE_DOC)
    doc2["uriIdentificatie"] = "/akn/other"
    doc2["identificatie"] = "/akn/other"
    doc2["omgevingsdocumentMetadata"] = {"expressionId": "expr-2", "publicatieUrl": "https://example.nl/2"}
    responses.add(responses.POST, ZOEK, json=_page_payload([doc2], number=1, total_pages=2, total_elements=2), status=200)
    result = client.search_documents({"type": "Point", "coordinates": [1, 2]}, max_documents=10, page_size=1)
    assert len(result.documents) == 2
    assert "page=0" in responses.calls[0].request.url
    assert "page=1" in responses.calls[1].request.url
