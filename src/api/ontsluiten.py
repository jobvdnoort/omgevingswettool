"""Client voor Omgevingsinformatie Ontsluiten v2."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src.api.base_client import BaseClient, DSOApiError
from src.config import ApiConfig
from src.models import DocumentRecord

RD_CRS_URI = "http://www.opengis.net/def/crs/EPSG/0/28992"
DOCUMENT_SEARCH_PATH = "/documenten/_zoek"

# OpenAPI: page minimum=0, example=0 (0-based). size maximum=200.
DEFAULT_PAGE = 0
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200


@dataclass
class DocumentSearchDebug:
    """Veilige debuginformatie over de documentzoekactie (zonder API-key)."""

    endpoint: str = ""
    method: str = "POST"
    query_params: dict[str, Any] = field(default_factory=dict)
    request_body: dict[str, Any] = field(default_factory=dict)
    http_status: int | None = None
    response_headers: dict[str, str] = field(default_factory=dict)
    response_body: Any = None
    duration_ms: float | None = None
    geometry_type: str | None = None
    bbox_rd: list[float] | None = None
    representative_point_rd: list[float] | None = None
    documents_array_path: str | None = None
    received_count: int = 0
    normalized_count: int = 0
    page_info: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    polygon_result_count: int | None = None
    point_result_count: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "method": self.method,
            "query_params": self.query_params,
            "request_body": self.request_body,
            "http_status": self.http_status,
            "response_headers": self.response_headers,
            "geometry_type": self.geometry_type,
            "bbox_rd": self.bbox_rd,
            "representative_point_rd": self.representative_point_rd,
            "documents_array_path": self.documents_array_path,
            "received_count": self.received_count,
            "normalized_count": self.normalized_count,
            "page_info": self.page_info,
            "warnings": self.warnings,
            "polygon_result_count": self.polygon_result_count,
            "point_result_count": self.point_result_count,
            "duration_ms": self.duration_ms,
        }


@dataclass
class DocumentSearchResult:
    documents: list[DocumentRecord]
    debug: DocumentSearchDebug
    warnings: list[str] = field(default_factory=list)


def _value(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item and item[key] is not None:
            return item[key]
    return None


def _nested(item: dict[str, Any], *path: str) -> Any:
    current: Any = item
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def find_documents_array(payload: Any) -> tuple[list[Any], str]:
    """Vind de documentenarray in de echte response; verzin geen stille lege lijst."""
    if not isinstance(payload, dict):
        raise DSOApiError(
            "Onverwachte JSON-structuur bij documentzoekactie: response is geen object.",
            response_body=payload,
        )

    candidates: list[tuple[str, Any]] = [
        ("_embedded.documenten", _nested(payload, "_embedded", "documenten")),
        ("documenten", payload.get("documenten")),
        ("content", payload.get("content")),
        ("_embedded.content", _nested(payload, "_embedded", "content")),
        ("results", payload.get("results")),
    ]
    for path, value in candidates:
        if isinstance(value, list):
            return value, path

    embedded = payload.get("_embedded")
    if isinstance(embedded, dict):
        for key, value in embedded.items():
            if isinstance(value, list):
                return value, f"_embedded.{key}"

    raise DSOApiError(
        "Onverwachte JSON-structuur: geen herkenbare documentenarray in de response. "
        "Response is opgeslagen voor diagnose; dit wordt niet als nul documenten behandeld.",
        response_body=payload,
    )


def normalize_documents(payload: Any, fetched_at: str) -> list[DocumentRecord]:
    items, _path = find_documents_array(payload)
    result: list[DocumentRecord] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        uri = _value(item, "uriIdentificatie", "uri_identificatie")
        ident = _value(item, "identificatie")
        ow_meta = item.get("omgevingsdocumentMetadata") if isinstance(item.get("omgevingsdocumentMetadata"), dict) else {}
        imro_meta = item.get("imroDocumentMetadata") if isinstance(item.get("imroDocumentMetadata"), dict) else {}
        bevoegd = item.get("aangeleverdDoorEen") if isinstance(item.get("aangeleverdDoorEen"), dict) else {}
        expression = _value(ow_meta, "expressionId") or _value(item, "expressionId", "expression_id")
        doc_id = str(
            _value(item, "documentId", "document_id", "technischId", "technisch_id")
            or expression
            or uri
            or ident
            or len(result)
        )
        if doc_id in seen:
            continue
        seen.add(doc_id)
        links = item.get("_links") if isinstance(item.get("_links"), dict) else None
        result.append(
            DocumentRecord(
                document_id=doc_id,
                identificatie=ident,
                uri_identificatie=uri,
                expression_id=expression,
                technisch_id=_value(item, "technischId", "technisch_id"),
                titel=_value(item, "titel", "title"),
                document_type=_value(item, "type", "documentType"),
                bron_type="IMRO" if imro_meta else ("OW" if ow_meta else _value(item, "bronType")),
                regelgeving_of_overig=_value(item, "regelgevingOfOverig"),
                bestuurslaag=_value(bevoegd, "bestuurslaag") or _value(item, "bestuurslaag"),
                bevoegd_gezag=_value(bevoegd, "naam") or _value(item, "bevoegdGezag"),
                status=_value(item, "status") or _nested(imro_meta, "planstatusInfo", "planstatus"),
                geldig_vanaf=_value(item, "geldigVanaf"),
                geldig_tot=_value(item, "geldigTot"),
                beschikbaar_op=_value(item, "beschikbaarVanaf", "beschikbaarOp"),
                document_url=_value(ow_meta, "publicatieUrl") or _value(item, "documentUrl"),
                api_detail_url=links,
                download_url=_value(item, "downloadUrl"),
                ophaaldatum=fetched_at,
            )
        )
    return result


def _relevant_headers(headers: Any) -> dict[str, str]:
    wanted = {
        "content-type",
        "content-crs",
        "x-request-id",
        "x-correlation-id",
        "date",
        "api-version",
    }
    result: dict[str, str] = {}
    for key, value in dict(headers or {}).items():
        lowered = str(key).lower()
        if lowered in wanted or lowered.startswith("x-"):
            if lowered == "x-api-key":
                continue
            result[str(key)] = str(value)
    return result


def _write_raw(raw_dir: Path | None, name: str, payload: Any) -> None:
    if raw_dir is None:
        return
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def _page_size(requested: int) -> int:
    return max(1, min(int(requested), MAX_PAGE_SIZE))


def _has_next_page(payload: dict[str, Any], current_page: int) -> bool:
    links = payload.get("_links") if isinstance(payload.get("_links"), dict) else {}
    if isinstance(links.get("next"), dict) and links["next"].get("href"):
        return True
    page = payload.get("page") if isinstance(payload.get("page"), dict) else {}
    if not page:
        return False
    total_pages = page.get("totalPages")
    number = page.get("number", current_page)
    if isinstance(total_pages, int):
        # page.number is 0-based in deze API.
        return int(number) + 1 < int(total_pages)
    total_elements = page.get("totalElements")
    size = page.get("size")
    if isinstance(total_elements, int) and isinstance(size, int) and size > 0:
        return (int(number) + 1) * size < total_elements
    return False


class OntsluitenClient(BaseClient):
    def __init__(self, base_url: str, api_key: str, config: ApiConfig | None = None):
        super().__init__(base_url, api_key, config)
        self.last_debug = DocumentSearchDebug()

    def _build_params(
        self,
        *,
        page: int,
        size: int,
        valid_on: date | None,
        include_future: bool,
        beschikbaar_op: str | None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page": int(page), "size": _page_size(size)}
        # Alleen officieel ondersteunde queryparameters; defaults weglaten.
        if valid_on is not None:
            params["geldigOp"] = valid_on.isoformat()
        if include_future:
            params["inclusiefToekomstigGeldig"] = "true"
        if beschikbaar_op:
            params["beschikbaarOp"] = beschikbaar_op
        return params

    def _build_body(self, geometry: dict[str, Any], regulation_only: bool) -> dict[str, Any]:
        if not isinstance(geometry, dict) or "type" not in geometry or "coordinates" not in geometry:
            raise DSOApiError("Zoekgeometrie mist type/coordinates.")
        # Body niet extra nesten: geometrie staat direct onder de root.
        body: dict[str, Any] = {"geometrie": geometry}
        if regulation_only:
            body["regelgevingOfOverig"] = "REGELGEVING"
        return body

    def _post_zoek(
        self,
        body: dict[str, Any],
        params: dict[str, Any],
        *,
        raw_dir: Path | None,
        page_label: str,
    ) -> tuple[Any, DocumentSearchDebug]:
        endpoint = f"{self.base_url}{DOCUMENT_SEARCH_PATH}"
        headers = {"Content-Crs": RD_CRS_URI}
        started = time.perf_counter()
        debug = DocumentSearchDebug(
            endpoint=endpoint,
            method="POST",
            query_params=dict(params),
            request_body=body,
            geometry_type=str(body.get("geometrie", {}).get("type")),
        )
        request_dump = {
            "endpoint": endpoint,
            "method": "POST",
            "query_params": params,
            "headers": {"Content-Type": "application/json", "Content-Crs": RD_CRS_URI},
            "body": body,
        }
        _write_raw(raw_dir, f"request_{page_label}.json", request_dump)
        try:
            response = self.request(
                "POST",
                DOCUMENT_SEARCH_PATH,
                params=params,
                json=body,
                headers=headers,
            )
            duration_ms = (time.perf_counter() - started) * 1000
            try:
                payload = response.json()
            except ValueError as exc:
                debug.http_status = response.status_code
                debug.response_headers = _relevant_headers(response.headers)
                debug.duration_ms = duration_ms
                debug.response_body = (response.text or "")[:2000]
                _write_raw(
                    raw_dir,
                    f"response_{page_label}.json",
                    {
                        "http_status": response.status_code,
                        "headers": debug.response_headers,
                        "body_text": debug.response_body,
                        "duration_ms": duration_ms,
                    },
                )
                raise DSOApiError(
                    f"DSO gaf geen geldige JSON terug voor documentzoekactie (HTTP {response.status_code}).",
                    status_code=response.status_code,
                    response_body=debug.response_body,
                    endpoint=endpoint,
                    method="POST",
                ) from exc
            debug.http_status = response.status_code
            debug.response_headers = _relevant_headers(response.headers)
            debug.response_body = payload
            debug.duration_ms = duration_ms
            debug.page_info = payload.get("page") if isinstance(payload, dict) else None
            _write_raw(
                raw_dir,
                f"response_{page_label}.json",
                {
                    "http_status": response.status_code,
                    "headers": debug.response_headers,
                    "duration_ms": duration_ms,
                    "body": payload,
                },
            )
            return payload, debug
        except DSOApiError as exc:
            duration_ms = (time.perf_counter() - started) * 1000
            debug.http_status = exc.status_code
            debug.duration_ms = duration_ms
            debug.response_body = exc.response_body
            debug.warnings.append(str(exc))
            _write_raw(
                raw_dir,
                f"response_{page_label}.json",
                {
                    "http_status": exc.status_code,
                    "duration_ms": duration_ms,
                    "error": str(exc),
                    "body": exc.response_body,
                },
            )
            self.last_debug = debug
            raise

    def search_documents(
        self,
        geometry: dict[str, Any],
        valid_on: date | None = None,
        include_future: bool = False,
        regulation_only: bool = False,
        max_documents: int = 50,
        raw_dir: Any = None,
        *,
        minimal: bool = True,
        representative_point: dict[str, Any] | None = None,
        bbox_rd: list[float] | None = None,
        page_size: int | None = None,
    ) -> DocumentSearchResult:
        """Zoek documenten. Lege resultaten alleen bij HTTP 200 + herkende lege array."""
        raw_path = Path(raw_dir) if raw_dir is not None else None
        # Minimale request: page/size + geometrie. Optionele queryfilters alleen
        # meesturen wanneer expliciet gevraagd (geen defaults die leegte maskeren).
        default_size = DEFAULT_PAGE_SIZE if minimal else min(self.config.page_size, MAX_PAGE_SIZE)
        size = _page_size(page_size or min(default_size, max_documents))
        params = self._build_params(
            page=DEFAULT_PAGE,
            size=size,
            valid_on=None if minimal else valid_on,
            include_future=include_future,
            beschikbaar_op=None,
        )
        body = self._build_body(geometry, regulation_only=regulation_only)

        warnings: list[str] = []
        records: list[DocumentRecord] = []
        seen: set[str] = set()
        fetched_at = datetime.now(timezone.utc).isoformat()
        aggregate = DocumentSearchDebug(
            endpoint=f"{self.base_url}{DOCUMENT_SEARCH_PATH}",
            method="POST",
            query_params=dict(params),
            request_body=body,
            geometry_type=str(geometry.get("type")),
            bbox_rd=bbox_rd,
            representative_point_rd=(
                list(representative_point.get("coordinates"))
                if isinstance(representative_point, dict) and isinstance(representative_point.get("coordinates"), list)
                else None
            ),
        )

        page = DEFAULT_PAGE
        array_path: str | None = None
        received_total = 0
        human_page = 1

        while len(records) < max_documents:
            params = dict(params)
            params["page"] = page
            # Bestandsnamen request_page_1 / response_page_1 (1-based label; API-page is 0-based).
            file_label = f"page_{human_page}"
            payload, page_debug = self._post_zoek(body, params, raw_dir=raw_path, page_label=file_label)
            if not isinstance(payload, dict):
                raise DSOApiError("Onverwachte JSON-structuur: response is geen object.", response_body=payload)

            try:
                items, array_path = find_documents_array(payload)
            except DSOApiError as exc:
                warnings.append(str(exc))
                aggregate.warnings = warnings
                aggregate.http_status = page_debug.http_status
                aggregate.response_body = payload
                aggregate.duration_ms = page_debug.duration_ms
                self.last_debug = aggregate
                raise

            if human_page == 1:
                aggregate.http_status = page_debug.http_status
                aggregate.response_headers = page_debug.response_headers
                aggregate.response_body = payload
                aggregate.duration_ms = page_debug.duration_ms
                aggregate.documents_array_path = array_path
                aggregate.page_info = payload.get("page") if isinstance(payload.get("page"), dict) else None

            received_total += len(items)
            page_records = normalize_documents(payload, fetched_at)
            for record in page_records:
                if record.document_id in seen:
                    continue
                seen.add(record.document_id)
                records.append(record)
                if len(records) >= max_documents:
                    break

            if not _has_next_page(payload, page):
                break
            page += 1
            human_page += 1
            if page > 10_000:
                warnings.append("Paginering gestopt: onverwacht hoog paginanummer.")
                break

        aggregate.received_count = received_total
        aggregate.normalized_count = len(records)
        aggregate.documents_array_path = array_path
        aggregate.polygon_result_count = len(records)
        aggregate.query_params = dict(params)
        aggregate.request_body = body

        # Diagnostische fallback: polygon 0 resultaten → representatief punt.
        if len(records) == 0 and representative_point is not None:
            point_body = self._build_body(representative_point, regulation_only=False)
            point_params = self._build_params(
                page=DEFAULT_PAGE,
                size=size,
                valid_on=None,
                include_future=False,
                beschikbaar_op=None,
            )
            point_payload, point_debug = self._post_zoek(
                point_body, point_params, raw_dir=raw_path, page_label="point_page_1"
            )
            point_items, point_path = find_documents_array(point_payload)
            point_records = normalize_documents(point_payload, fetched_at)
            aggregate.point_result_count = len(point_records)
            msg = (
                f"Polygonrequest: 0 documenten. Diagnostisch puntrequest: {len(point_records)} documenten "
                f"(arraylocatie {point_path})."
            )
            warnings.append(msg)
            aggregate.warnings.extend(warnings)
            if point_records:
                warnings.append(
                    "Het zoekgebied-vlak leverde geen treffers, het representatieve punt wel. "
                    "Controleer coördinatenprecisie/nesting; polygonrequest blijft leidend."
                )
            # Polygon blijft leidend: we vervangen de resultaten niet stilzwijgend.
            aggregate.response_headers = point_debug.response_headers or aggregate.response_headers
        elif len(records) == 0:
            aggregate.point_result_count = None
            warnings.append("Documentzoekactie HTTP 200 met herkende lege documentenarray.")

        aggregate.warnings = list(dict.fromkeys(warnings))
        self.last_debug = aggregate
        return DocumentSearchResult(documents=records[:max_documents], debug=aggregate, warnings=aggregate.warnings)
