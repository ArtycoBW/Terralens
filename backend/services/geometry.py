import json
import math

from apps.core.errors import DomainError
from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from pyproj import Geod
from shapely import normalize, to_wkb
from shapely.geometry import MultiPolygon, shape
from shapely.validation import explain_validity
from terralens_ml.io import canonical_hash


def validate_geometry(value):
    if not isinstance(value, dict) or value.get("type") not in ("Polygon", "MultiPolygon"):
        raise DomainError("invalid_geometry", "Ожидается GeoJSON Polygon или MultiPolygon")

    polygons = value.get("coordinates")
    if value["type"] == "Polygon":
        polygons = [polygons]
    if not isinstance(polygons, list) or not polygons:
        raise DomainError("invalid_geometry", "Ожидаются непустые координаты")
    count = 0
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise DomainError("invalid_geometry", "Полигон должен содержать внешнее кольцо")
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4:
                raise DomainError(
                    "invalid_geometry", "Кольцо должно содержать минимум три вершины и замыкание"
                )
            for position in ring:
                if (
                    not isinstance(position, (list, tuple))
                    or len(position) != 2
                    or any(type(x) not in (int, float) or not math.isfinite(x) for x in position)
                ):
                    raise DomainError("invalid_geometry", "Координаты должны содержать конечные lon,lat")
                if not -180 <= position[0] <= 180 or not -90 <= position[1] <= 90:
                    raise DomainError("invalid_geometry", "Координаты вне диапазона WGS84")
            if ring[0] != ring[-1] or len({tuple(p) for p in ring[:-1]}) < 3:
                raise DomainError("invalid_geometry", "Замкните кольцо из трёх различных вершин")
            count += len(ring)
    if count > settings.MAX_VERTICES:
        raise DomainError(
            "geometry_too_large",
            "Слишком много вершин",
            details={"value": count, "limit": settings.MAX_VERTICES},
        )
    try:
        geometry = shape(value)
    except (TypeError, ValueError) as exc:
        raise DomainError("invalid_geometry", "Не удалось прочитать геометрию") from exc
    if not geometry.is_valid or geometry.is_empty:
        raise DomainError(
            "invalid_geometry", "Контур некорректен", details={"reason": explain_validity(geometry)}
        )
    if geometry.bounds[2] - geometry.bounds[0] > 180:
        raise DomainError(
            "invalid_geometry",
            "Контуры через антимеридиан пока не поддерживаются",
            details={"reason": "antimeridian"},
        )
    geometry = MultiPolygon([geometry]) if geometry.geom_type == "Polygon" else geometry
    # Суммируем площади компонент отдельно: ориентация колец не меняет знак общей площади.
    from shapely.geometry.polygon import orient

    area = (
        sum(abs(Geod(ellps="WGS84").geometry_area_perimeter(orient(p, sign=1))[0]) for p in geometry.geoms)
        / 10000
    )
    if area <= 0 or area > settings.MAX_POLYGON_AREA_HA:
        raise DomainError(
            "geometry_too_large",
            "Площадь вне допустимого диапазона",
            details={"value": area, "limit": settings.MAX_POLYGON_AREA_HA},
        )
    normalized = normalize(geometry)
    return (
        GEOSGeometry(json.dumps(normalized.__geo_interface__), srid=4326),
        area,
        canonical_hash(to_wkb(normalized).hex()),
    )
