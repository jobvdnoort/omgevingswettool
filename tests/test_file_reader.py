import json
from src.file_reader import read_uploaded_file


def test_geojson_is_read():
    payload = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[[4, 52], [4.1, 52], [4.1, 52.1], [4, 52],]]}}]}
    frame = read_uploaded_file("gebied.geojson", json.dumps(payload).encode())
    assert len(frame) == 1
