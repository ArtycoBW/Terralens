import pytest
from apps.core.models import PolygonVersion

from .test_api import polygon


# Синтетические геометрии на российских координатах, без утверждения о реальных полях.
@pytest.mark.django_db
@pytest.mark.parametrize("lon,lat", [(37.6, 55.7), (38.9, 45.0), (82.9, 55.0), (131.9, 43.1), (33.1, 68.9)])
def test_small_fields_at_russian_coordinates_are_accepted(client, lon, lat):
    geometry = {
        "type": "Polygon",
        "coordinates": [
            [
                [lon, lat],
                [lon + 0.01, lat],
                [lon + 0.01, lat + 0.01],
                [lon, lat + 0.01],
                [lon, lat],
            ]
        ],
    }
    saved = polygon(client, geometry)
    assert 30 < saved["area_ha"] < 100
    assert saved["current_version"] == 1


SCREENSHOT_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [
        [
            [29.6766475, 55.6156853],
            [31.3407651, 55.3730105],
            [29.8084589, 56.2524825],
            [29.6766475, 55.6156853],
        ]
    ],
}


@pytest.mark.django_db
def test_large_screenshot_contour_reports_area_and_limit_and_does_not_save(client):
    response = client.post(
        "/api/v1/polygons", {"name": "Russian", "geometry": SCREENSHOT_GEOMETRY}, format="json"
    )
    assert response.status_code == 422
    error = response.data["error"]
    assert error["code"] == "geometry_too_large"
    assert error["details"] == {
        "field": "geometry",
        "reason": "area_limit",
        "unit": "ha",
        "value": pytest.approx(384560.75995),
        "limit": 10000,
    }
    text = error["message"].replace("\u202f", " ")
    assert "384 560,76 га (3 845,61 км²)" in text
    assert "10 000 га (100 км²)" in text
    assert "Приблизьте карту" in text
    assert not PolygonVersion.objects.exists()


@pytest.mark.django_db
def test_area_limit_on_edit_keeps_saved_geometry_and_uses_configured_limit(client, geometry, settings):
    saved = polygon(client, geometry)
    settings.MAX_POLYGON_AREA_HA = 5000
    response = client.patch(
        f"/api/v1/polygons/{saved['id']}",
        {"expected_version": 1, "geometry": SCREENSHOT_GEOMETRY},
        format="json",
    )
    assert response.status_code == 422
    assert response.data["error"]["details"]["limit"] == 5000
    assert "5\u202f000 га (50 км²)" in response.data["error"]["message"]
    current = client.get(f"/api/v1/polygons/{saved['id']}").data
    assert current["geometry"] == saved["geometry"]
    assert current["current_version"] == 1
