import numpy as np
import pytest
from providers.base import ProviderError
from providers.stac import asset_url, fetch_satellite, reflectance


def test_scale_and_offset_and_untrusted_asset():
    result = reflectance(np.array([1000, 2000]), {"raster:bands": [{"scale": 0.0001, "offset": -0.1}]})
    assert result.tolist() == pytest.approx([0, 0.1])
    with pytest.raises(ProviderError):
        asset_url({"href": "http://127.0.0.1/secret.tif"})
    with pytest.raises(ProviderError):
        reflectance(np.array([1000]), {})


def test_next_link_on_last_stac_page_does_not_mean_truncation(monkeypatch):
    from shapely.geometry import box

    scene = {"id": "A", "properties": {"datetime": "2024-06-01T00:00:00Z"}}
    calls = []

    def get(*args, **kwargs):
        calls.append(args)
        return {
            "features": [scene],
            "numberMatched": 1,
            "links": [{"rel": "next", "href": "https://earth-search.aws.element84.com/v1/search?next=A"}],
        }

    monkeypatch.setattr("providers.stac.get_json", get)
    monkeypatch.setattr("providers.stac.extract_scene", lambda *args: {"scene_id": "A"})
    observations, snapshot = fetch_satellite(box(0, 0, 1, 1), "2024-06-01", "2024-06-10")
    assert len(calls) == 1 and len(observations) == 1
    assert snapshot["warnings"] == []


def test_weather_invalid_response_becomes_provider_error(monkeypatch):
    from providers.weather import fetch_weather
    from shapely.geometry import box

    monkeypatch.setattr(
        "providers.weather.get_json",
        lambda *args, **kwargs: {
            "daily": {"time": ["2024-06-01"], "temperature_2m_mean": [float("inf")], "precipitation_sum": [1]}
        },
    )
    with pytest.raises(ProviderError, match="схема"):
        fetch_weather(box(0, 0, 1, 1), "2024-06-01", "2024-06-02")


def raster_scene(tmp_path, *, landsat=False, arrays=None):
    """Синтетические COG-подобные GeoTIFF для проверки реального пиксельного вычисления."""
    import rasterio
    from rasterio.transform import from_origin

    bands = {
        "red": 10000 if landsat else 2000,
        "nir08" if landsat else "nir": 20000 if landsat else 6000,
        "blue": 9000 if landsat else 1000,
        "swir16": 15000 if landsat else 3000,
    }
    bands.update({"qa_pixel": 64, "qa_radsat": 0, "qa_aerosol": 2} if landsat else {"scl": 4})
    assets = {}
    for name, value in bands.items():
        values = (arrays or {}).get(name, np.full((4, 4), value, dtype=np.uint16))
        path = tmp_path / f"{name}.tif"
        quality = name.startswith("qa_") or name == "scl"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=4,
            height=4,
            count=1,
            dtype="uint16",
            crs="EPSG:4326",
            transform=from_origin(0, 0.004, 0.001, 0.001),
            nodata=None if quality else 0,
        ) as source:
            source.write(values.astype(np.uint16), 1)
        assets[name] = {
            "href": str(path),
            "raster:bands": [
                {
                    "scale": 0.0000275 if landsat else 0.0001,
                    "offset": -0.2 if landsat else 0,
                }
            ],
        }
    return {"id": "synthetic", "properties": {"datetime": "2024-06-01T10:00:00Z"}, "assets": assets}


def test_scene_coverage_uses_entire_aoi_even_outside_raster(tmp_path):
    from providers.stac import extract_optical_scene
    from shapely.geometry import box

    scene = raster_scene(tmp_path)
    result = extract_optical_scene(scene, box(0, 0, 0.008, 0.004), resolve_asset=lambda asset: asset["href"])
    assert result["valid_pixel_fraction"] == pytest.approx(0.5)
    assert result["pixel_count"] == 16
    assert result["ndvi"] == pytest.approx(0.5)


def test_landsat_masks_cloud_shadow_snow_saturation_aerosol_and_negative_reflectance(tmp_path):
    from providers.stac import extract_optical_scene
    from shapely.geometry import box

    qa = np.full((4, 4), 64, dtype=np.uint16)
    qa.flat[1:7] = [1 << i for i in range(6)]
    radsat = np.zeros((4, 4), dtype=np.uint16)
    radsat[2, 0] = 8
    aerosol = np.full((4, 4), 2, dtype=np.uint16)
    aerosol[2, 1] = 192
    nir = np.full((4, 4), 20000, dtype=np.uint16)
    nir[2, 2] = 1000
    scene = raster_scene(
        tmp_path,
        landsat=True,
        arrays={"qa_pixel": qa, "qa_radsat": radsat, "qa_aerosol": aerosol, "nir08": nir},
    )
    result = extract_optical_scene(
        scene, box(0, 0, 0.004, 0.004), sensor="landsat", resolve_asset=lambda asset: asset["href"]
    )
    assert result["pixel_count"] == 7
    assert result["valid_pixel_fraction"] == pytest.approx(7 / 16)
    assert result["ndvi"] == pytest.approx((0.35 - 0.075) / (0.35 + 0.075))
    assert result["usable"]


def test_invalid_ndvi_pixels_do_not_count_as_coverage(tmp_path):
    from providers.stac import extract_optical_scene
    from shapely.geometry import box

    scene = raster_scene(tmp_path, landsat=True, arrays={"nir08": np.full((4, 4), 1000)})
    result = extract_optical_scene(
        scene, box(0, 0, 0.004, 0.004), sensor="landsat", resolve_asset=lambda asset: asset["href"]
    )
    assert result["ndvi"] is None
    assert result["pixel_count"] == 0 and result["valid_pixel_fraction"] == 0
    assert not result["usable"] and "no_valid_pixels" in result["quality_flags"]


@pytest.mark.parametrize("page", [[], {"features": [{}]}, {"features": None}])
def test_malformed_stac_response_is_provider_error(monkeypatch, page):
    from shapely.geometry import box

    monkeypatch.setattr("providers.stac.get_json", lambda *args, **kwargs: page)
    with pytest.raises(ProviderError):
        fetch_satellite(box(0, 0, 1, 1), "2024-06-01", "2024-06-02")


def test_foreign_pagination_is_rejected_before_fetch(monkeypatch):
    from shapely.geometry import box

    calls = []

    def get(*args, **kwargs):
        calls.append(args)
        return {
            "features": [{"id": "A", "properties": {"datetime": "2024-06-01T00:00:00Z"}}],
            "links": [{"rel": "next", "href": "https://127.0.0.1/v1/search"}],
        }

    monkeypatch.setattr("providers.stac.get_json", get)
    with pytest.raises(ProviderError, match="пагинация"):
        fetch_satellite(box(0, 0, 1, 1), "2024-06-01", "2024-06-02")
    assert len(calls) == 1


def test_incomplete_weather_is_explicitly_partial(monkeypatch):
    from providers.weather import fetch_weather
    from shapely.geometry import box

    monkeypatch.setattr(
        "providers.weather.get_json",
        lambda *args, **kwargs: {
            "daily": {"time": ["2024-06-01"], "temperature_2m_mean": [None], "precipitation_sum": [-0.1]}
        },
    )
    records, snapshot = fetch_weather(box(0, 0, 1, 1), "2024-06-01", "2024-06-02")
    assert records[0]["precipitation_mm"] is None
    assert snapshot["warnings"][0]["missing_days"] == 1
    assert snapshot["warnings"][0]["incomplete_days"] == 1


def test_weather_explicit_seamless_supports_precipitation(monkeypatch):
    from providers.weather import fetch_weather
    from shapely.geometry import box

    def get(*args, **kwargs):
        assert kwargs["params"]["models"] == "era5_seamless"
        return {
            "daily_units": {"temperature_2m_mean": "°C", "precipitation_sum": "mm"},
            "daily": {"time": ["2024-06-10"], "temperature_2m_mean": [14.7], "precipitation_sum": [1.5]},
        }

    monkeypatch.setattr("providers.weather.get_json", get)
    records, snapshot = fetch_weather(box(13, 52, 13.1, 52.1), "2024-06-10", "2024-06-10")
    assert records[0]["provider"] == "open_meteo_era5_seamless"
    assert records[0]["precipitation_mm"] == 1.5
    assert snapshot["query"]["field_sources"] == {"temperature_c": "era5_land", "precipitation_mm": "era5"}
    assert snapshot["warnings"] == []


def test_retry_after_nonfinite_does_not_sleep_or_leak_error(monkeypatch):
    import httpx
    from providers.base import get_json

    monkeypatch.setattr(
        "providers.base.httpx.get",
        lambda *args, **kwargs: httpx.Response(
            429,
            headers={"Retry-After": "nan"},
            request=httpx.Request("GET", "https://example.com"),
        ),
    )
    monkeypatch.setattr("providers.base.time.sleep", lambda *args: pytest.fail("must not sleep"))
    with pytest.raises(ProviderError) as error:
        get_json("https://example.com", provider="test")
    assert error.value.code == "provider_rate_limited"


def test_landsat_recorded_stac_signs_only_in_memory(monkeypatch):
    import copy
    import json
    from pathlib import Path

    from providers.landsat import fetch_landsat
    from shapely.geometry import box

    fixture = json.loads((Path(__file__).parent / "fixtures" / "landsat_recorded.json").read_text())
    scene = fixture["scene"]
    second = copy.deepcopy(scene)
    second["id"] += "-second"
    signed_urls, token_calls = [], []
    monkeypatch.setattr(
        "providers.stac.get_json",
        lambda *args, **kwargs: {
            "features": [scene, second],
            "links": [],
            "numberMatched": 2,
        },
    )

    def token(*args, **kwargs):
        token_calls.append(args)
        return {"token": "synthetic-test-signature"}

    def extract(scene, geometry, **kwargs):
        signed_urls.append(kwargs["resolve_asset"](scene["assets"]["red"]))
        return {"scene_id": scene["id"], "sensor": "landsat"}

    monkeypatch.setattr("providers.landsat.get_json", token)
    monkeypatch.setattr("providers.landsat.extract_optical_scene", extract)
    records, snapshot = fetch_landsat(box(13, 52.49, 13.01, 52.5), "2024-06-10", "2024-06-20")
    assert len(records) == 2 and len(token_calls) == 1
    assert all(url.endswith("?synthetic-test-signature") for url in signed_urls)
    assert "synthetic-test-signature" not in json.dumps(snapshot)
    assert snapshot["provider"] == "planetary_computer_landsat"
    assert snapshot["warnings"] == []


def test_scene_failure_preserves_successful_scenes(monkeypatch):
    from shapely.geometry import box

    scenes = [{"id": key, "properties": {"datetime": "2024-06-01T00:00:00Z"}} for key in ["A", "B"]]
    monkeypatch.setattr(
        "providers.stac.get_json",
        lambda *args, **kwargs: {
            "features": scenes,
            "numberMatched": 2,
        },
    )

    def extract(scene, *args):
        if scene["id"] == "B":
            raise ValueError("Private provider detail")
        return {"scene_id": "A"}

    monkeypatch.setattr("providers.stac.extract_scene", extract)
    records, snapshot = fetch_satellite(box(0, 0, 1, 1), "2024-06-01", "2024-06-02")
    assert records == [{"scene_id": "A"}]
    assert snapshot["warnings"] == [
        {
            "code": "scene_unavailable",
            "scene_id": "B",
            "provider": "earth_search",
            "reason": "ValueError",
        }
    ]


def test_incomplete_overpass_geometry_does_not_abort_other_candidates(monkeypatch):
    from providers.osm import discover

    raw = {
        "elements": [
            {"type": "way", "id": 1, "geometry": []},
            {
                "type": "relation",
                "id": 2,
                "members": [
                    {"type": "way", "role": "outer", "geometry": [{"lon": 0, "lat": 0}]},
                ],
            },
            {
                "type": "way",
                "id": 3,
                "geometry": [{"lon": x, "lat": y} for x, y in [(0, 0), (1, 0), (1, 1), (0, 0)]],
            },
        ],
        "remark": "runtime error: Query timed out",
    }
    monkeypatch.setattr("providers.osm.get_json", lambda *args, **kwargs: raw)
    candidates, snapshot = discover([0, 0, 1, 1])
    assert len(candidates) == 1
    assert candidates[0]["source_ref"].endswith("/3")
    assert {x["code"] for x in snapshot["warnings"]} == {"invalid_source_geometry", "provider_partial"}
