"""Ограниченный STAC-поиск и чтение COG; Sentinel-2 C1 с пиксельной SCL-маской."""

import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import urlparse

import numpy as np
import rasterio
from rasterio.features import geometry_mask, geometry_window
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_geom
from shapely.geometry import mapping

from .base import ProviderError, get_json, snapshot

CATALOG = "https://earth-search.aws.element84.com/v1"
ALLOWED_RASTER_HOSTS = {"e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com"}


def asset_url(asset, *, allowed_hosts=ALLOWED_RASTER_HOSTS, provider="earth_search"):
    url = asset["href"]
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in allowed_hosts
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.fragment
    ):
        raise ProviderError(
            "provider_schema_changed", "Неожиданный адрес спутникового растра", provider=provider
        )
    return url


def reflectance(values, asset, *, provider="earth_search"):
    raster_bands = asset.get("raster:bands")
    metadata = raster_bands[0] if isinstance(raster_bands, list) and raster_bands else {}
    if not isinstance(metadata, dict):
        metadata = {}
    scale, offset = metadata.get("scale"), metadata.get("offset", 0)
    if (
        not isinstance(scale, (float, int))
        or isinstance(scale, bool)
        or not math.isfinite(scale)
        or scale <= 0
        or not isinstance(offset, (float, int))
        or isinstance(offset, bool)
        or not math.isfinite(offset)
    ):
        raise ProviderError(
            "provider_schema_changed",
            "В метаданных отсутствует корректный масштаб отражательной способности",
            provider=provider,
        )
    return values.astype(np.float64) * scale + offset


def extract_scene(scene, geometry, min_valid_fraction=0.3):
    return extract_optical_scene(scene, geometry, min_valid_fraction=min_valid_fraction)


def extract_optical_scene(
    scene,
    geometry,
    *,
    min_valid_fraction=0.3,
    sensor="sentinel2",
    provider="earth_search",
    resolve_asset=asset_url,
):
    assets = scene["assets"]
    landsat = sensor == "landsat"
    nir_key = "nir08" if landsat else "nir"
    quality_bands = ["qa_pixel", "qa_radsat", "qa_aerosol"] if landsat else ["scl"]
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_CONNECTTIMEOUT="15",
        GDAL_HTTP_TIMEOUT="45",
        GDAL_HTTP_MAX_RETRY="2",
        GDAL_HTTP_RETRY_DELAY="1",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF",
    ):
        with rasterio.open(resolve_asset(assets["red"])) as red_source:
            projected = transform_geom("EPSG:4326", red_source.crs, mapping(geometry))
            # Полное окно AOI: иначе сцена на краю тайла завышает долю пригодных пикселей.
            window = geometry_window(red_source, [projected], boundless=True)
            if window.width * window.height > 2_000_000:
                raise ProviderError("geometry_too_large", "Слишком большое окно растра", provider=provider)
            transform = red_source.window_transform(window)
            shape = (int(window.height), int(window.width))
            inside = geometry_mask([projected], out_shape=shape, transform=transform, invert=True)
            red_raw = red_source.read(1, window=window, masked=True, boundless=True)
            arrays = {"red": red_raw}
            for band in [nir_key, "blue", "swir16", *quality_bands]:
                with rasterio.open(resolve_asset(assets[band])) as source:
                    with WarpedVRT(
                        source,
                        crs=red_source.crs,
                        transform=transform,
                        width=shape[1],
                        height=shape[0],
                        resampling=rasterio.enums.Resampling.nearest,
                    ) as aligned:
                        arrays[band] = aligned.read(1, masked=True)
            # QA_PIXEL: fill, dilation, cirrus, cloud, shadow, snow; QA_RADSAT: насыщение/рельеф.
            if landsat:
                qa = arrays["qa_pixel"].filled(1).astype(np.uint16)
                aerosol = arrays["qa_aerosol"].filled(1).astype(np.uint16)
                valid = inside & ((qa & 0b111111) == 0) & (arrays["qa_radsat"].filled(1) == 0)
                valid &= ((aerosol & 1) == 0) & (((aerosol >> 6) & 3) != 3)
            else:
                # 4 vegetation, 5 bare soil, 6 water; облака, тени, снег и unclassified исключены.
                valid = inside & np.isin(arrays["scl"], [4, 5, 6])
            for values in arrays.values():
                valid &= ~np.ma.getmaskarray(values)
            bands = {
                band: reflectance(arrays[band].filled(0), assets[band], provider=provider)
                for band in ["red", nir_key, "blue", "swir16"]
            }
            red, nir, blue, swir = (bands[x] for x in ["red", nir_key, "blue", "swir16"])
            # Отрицательные RED/NIR дают нефизичные NDVI; исключаем их до подсчёта coverage.
            valid &= np.isfinite(red) & np.isfinite(nir) & (red >= 0) & (nir >= 0) & (nir + red > 1e-10)
            total, count = int(inside.sum()), int(valid.sum())
            fraction = count / total if total else 0
            if count:
                ndvi = (nir[valid] - red[valid]) / (nir[valid] + red[valid])
                ndvi = ndvi[np.isfinite(ndvi) & (np.abs(ndvi) <= 1)]
                ndvi_value = float(np.median(ndvi)) if len(ndvi) else None
                spread = float(np.std(ndvi)) if len(ndvi) else None
            else:
                ndvi_value, spread = None, None
            indices = {}
            for name, numerator, denominator in [
                ("evi", 2.5 * (nir - red), nir + 6 * red - 7.5 * blue + 1),
                ("ndwi", nir - swir, nir + swir),
            ]:
                usable = valid & (np.abs(denominator) > 1e-10)
                values = numerator[usable] / denominator[usable]
                values = values[np.isfinite(values)]
                indices[name] = float(np.median(values)) if len(values) else None
    timestamp = datetime.fromisoformat(scene["properties"]["datetime"].replace("Z", "+00:00"))
    if timestamp.utcoffset() is None or timestamp.utcoffset().total_seconds() != 0:
        raise ValueError("STAC acquisition time must be UTC")
    quality_flags = [] if fraction >= min_valid_fraction else ["low_pixel_coverage"]
    if ndvi_value is None:
        quality_flags.append("no_valid_pixels")
    return {
        "scene_id": scene["id"],
        "date": scene["properties"]["datetime"][:10],
        "acquisition_time": scene["properties"]["datetime"],
        "sensor": sensor,
        "ndvi": ndvi_value,
        **indices,
        "valid_pixel_fraction": fraction,
        "pixel_count": count,
        "pixel_std": spread,
        "usable": ndvi_value is not None and fraction >= min_valid_fraction,
        "quality_flags": quality_flags,
        "aggregation_version": (
            "landsat89-t1-median-qa63-radsat-aerosol-scale-v1"
            if landsat
            else "s2-median-scl456-scale-full-aoi-v2"
        ),
        "spatial_resolution_m": 30 if landsat else 10,
        "ndwi_formula": "(NIR-SWIR)/(NIR+SWIR) moisture index",
    }


def search_scenes(
    geometry,
    start,
    end,
    *,
    catalog=CATALOG,
    provider="earth_search",
    collection="sentinel-2-c1-l2a",
    max_scenes=80,
    extra_query=None,
):
    if isinstance(max_scenes, bool) or not isinstance(max_scenes, int) or max_scenes < 1:
        raise ValueError("max_scenes must be a positive integer")
    query = {
        "collections": collection,
        "bbox": ",".join(map(str, geometry.bounds)),
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
        "limit": min(max_scenes + 1, 100),
    }
    query.update(extra_query or {})
    raw = get_json(catalog + "/search", params=query, provider=provider)

    def features(page):
        if not isinstance(page, dict) or not isinstance(page.get("features"), list):
            raise ProviderError("provider_schema_changed", "Нет списка сцен STAC", provider=provider)
        try:
            if not isinstance(page.get("links", []), list) or any(
                not isinstance(link, dict) for link in page.get("links", [])
            ):
                raise ValueError("Invalid STAC links")
            for item in page["features"]:
                if not isinstance(item["id"], str) or not isinstance(item["properties"]["datetime"], str):
                    raise ValueError("Invalid STAC item")
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError(
                "provider_schema_changed", "Некорректная сцена STAC", provider=provider
            ) from exc
        return page["features"]

    scenes = list({scene["id"]: scene for scene in features(raw)}.values())
    pages, seen = [], set()
    current = raw
    while len(scenes) <= max_scenes:
        matched = current.get("numberMatched", raw.get("numberMatched"))
        if isinstance(matched, int) and matched <= len(scenes):
            break
        link = next((x for x in current.get("links", []) if x.get("rel") == "next"), None)
        if not link or not current["features"]:
            break
        url = link.get("href", "")
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != urlparse(catalog).netloc
            or parsed.path != urlparse(catalog).path + "/search"
            or link.get("method", "GET") != "GET"
            or url in seen
        ):
            raise ProviderError("provider_schema_changed", "Некорректная пагинация STAC", provider=provider)
        seen.add(url)
        current = get_json(url, provider=provider)
        pages.append(current)
        identifiers = {scene["id"] for scene in scenes}
        additional = []
        for scene in features(current):
            if scene["id"] not in identifiers:
                additional.append(scene)
                identifiers.add(scene["id"])
        if not additional:
            if current["features"]:
                raise ProviderError("provider_schema_changed", "Повторная страница STAC", provider=provider)
            break
        scenes.extend(additional)
    raw["additional_pages"] = pages
    # Каталог может отдавать next даже на последней странице; сам link не означает потерю данных.
    truncated = len(scenes) > max_scenes
    scenes = sorted(scenes, key=lambda x: x["properties"]["datetime"])[:max_scenes]
    warnings = [{"code": "scene_limit", "provider": provider, "limit": max_scenes}] if truncated else []
    return scenes, query, raw, warnings


def fetch_satellite(geometry, start, end, *, max_scenes=80, progress=None):
    scenes, query, raw, warnings = search_scenes(geometry, start, end, max_scenes=max_scenes)
    observations = collect_scenes(
        scenes,
        lambda scene: extract_scene(scene, geometry),
        provider="earth_search",
        warnings=warnings,
        progress=progress,
    )
    return observations, snapshot(
        "earth_search", query, {"stac": raw, "observations": observations}, warnings
    )


def collect_scenes(scenes, extract, *, provider, warnings, progress=None):
    """Не более трёх одновременных COG-окон; отмена проверяется между короткими пакетами."""
    observations = []

    def read(scene):
        try:
            return extract(scene), None
        except (rasterio.errors.RasterioError, KeyError, TypeError, ValueError) as exc:
            # Текст GDAL exception может содержать подписанный URL; сохраняем только тип.
            return None, {
                "code": "scene_unavailable",
                "scene_id": scene.get("id"),
                "provider": provider,
                "reason": type(exc).__name__,
            }

    with ThreadPoolExecutor(max_workers=3) as executor:
        for offset in range(0, len(scenes), 3):
            if progress:
                progress(offset, len(scenes))
            for observation, warning in executor.map(read, scenes[offset : offset + 3]):
                if observation is not None:
                    observations.append(observation)
                if warning:
                    warnings.append(warning)
    if progress:
        progress(len(scenes), len(scenes))
    return observations
