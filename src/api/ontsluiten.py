"""Client voor Omgevingsinformatie Ontsluiten v2."""
from __future__ import annotations
from datetime import date
from typing import Any
from src.api.base_client import BaseClient
from src.config import ApiConfig
from src.models import DocumentRecord


def _value(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item:
            return item[key]
    return None


def normalize_documents(payload: Any, fetched_at: str) -> list[DocumentRecord]:
    items = payload.get("_embedded", {}).get("documenten", []) if isinstance(payload, dict) else []
    if not items and isinstance(payload, dict):
        items = payload.get("documenten", payload.get("content", []))
    result: list[DocumentRecord] = []
    seen: set[str] = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        uri = _value(item, "uriIdentificatie", "uri_identificatie")
        ident = _value(item, "identificatie")
        doc_id = str(_value(item, "documentId", "document_id", "technischId", "technisch_id", "expressionId", "expression_id") or uri or ident or len(result))
        if doc_id in seen:
            continue
        seen.add(doc_id)
        result.append(DocumentRecord(
            document_id=doc_id, identificatie=ident, uri_identificatie=uri,
            expression_id=_value(item, "expressionId", "expression_id"),
            technisch_id=_value(item, "technischId", "technisch_id"),
            titel=_value(item, "titel", "title"), document_type=_value(item, "documentType"),
            bron_type=_value(item, "bronType"), regelgeving_of_overig=_value(item, "regelgevingOfOverig"),
            bestuurslaag=_value(item, "bestuurslaag"), bevoegd_gezag=_value(item, "bevoegdGezag"),
            status=_value(item, "status"), geldig_vanaf=_value(item, "geldigVanaf"),
            geldig_tot=_value(item, "geldigTot"), beschikbaar_op=_value(item, "beschikbaarOp"),
            document_url=_value(item, "documentUrl"), api_detail_url=_value(item, "_links"),
            download_url=_value(item, "downloadUrl"), ophaaldatum=fetched_at,
        ))
    return result


class OntsluitenClient(BaseClient):
    def search_documents(
        self, geometry: dict[str, Any], valid_on: date, include_future: bool,
        regulation_only: bool, max_documents: int, raw_dir: Any = None,
    ) -> list[DocumentRecord]:
        params = {"geldigOp": valid_on.isoformat(), "inclusiefToekomstigGeldig": str(include_future).lower(), "page": 1, "size": min(self.config.page_size, max_documents)}
        body: dict[str, Any] = {"geometrie": geometry}
        if regulation_only:
            body["regelgevingOfOverig"] = "REGELGEVING"
        records: list[DocumentRecord] = []
        while len(records) < max_documents:
            payload = self.json("POST", "/documenten/_zoek", params=params, json=body, headers={"Content-Crs": "EPSG:28992"})
            if raw_dir:
                raw_dir.mkdir(parents=True, exist_ok=True)
                (raw_dir / f"pagina_{params['page']}.json").write_text(__import__("json").dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            records.extend(normalize_documents(payload, __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()))
            page = payload.get("page", {}) if isinstance(payload, dict) else {}
            if not page or page.get("number", params["page"]) + 1 >= page.get("totalPages", params["page"]):
                break
            params["page"] += 1
        return records[:max_documents]
