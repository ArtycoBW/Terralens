import json

from django.conf import settings
from redis import Redis
from shapely.errors import ShapelyError
from shapely.geometry import Polygon, mapping
from shapely.ops import polygonize, unary_union

from .base import ProviderError, get_json, snapshot


def search_regions(query, country=None):
    redis = Redis.from_url(settings.REDIS_URL)
    key = "terralens:nominatim:" + json.dumps([query, country], ensure_ascii=False)
    cached = redis.get(key)
    if cached:
        return json.loads(cached)
    # Глобальный лимит для всех процессов, а не отдельный таймер на worker.
    if not redis.set("terralens:nominatim:rate", "1", nx=True, px=1100):
        raise ProviderError(
            "provider_rate_limited",
            "Поиск доступен раз в секунду; повторите запрос",
            provider="nominatim",
            retryable=True,
        )
    params = {"q": query, "format": "jsonv2", "addressdetails": 1, "limit": 10}
    if country:
        params["countrycodes"] = country
    result = get_json("https://nominatim.openstreetmap.org/search", params=params, provider="nominatim")
    if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
        raise ProviderError("provider_schema_changed", "Нет списка регионов", provider="nominatim")
    redis.setex(key, 86400, json.dumps(result))
    return result


def discover(bbox):
    west, south, east, north = bbox
    query = f'[out:json][timeout:30];nwr["landuse"="farmland"]({south},{west},{north},{east});out geom 501;'
    raw = get_json(
        "https://overpass-api.de/api/interpreter", params={"data": query}, provider="overpass", timeout=40
    )
    candidates, warnings = [], []
    elements = raw.get("elements") if isinstance(raw, dict) else None
    if not isinstance(elements, list):
        raise ProviderError("provider_schema_changed", "Нет списка контуров OSM", provider="overpass")
    for element in elements[:500]:
        if not isinstance(element, dict):
            warnings.append({"code": "invalid_source_geometry", "source_id": None})
            continue
        try:
            if element["type"] == "way":
                points = [(p["lon"], p["lat"]) for p in element["geometry"]]
                if len(points) < 4 or points[0] != points[-1]:
                    continue
                geometry = Polygon(points)
            elif element["type"] == "relation":
                from shapely.geometry import LineString

                outer, inner = [], []
                for member in element.get("members", []):
                    if member.get("type") == "way" and member.get("geometry"):
                        line = LineString([(p["lon"], p["lat"]) for p in member["geometry"]])
                        (inner if member.get("role") == "inner" else outer).append(line)
                geometry = unary_union(list(polygonize(unary_union(outer))))
                if inner:
                    geometry = geometry.difference(unary_union(list(polygonize(unary_union(inner)))))
            else:
                continue
            if (
                geometry.is_valid
                and not geometry.is_empty
                and geometry.geom_type in ["Polygon", "MultiPolygon"]
            ):
                candidates.append(
                    {
                        # Shapely возвращает tuples, а контракт GeoJSON и валидатор — JSON arrays.
                        "geometry": json.loads(json.dumps(mapping(geometry))),
                        "source_ref": f"https://www.openstreetmap.org/{element['type']}/{element['id']}",
                        "name": element.get("tags", {}).get("name"),
                    }
                )
        except (KeyError, ValueError, TypeError, ShapelyError):
            warnings.append({"code": "invalid_source_geometry", "source_id": element.get("id")})
    if raw.get("remark"):
        warnings.append({"code": "provider_partial", "provider": "overpass"})
    if len(elements) > 500:
        warnings.append({"code": "candidate_limit", "limit": 500})
    return candidates, snapshot("overpass", {"bbox": bbox, "query": query}, raw, warnings)
