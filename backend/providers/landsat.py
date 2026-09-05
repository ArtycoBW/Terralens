"""Landsat 8/9 C2 L2 Tier 1: публичный STAC Planetary Computer и временная SAS в памяти."""

import json
from urllib.parse import urlparse

from .base import ProviderError, get_json, snapshot
from .stac import asset_url, collect_scenes, extract_optical_scene, search_scenes

CATALOG = "https://planetarycomputer.microsoft.com/api/stac/v1"
PROVIDER = "planetary_computer_landsat"
COLLECTION = "landsat-c2-l2"
ALLOWED_HOSTS = {"landsateuwest.blob.core.windows.net"}
TOKEN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/token/landsateuwest/landsat-c2"


def fetch_landsat(geometry, start, end, *, max_scenes=80, progress=None):
    scenes, query, raw, warnings = search_scenes(
        geometry,
        start,
        end,
        catalog=CATALOG,
        provider=PROVIDER,
        collection=COLLECTION,
        max_scenes=max_scenes,
        extra_query={
            "query": json.dumps(
                {
                    "platform": {"in": ["landsat-8", "landsat-9"]},
                    "landsat:collection_category": {"eq": "T1"},
                }
            )
        },
    )
    # Ответ каталога сохраняется без SAS; подпись добавляется только при открытии COG.
    token = None
    if scenes:
        response = get_json(TOKEN_URL, provider=PROVIDER)
        token = response.get("token") if isinstance(response, dict) else None
        if not isinstance(token, str) or not token:
            raise ProviderError("provider_schema_changed", "Некорректная SAS-подпись", provider=PROVIDER)

    def resolve_asset(asset):
        url = asset_url(asset, allowed_hosts=ALLOWED_HOSTS, provider=PROVIDER)
        parsed = urlparse(url)
        if not parsed.path.startswith("/landsat-c2/level-2/") or parsed.query:
            raise ProviderError("provider_schema_changed", "Неожиданный путь Landsat COG", provider=PROVIDER)
        return url + "?" + token

    def extract(scene):
        # Проверяем ответ независимо от query: фильтры каталога не заменяют проверку схемы.
        properties = scene["properties"]
        if properties.get("platform") not in {"landsat-8", "landsat-9"}:
            raise ValueError("Unsupported Landsat platform")
        if properties.get("landsat:collection_category") != "T1":
            raise ValueError("Unsupported Landsat collection category")
        return extract_optical_scene(
            scene, geometry, sensor="landsat", provider=PROVIDER, resolve_asset=resolve_asset
        )

    observations = collect_scenes(scenes, extract, provider=PROVIDER, warnings=warnings, progress=progress)
    return observations, snapshot(PROVIDER, query, {"stac": raw, "observations": observations}, warnings)
