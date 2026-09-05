"""Исполняемый контракт запросов. Неизвестные поля отклоняются."""

from rest_framework import serializers

from .errors import DomainError


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Ожидается JSON object")
        if unknown := set(data) - set(self.fields):
            raise serializers.ValidationError({key: "Неизвестное поле" for key in unknown})
        return super().to_internal_value(data)


class CropSeasonInput(StrictSerializer):
    season_start = serializers.DateField()
    season_end = serializers.DateField()
    crop_type = serializers.CharField(max_length=100, allow_null=True)

    def validate(self, attrs):
        if attrs["season_start"] > attrs["season_end"]:
            raise serializers.ValidationError("Начало сезона должно быть не позднее окончания")
        return attrs


class CropHistoryMixin:
    def validate_crop_seasons(self, seasons):
        ordered = sorted(seasons, key=lambda season: season["season_start"])
        if any(left["season_end"] >= right["season_start"] for left, right in zip(ordered, ordered[1:])):
            raise serializers.ValidationError("Сезоны культур не должны пересекаться")
        return ordered


class PolygonInput(CropHistoryMixin, StrictSerializer):
    name = serializers.CharField(max_length=200)
    geometry = serializers.JSONField(required=False)
    candidate_id = serializers.UUIDField(required=False)
    crop_type = serializers.CharField(max_length=100, allow_null=True, required=False)
    crop_seasons = CropSeasonInput(many=True, required=False, max_length=50)

    def validate(self, attrs):
        if ("geometry" in attrs) == ("candidate_id" in attrs):
            raise serializers.ValidationError("Укажите ровно одно поле: geometry или candidate_id")
        return attrs


class PolygonPatch(CropHistoryMixin, StrictSerializer):
    expected_version = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=200, required=False)
    geometry = serializers.JSONField(required=False)
    crop_type = serializers.CharField(max_length=100, allow_null=True, required=False)
    crop_seasons = CropSeasonInput(many=True, required=False, max_length=50)


class VersionInput(StrictSerializer):
    expected_version = serializers.IntegerField(min_value=1)


class Period(StrictSerializer):
    def get_fields(self):
        return {"from": serializers.DateField(), "to": serializers.DateField()}


class AnalysisOptions(StrictSerializer):
    climatology_years = serializers.IntegerField(min_value=0, max_value=5, default=3)
    refresh_sources = serializers.BooleanField(default=False)


class AnalysisInput(StrictSerializer):
    polygon_id = serializers.UUIDField()
    polygon_version = serializers.IntegerField(min_value=1)
    period = Period()
    mode = serializers.ChoiceField(choices=["retrospective"], default="retrospective")
    sources = serializers.ListField(
        child=serializers.ChoiceField(choices=["sentinel2", "landsat", "era5_land"]), allow_empty=True
    )
    options = AnalysisOptions(required=False)

    def validate_sources(self, values):
        if not set(values) & {"sentinel2", "landsat"}:
            raise DomainError("empty_sources", "Выберите хотя бы один спутниковый источник")
        return values


class DiscoveryInput(StrictSerializer):
    region_id = serializers.UUIDField(required=False)
    bbox = serializers.ListField(child=serializers.FloatField(), min_length=4, max_length=4)
    sources = serializers.ListField(
        child=serializers.ChoiceField(choices=["osm"]), default=["osm"], allow_empty=False
    )


class ExportInput(StrictSerializer):
    run_id = serializers.UUIDField()
    format = serializers.ChoiceField(choices=["csv", "json", "geojson"])


class ComparisonInput(StrictSerializer):
    run_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=4)
    alignment = serializers.ChoiceField(choices=["calendar", "day_of_year"], default="calendar")

    def validate_run_ids(self, values):
        if len(set(values)) != len(values):
            raise serializers.ValidationError("Каждый анализ можно включить в сравнение только один раз")
        return values


class JobResponse(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=["analysis", "discovery", "export"])
    state = serializers.ChoiceField(choices=["queued", "running", "succeeded", "failed", "cancelled"])
    stage = serializers.ChoiceField(
        choices=[
            "validating",
            "discovering",
            "fetching_satellite",
            "fetching_weather",
            "preprocessing",
            "reconstructing",
            "detecting",
            "exporting",
        ]
    )
    progress = serializers.FloatField(allow_null=True, min_value=0, max_value=1)
    attempt = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)
    cancel_requested = serializers.BooleanField()
    retryable = serializers.BooleanField()
    error = serializers.JSONField(allow_null=True)
    result = serializers.JSONField(allow_null=True)
    parent_job_id = serializers.UUIDField(allow_null=True)


class SessionResponse(serializers.Serializer):
    workspace_id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=["guest"])
    expires_at = serializers.DateTimeField()
    csrf_token = serializers.CharField()


class CropSeasonResponse(CropSeasonInput):
    id = serializers.UUIDField()
    origin = serializers.ChoiceField(choices=["user", "provider", "unknown"])


class PolygonResponse(serializers.Serializer):
    id = serializers.UUIDField()
    workspace_id = serializers.UUIDField()
    region_id = serializers.UUIDField(allow_null=True)
    name = serializers.CharField()
    current_version = serializers.IntegerField(min_value=1)
    geometry = serializers.JSONField(
        required=False,
        help_text="GeoJSON MultiPolygon EPSG:4326 [lon,lat]; omitted only with lightweight=true",
    )
    geometry_hash = serializers.CharField()
    area_ha = serializers.FloatField()
    source = serializers.CharField()
    source_ref = serializers.CharField(allow_blank=True)
    crop_type = serializers.CharField(allow_null=True)
    crop_seasons = CropSeasonResponse(many=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    latest_run_id = serializers.UUIDField(allow_null=True)


class LatestEstimate(serializers.Serializer):
    date = serializers.DateField()
    value = serializers.FloatField()
    origin = serializers.ChoiceField(
        choices=["observed", "interpolated", "extrapolated", "climatology_fallback", "unavailable"]
    )


class SummaryResponse(serializers.Serializer):
    observed_days = serializers.IntegerField(
        help_text="Число дат с пригодным первичным спутниковым наблюдением после QA; восстановленные значения не учитываются"
    )
    total_days = serializers.IntegerField()
    observed_coverage_ratio = serializers.FloatField(min_value=0, max_value=1)
    reconstructed_days = serializers.IntegerField()
    unavailable_days = serializers.IntegerField()
    longest_gap_days = serializers.IntegerField()
    anomaly_period_count = serializers.IntegerField()
    overall_status = serializers.ChoiceField(choices=["normal", "stress", "critical", "insufficient_data"])
    summary_rule = serializers.CharField()
    latest_estimate = LatestEstimate(allow_null=True)


class SnapshotResponse(serializers.Serializer):
    id = serializers.UUIDField()
    provider = serializers.CharField()
    checksum = serializers.CharField()
    retrieved_at = serializers.DateTimeField()
    status = serializers.ChoiceField(choices=["completed", "partial"])


class RunResponse(serializers.Serializer):
    id = serializers.UUIDField()
    polygon_id = serializers.UUIDField()
    polygon_version = serializers.IntegerField()
    mode = serializers.ChoiceField(choices=["retrospective"])
    period = Period()
    state = serializers.ChoiceField(
        choices=["queued", "running", "completed", "partial", "no_data", "failed", "cancelled"]
    )
    job_id = serializers.UUIDField(allow_null=True)
    model_version = serializers.CharField()
    config_version = serializers.CharField()
    created_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)
    snapshots = SnapshotResponse(many=True)
    warnings = serializers.ListField(child=serializers.JSONField())
    summary = SummaryResponse(allow_null=True)
    result_version = serializers.CharField(allow_null=True)


class IntervalResponse(serializers.Serializer):
    lower = serializers.FloatField(allow_null=True)
    upper = serializers.FloatField(allow_null=True)
    level = serializers.FloatField(allow_null=True)
    method = serializers.CharField()


class WeatherResponse(serializers.Serializer):
    temperature_c = serializers.FloatField(allow_null=True)
    precipitation_mm = serializers.FloatField(allow_null=True)
    provider = serializers.CharField(allow_null=True)


class SensorsResponse(serializers.Serializer):
    sentinel2 = serializers.FloatField(allow_null=True)
    landsat = serializers.FloatField(allow_null=True)
    modis = serializers.FloatField(allow_null=True)


class DailyPointResponse(serializers.Serializer):
    date = serializers.DateField()
    observed_primary = serializers.FloatField(allow_null=True)
    clean_primary = serializers.FloatField(allow_null=True)
    reconstructed = serializers.FloatField(allow_null=True)
    origin = serializers.ChoiceField(
        choices=["observed", "interpolated", "extrapolated", "climatology_fallback", "unavailable"]
    )
    source_sensor = serializers.CharField(allow_null=True)
    sensors = SensorsResponse()
    climatology_mean = serializers.FloatField(allow_null=True)
    climatology_std = serializers.FloatField(allow_null=True)
    zscore = serializers.FloatField(allow_null=True)
    prediction_interval = IntervalResponse()
    weather = WeatherResponse()
    support_count = serializers.IntegerField()
    gap_days = serializers.IntegerField()
    quality_flags = serializers.ListField(child=serializers.CharField())
    reference_years = serializers.IntegerField()


class AggregatedPointResponse(serializers.Serializer):
    bucket_start = serializers.DateField()
    bucket_end = serializers.DateField()
    estimate_mean = serializers.FloatField(allow_null=True)
    estimate_min = serializers.FloatField(allow_null=True)
    estimate_max = serializers.FloatField(allow_null=True)
    observed_count = serializers.IntegerField()
    available_day_count = serializers.IntegerField()
    total_day_count = serializers.IntegerField()
    minimum_z = serializers.FloatField(allow_null=True)
    quality_flags = serializers.ListField(child=serializers.CharField())


class AnomalyResponse(serializers.Serializer):
    id = serializers.UUIDField()
    run_id = serializers.UUIDField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    peak_date = serializers.DateField()
    severity = serializers.ChoiceField(choices=["stress", "critical"])
    confidence = serializers.ChoiceField(choices=["low", "medium", "high"])
    event_kind = serializers.ChoiceField(choices=["persistent_period", "single_observation_alert"])
    min_z = serializers.FloatField(allow_null=True)
    integrated_deficit = serializers.FloatField(allow_null=True)
    observed_evidence_count = serializers.IntegerField()
    reconstructed_fraction = serializers.FloatField(min_value=0, max_value=1)
    weather_coverage_ratio = serializers.FloatField(min_value=0, max_value=1, required=False)
    quality_flags = serializers.ListField(child=serializers.CharField())
    causes = serializers.ListField(child=serializers.JSONField())
    explanation = serializers.JSONField()
    review_status = serializers.CharField()


class RegionResponse(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    country_code = serializers.CharField(allow_blank=True)
    bbox = serializers.ListField(child=serializers.FloatField(), min_length=4, max_length=4)
    provider = serializers.CharField()
    external_id = serializers.CharField()
    fetched_at = serializers.DateTimeField()
    geometry = serializers.JSONField(allow_null=True)


class CandidateResponse(serializers.Serializer):
    candidate_id = serializers.UUIDField()
    geometry = serializers.JSONField()
    bbox = serializers.ListField(child=serializers.FloatField())
    area_ha = serializers.FloatField()
    name = serializers.CharField(allow_null=True)
    source = serializers.CharField()
    source_ref = serializers.CharField()
    source_date = serializers.DateField(allow_null=True)
    confidence = serializers.FloatField(allow_null=True)
    boundary_kind = serializers.ChoiceField(choices=["mapped_landuse", "derived_cropland_candidate"])
    expires_at = serializers.DateTimeField()


def list_response(name, item, **extra):
    return type(
        name,
        (serializers.Serializer,),
        {
            "items": item(many=True),
            "next_cursor": serializers.CharField(allow_null=True),
            "total": serializers.IntegerField(allow_null=True),
            **extra,
        },
    )


PolygonList = list_response("PolygonList", PolygonResponse)
RunList = list_response("RunList", RunResponse)
RegionList = list_response("RegionList", RegionResponse)
DailySeries = list_response(
    "DailySeries", DailyPointResponse, actual_resolution=serializers.ChoiceField(choices=["daily"])
)
AggregatedSeries = list_response(
    "AggregatedSeries",
    AggregatedPointResponse,
    actual_resolution=serializers.ChoiceField(choices=["weekly", "monthly"]),
)
AnomalyList = list_response("AnomalyList", AnomalyResponse)
DiscoveryResponse = list_response(
    "DiscoveryResponse",
    CandidateResponse,
    status=serializers.CharField(),
    source_status=serializers.JSONField(),
    coverage=serializers.JSONField(),
)


class RunAccepted(serializers.Serializer):
    run_id = serializers.UUIDField()
    job_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=["queued", "running"])
    reused = serializers.BooleanField()


class DiscoveryAccepted(serializers.Serializer):
    discovery_id = serializers.UUIDField()
    job_id = serializers.UUIDField()
    state = serializers.CharField()
    reused = serializers.BooleanField()


class ExportAccepted(serializers.Serializer):
    export_id = serializers.UUIDField()
    job_id = serializers.UUIDField()
    state = serializers.CharField()
    reused = serializers.BooleanField()


class ExportResponse(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    filename = serializers.CharField()
    hash = serializers.CharField(allow_null=True)
    expires_at = serializers.DateTimeField()
    download_url = serializers.CharField(allow_null=True)
    manifest_url = serializers.CharField(allow_null=True)


class ComparisonPointResponse(serializers.Serializer):
    alignment_key = serializers.CharField(
        help_text="ISO date для calendar; MM-DD для day_of_year, 29 февраля сохраняется"
    )
    date = serializers.DateField()
    reconstructed = serializers.FloatField(allow_null=True)
    origin = serializers.CharField()
    zscore = serializers.FloatField(allow_null=True)
    clean_primary = serializers.FloatField(allow_null=True)
    quality_flags = serializers.ListField(child=serializers.CharField())


class ComparisonSeriesResponse(serializers.Serializer):
    run_id = serializers.UUIDField()
    points = ComparisonPointResponse(many=True)


class ComparisonItemResponse(serializers.Serializer):
    run = RunResponse()
    series_url = serializers.CharField()


class ComparisonResponse(serializers.Serializer):
    alignment = serializers.ChoiceField(choices=["calendar", "day_of_year"])
    alignment_rule = serializers.CharField()
    axis = serializers.ListField(child=serializers.CharField())
    aligned_series = ComparisonSeriesResponse(many=True)
    items = ComparisonItemResponse(many=True)
    warnings = serializers.ListField(child=serializers.CharField())


class QualityResponse(serializers.Serializer):
    summary = SummaryResponse(allow_null=True)
    exclusions = serializers.DictField(child=serializers.IntegerField())
    warnings = serializers.ListField(child=serializers.JSONField())
    model = serializers.JSONField()
    reference = serializers.JSONField()
    observed_days_definition = serializers.CharField()


class ErrorDetail(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.JSONField()
    retryable = serializers.BooleanField()
    request_id = serializers.UUIDField()


class ErrorResponse(serializers.Serializer):
    error = ErrorDetail()
