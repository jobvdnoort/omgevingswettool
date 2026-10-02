"""Gemeenschappelijke HTTP-client met retries en logging."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from src.config import ApiConfig

LOG = logging.getLogger(__name__)

# Permanente clientfouten: niet opnieuw proberen.
NON_RETRYABLE_STATUS = {400, 401, 403, 404, 422}
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class DSOApiError(RuntimeError):
    """Nette fout voor een DSO-request."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: Any = None,
        endpoint: str | None = None,
        method: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        self.endpoint = endpoint
        self.method = method


def safe_error_text(response: requests.Response) -> str:
    """Haal een veilige, korte fouttekst uit een response zonder secrets."""
    try:
        payload = response.json()
    except ValueError:
        text = (response.text or "").strip()
        return text[:500] if text else response.reason or "onbekende fout"
    if isinstance(payload, dict):
        for key in ("detail", "title", "message", "foutmelding"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:500]
        return str({k: payload[k] for k in list(payload)[:6]})[:500]
    return str(payload)[:500]


def redact_request_headers(headers: Any) -> dict[str, str]:
    """Kopieer requestheaders voor logging/debug; verberg de API-key."""
    result: dict[str, str] = {}
    for key, value in dict(headers or {}).items():
        if str(key).lower() == "x-api-key":
            result[str(key)] = "[INGESTELD]"
        else:
            result[str(key)] = str(value)
    return result


class BaseClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        config: ApiConfig | None = None,
        *,
        accept: str | None = None,
    ):
        if not api_key or not str(api_key).strip():
            raise DSOApiError("DSO API-key ontbreekt. Stel DSO_API_KEY in.")
        self.base_url = base_url.rstrip("/")
        self.config = config or ApiConfig()
        # Accept is per API configureerbaar; default JSON voor overige clients.
        self.accept = accept if accept is not None else "application/json"
        self.session = requests.Session()
        # Geen harde Accept: application/json die latere HAL-headers overschrijft:
        # Accept komt uit self.accept en kan per request nog worden gezet.
        self.session.headers.update(
            {
                "x-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": self.accept,
            }
        )

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def merge_headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        """Samenvoegen van sessie- en requestheaders; request wint bij conflicten."""
        merged = {str(k): str(v) for k, v in self.session.headers.items()}
        if headers:
            merged.update({str(k): str(v) for k, v in headers.items()})
        return merged

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = self._url(path)
        # Zorg dat een expliciete Accept op het request de sessiewaarde overschrijft.
        request_headers = dict(kwargs.pop("headers", None) or {})
        if "Accept" not in request_headers and "accept" not in {k.lower() for k in request_headers}:
            request_headers["Accept"] = self.accept
        kwargs["headers"] = request_headers
        last_error: Exception | None = None
        for attempt in range(self.config.retries + 1):
            try:
                response = self.session.request(method, url, timeout=self.config.timeout, **kwargs)
                status = response.status_code
                if status in RETRYABLE_STATUS:
                    if attempt == self.config.retries:
                        raise DSOApiError(
                            f"HTTP {status} bij {method} {path}: {safe_error_text(response)}",
                            status_code=status,
                            response_body=_safe_json_or_text(response),
                            endpoint=url,
                            method=method,
                        )
                    LOG.warning("Tijdelijke DSO-fout %s voor %s (poging %s)", status, path, attempt + 1)
                    time.sleep(2**attempt)
                    continue
                if status >= 400 or status in NON_RETRYABLE_STATUS:
                    raise DSOApiError(
                        f"HTTP {status} bij {method} {path}: {safe_error_text(response)}",
                        status_code=status,
                        response_body=_safe_json_or_text(response),
                        endpoint=url,
                        method=method,
                    )
                return response
            except DSOApiError:
                raise
            except requests.RequestException as exc:
                last_error = exc
                if attempt == self.config.retries:
                    raise DSOApiError(
                        f"DSO-request mislukt ({method} {path}): {exc}",
                        endpoint=url,
                        method=method,
                    ) from exc
                LOG.warning("Netwerkfout voor %s (poging %s)", path, attempt + 1)
                time.sleep(2**attempt)
        raise DSOApiError(f"DSO-request mislukt ({method} {path}): {last_error}", endpoint=url, method=method)

    def json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.request(method, path, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise DSOApiError(
                f"DSO gaf geen geldige JSON terug voor {path} (HTTP {response.status_code}).",
                status_code=response.status_code,
                response_body=(response.text or "")[:2000],
                endpoint=self._url(path),
                method=method,
            ) from exc


def _safe_json_or_text(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return (response.text or "")[:2000]
