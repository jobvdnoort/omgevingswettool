"""GIS-bewerkingen voor onderzoeksgebieden en API-filtering."""
from __future__ import annotations

from typing import Any
import geopandas as gpd
from shapely.geometry import shape, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

RD_CRS = "EPSG:28992"
WGS84_CRS = "EPSG:4326"


def repair_geometry(geom: BaseGeometry) -> BaseGeometry | None:
    if geom is None or geom.is_empty:
        return None
    if geom.is_valid:
        return geom
    try:
        from shapely import make_valid
        fixed = make_valid(geom)
    except ImportError:
        fixed = geom.buffer(0)
    return None if fixed.is_empty else fixed


def prepare_search_geometry(frame: gpd.GeoDataFrame) -> tuple[BaseGeometry, gpd.GeoDataFrame]:
    """Valideer, herstel en combineer polygonen in RD."""
    if frame.crs is None:
        raise ValueError("Het invoerbestand heeft geen CRS. Voeg een CRS toe en probeer opnieuw.")
    frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty].copy()
    if frame.empty:
        raise ValueError("Het invoerbestand bevat geen niet-lege geometrieën.")
    frame["geometry"] = frame.geometry.map(repair_geometry)
    frame = frame[frame.geometry.notna()].copy()
    frame = frame[frame.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    if frame.empty:
        raise ValueError("Het invoerbestand bevat geen Polygon of MultiPolygon.")
    frame = frame.to_crs(RD_CRS)
    merged = repair_geometry(unary_union(frame.geometry.tolist()))
    if merged is None:
        raise ValueError("De geometrieën konden niet worden samengevoegd.")
    return merged, frame


def _to_python_number(value: Any, decimals: int) -> float:
    """Zet coördinaten om naar plain float; weiger NaN/Infinity/numpy-restanten."""
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Ongeldige coördinaatwaarde: {value!r}") from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError("Geometrie bevat NaN of Infinity en kan niet naar JSON.")
    return round(number, decimals)


def _round_coords(value: Any, decimals: int = 3) -> Any:
    if isinstance(value, (list, tuple)):
        return [_round_coords(v, decimals) for v in value]
    return _to_python_number(value, decimals)


def _close_ring(ring: list[Any]) -> list[Any]:
    if not ring:
        return ring
    if ring[0] != ring[-1]:
        return list(ring) + [ring[0]]
    return list(ring)


def _ensure_closed_coordinates(geom_type: str, coordinates: Any) -> Any:
    """Houd Polygon-/MultiPolygon-nesting intact en sluit ringen."""
    if geom_type == "Polygon":
        return [_close_ring(list(ring)) for ring in coordinates]
    if geom_type == "MultiPolygon":
        return [[_close_ring(list(ring)) for ring in polygon] for polygon in coordinates]
    return coordinates


def rounded_geojson(geom: BaseGeometry, decimals: int = 3) -> dict[str, Any]:
    """GeoJSON met RD-coördinaten afgerond op maximaal drie decimalen."""
    if geom.geom_type == "GeometryCollection":
        polygons = [g for g in geom.geoms if g.geom_type in {"Polygon", "MultiPolygon"}]
        if not polygons:
            raise ValueError("GeometryCollection bevat geen Polygon/MultiPolygon.")
        geom = unary_union(polygons)
    result = mapping(geom)
    geom_type = result.get("type")
    if geom_type not in {"Point", "Polygon", "MultiPolygon", "LineString", "MultiLineString", "MultiPoint"}:
        raise ValueError(f"Niet-ondersteund geometrietype voor DSO: {geom_type}")
    coordinates = _round_coords(result["coordinates"], decimals)
    result["coordinates"] = _ensure_closed_coordinates(str(geom_type), coordinates)
    # Alleen type + coordinates; voorkom extra nesting of crs-velden.
    return {"type": result["type"], "coordinates": result["coordinates"]}


def representative_point_geojson(geom: BaseGeometry, decimals: int = 3) -> dict[str, Any]:
    """Representatief punt in RD als GeoJSON Point."""
    point = geom.representative_point()
    return rounded_geojson(point, decimals)


def bounding_box_rd(geom: BaseGeometry, decimals: int = 3) -> list[float]:
    return [round(float(v), decimals) for v in geom.bounds]


def geometry_flags(geom: BaseGeometry, search: BaseGeometry) -> dict[str, Any]:
    clipped = geom.intersection(search)
    area = geom.area
    inside_area = clipped.area if not clipped.is_empty else 0.0
    return {
        "raakt_zoekgebied": geom.intersects(search),
        "volledig_binnen": geom.within(search),
        "oppervlakte_m2": area,
        "oppervlakte_binnen_m2": inside_area,
        "percentage_binnen": (inside_area / area * 100) if area else None,
    }


def split_by_geometry_type(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups = {"point": [], "line": [], "polygon": []}
    for record in records:
        geom = record.get("geometry")
        if geom is None:
            continue
        kind = geom.geom_type.lower()
        if "point" in kind:
            groups["point"].append(record)
        elif "line" in kind:
            groups["line"].append(record)
        elif "polygon" in kind:
            groups["polygon"].append(record)
    return groups
