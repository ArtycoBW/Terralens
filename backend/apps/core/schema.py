"""Одна OpenAPI-схема для frontend и contract tests."""

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    PolymorphicProxySerializer,
    extend_schema,
    extend_schema_view,
)

from . import serializers as s
from . import views as v


def install_schema():
    entries = [
        (v.ReadyView, {"get": OpenApiTypes.OBJECT}),
        (v.CapabilitiesView, {"get": OpenApiTypes.OBJECT}),
        (v.SessionView, {"get": s.SessionResponse, "post": s.SessionResponse}),
        (v.PolygonsView, {"get": s.PolygonList, "post": {201: s.PolygonResponse}}),
        (v.PolygonView, {"get": s.PolygonResponse, "patch": s.PolygonResponse}),
        (v.RegionsView, {"get": s.RegionList}),
        (v.RegionView, {"get": s.RegionResponse}),
        (v.AnalysesView, {"post": {200: s.RunAccepted, 202: s.RunAccepted}}),
        (v.AnalysisView, {"get": s.RunResponse}),
        (v.PolygonAnalysesView, {"get": s.RunList}),
        (
            v.SeriesView,
            {
                "get": PolymorphicProxySerializer(
                    component_name="SeriesResponse",
                    serializers=[s.DailySeries, s.AggregatedSeries],
                    resource_type_field_name=None,
                )
            },
        ),
        (v.AnomaliesView, {"get": s.AnomalyList}),
        (v.DiscoveriesView, {"post": {200: s.DiscoveryAccepted, 202: s.DiscoveryAccepted}}),
        (v.DiscoveryView, {"get": s.DiscoveryResponse}),
        (v.ExportsView, {"post": {200: s.ExportAccepted, 202: s.ExportAccepted}}),
        (v.ExportView, {"get": s.ExportResponse}),
        (v.QualityView, {"get": s.QualityResponse}),
        (v.ComparisonsView, {"post": s.ComparisonResponse}),
    ]
    for view, methods in entries:
        decorators = {}
        for method, response in methods.items():
            responses = response if isinstance(response, dict) else {200: response}
            errors = {code: s.ErrorResponse for code in [400, 401, 403, 404, 409, 413, 422, 429, 503]}
            decorators[method] = extend_schema(responses=responses | errors)
        extend_schema_view(**decorators)(view)
    extend_schema_view(get=extend_schema(operation_id="polygons_list"))(v.PolygonsView)
    extend_schema_view(get=extend_schema(operation_id="regions_search"))(v.RegionsView)
    pagination = [
        OpenApiParameter("limit", int, description="1–200, default 50"),
        OpenApiParameter("cursor", str),
    ]
    for view in [
        v.PolygonsView,
        v.RegionsView,
        v.PolygonAnalysesView,
        v.DiscoveryView,
        v.AnomaliesView,
        v.ModelsView,
    ]:
        extra = []
        if view == v.RegionsView:
            extra = [OpenApiParameter("q", str, required=True), OpenApiParameter("country", str)]
        extend_schema_view(get=extend_schema(parameters=pagination + extra))(view)
    extend_schema_view(
        get=extend_schema(
            parameters=pagination
            + [
                OpenApiParameter("from", OpenApiTypes.DATE),
                OpenApiParameter("to", OpenApiTypes.DATE),
                OpenApiParameter("resolution", str, enum=["daily", "weekly", "monthly"]),
            ]
        )
    )(v.SeriesView)
    for view in [v.AnalysesView, v.ExportsView, v.DiscoveriesView]:
        extend_schema_view(
            post=extend_schema(
                parameters=[
                    OpenApiParameter("Idempotency-Key", str, location=OpenApiParameter.HEADER, required=True),
                    OpenApiParameter("X-CSRFToken", str, location=OpenApiParameter.HEADER, required=True),
                ]
            )
        )(view)
