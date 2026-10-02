from shapely.geometry import Polygon, MultiPolygon
from src.geometry_utils import prepare_search_geometry, rounded_geojson, geometry_flags
import geopandas as gpd


def test_polygon_and_multipolygon_to_rd():
    frame = gpd.GeoDataFrame(geometry=[Polygon([(4, 52), (4.01, 52), (4.01, 52.01), (4, 52)])], crs=4326)
    merged, valid = prepare_search_geometry(frame)
    assert merged.geom_type in {"Polygon", "MultiPolygon"}
    assert valid.crs.to_epsg() == 28992


def test_rounding_three_decimals():
    result = rounded_geojson(Polygon([(1.123456, 2.987654), (2, 2), (1, 2)]))
    assert result["coordinates"][0][0] == [1.123, 2.988]


def test_invalid_geometry_repaired():
    invalid = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    frame = gpd.GeoDataFrame(geometry=[invalid], crs=28992)
    merged, _ = prepare_search_geometry(frame)
    assert merged.is_valid
