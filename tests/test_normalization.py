from src.api.ontsluiten import normalize_documents
from src.api.presenteren import PresenterenClient
from src.config import get_api_key
from src.geometry_utils import split_by_geometry_type
from shapely.geometry import Point, LineString, Polygon


def test_missing_fields_are_none_and_documents_deduplicated():
    payload = {"_embedded": {"documenten": [{"uriIdentificatie": "a"}, {"uriIdentificatie": "a"}]}}
    result = normalize_documents(payload, "now")
    assert len(result) == 1
    assert result[0].titel is None


def test_geometry_identifiers_deduplicated():
    client = object.__new__(PresenterenClient)
    assert client.find_geometry_identifiers({"a": [{"geometrieIdentificatie": "x"}, {"geometrieIdentificatie": "x"}]}) == ["x"]


def test_geometry_types_are_separated():
    result = split_by_geometry_type([{"geometry": Point(0, 0)}, {"geometry": LineString([(0, 0), (1, 1)])}, {"geometry": Polygon([(0, 0), (1, 0), (1, 1)])}])
    assert [len(result[k]) for k in ("point", "line", "polygon")] == [1, 1, 1]


def test_missing_api_key_is_handled(monkeypatch):
    monkeypatch.delenv("DSO_API_KEY", raising=False)
    assert get_api_key() is None
