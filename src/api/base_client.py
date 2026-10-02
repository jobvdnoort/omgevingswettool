"""Gemeenschappelijke HTTP-client met retries en logging."""
from __future__ import annotations

import logging
import time
from typing import Any
import requests
from src.config import ApiConfig

LOG = logging.getLogger(__name__)


class DSOApiError(RuntimeError):
    """Nette fout voor een DSO-request."""


class BaseClient:
    def __init__(self, base_url: str, api_key: str, config: ApiConfig | None = None):
        self.base_url = base_url.rstrip("/")
        self.config = config or ApiConfig()
        self.session = requests.Session()
        self.session.headers.update({"x-api-key": api_key, "Content-Type": "application/json"})

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self.base_url}/{path.lstrip('/')}"
        for attempt in range(self.config.retries + 1):
            try:
                response = self.session.request(method, url, timeout=self.config.timeout, **kwargs)
                if response.status_code not in {429, 500, 502, 503, 504}:
                    response.raise_for_status()
                    return response
                if attempt == self.config.retries:
                    response.raise_for_status()
            except requests.RequestException as exc:
                if attempt == self.config.retries:
                    raise DSOApiError(f"DSO-request mislukt ({method} {path}): {exc}") from exc
                LOG.warning("Tijdelijke DSO-fout voor %s (poging %s)", path, attempt + 1)
            time.sleep(2**attempt)
        raise DSOApiError("DSO-request mislukt.")

    def json(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            return self.request(method, path, **kwargs).json()
        except ValueError as exc:
            raise DSOApiError(f"DSO gaf geen geldige JSON terug voor {path}.") from exc
