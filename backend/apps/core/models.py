import uuid

from django.contrib.gis.db import models
from django.db.models import Q


class Entity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Workspace(Entity):
    expires_at = models.DateTimeField(db_index=True)


class Region(Entity):
    name = models.CharField(max_length=500)
    country_code = models.CharField(max_length=2, blank=True)
    provider = models.CharField(max_length=40, default="nominatim")
    external_id = models.CharField(max_length=100)
    bbox = models.JSONField()
    geometry = models.GeometryField(srid=4326, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "external_id"], name="unique_region_source")
        ]


class Polygon(Entity):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=200)
    source = models.CharField(max_length=40, default="user")
    source_ref = models.TextField(blank=True)
    current_version = models.PositiveIntegerField(default=1)
    crop_type = models.CharField(max_length=100, null=True)
    deleted_at = models.DateTimeField(null=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["workspace", "-created_at"],
                condition=Q(deleted_at__isnull=True),
                name="active_workspace_polygons",
            )
        ]


class PolygonVersion(Entity):
    polygon = models.ForeignKey(Polygon, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    geometry = models.MultiPolygonField(srid=4326)
    geometry_hash = models.CharField(max_length=64, db_index=True)
    area_ha = models.FloatField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["polygon", "version"], name="unique_polygon_version")]


class CropSeason(Entity):
    polygon = models.ForeignKey(Polygon, on_delete=models.CASCADE)
    season_start = models.DateField()
    season_end = models.DateField()
    crop_type = models.CharField(max_length=100, null=True)
    origin = models.CharField(max_length=20, default="user")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(season_end__gte=models.F("season_start")), name="crop_season_date_order"
            ),
        ]


class ModelVersion(Entity):
    model_id = models.CharField(max_length=64, unique=True)
    artifact_hash = models.CharField(max_length=64)
    manifest_path = models.TextField()
    manifest = models.JSONField()
    active = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["active"], condition=Q(active=True), name="one_active_model")
        ]


class SourceSnapshot(Entity):
    provider = models.CharField(max_length=60)
    query_hash = models.CharField(max_length=64, db_index=True)
    geometry_hash = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=20)
    artifact_path = models.TextField()
    checksum = models.CharField(max_length=64)
    metadata = models.JSONField()


class AnalysisRun(Entity):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    polygon_version = models.ForeignKey(PolygonVersion, on_delete=models.PROTECT)
    model_version = models.ForeignKey(ModelVersion, on_delete=models.PROTECT)
    period_from = models.DateField()
    period_to = models.DateField()
    mode = models.CharField(max_length=20, default="retrospective")
    config = models.JSONField()
    fingerprint = models.CharField(max_length=64)
    state = models.CharField(max_length=20, default="queued", db_index=True)
    completed_at = models.DateTimeField(null=True)
    result_version = models.CharField(max_length=64, null=True)
    summary = models.JSONField(null=True)
    warnings = models.JSONField(default=list)
    snapshots = models.ManyToManyField(SourceSnapshot)

    class Meta:
        indexes = [models.Index(fields=["workspace", "-created_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "fingerprint"],
                condition=Q(state__in=["queued", "running"]),
                name="one_active_analysis",
            )
        ]


class DailyEstimate(models.Model):
    run = models.ForeignKey(AnalysisRun, on_delete=models.CASCADE, related_name="points")
    date = models.DateField()
    data = models.JSONField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["run", "date"], name="unique_run_date")]
        ordering = ["date"]


class AnomalyPeriod(Entity):
    run = models.ForeignKey(AnalysisRun, on_delete=models.CASCADE, related_name="anomalies")
    start_date = models.DateField()
    end_date = models.DateField()
    severity = models.CharField(max_length=20)
    data = models.JSONField()


class Discovery(Entity):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    region = models.ForeignKey(Region, on_delete=models.PROTECT, null=True)
    bbox = models.JSONField()
    status = models.CharField(max_length=20, default="queued")
    source_status = models.JSONField(default=dict)


class CandidatePolygon(Entity):
    discovery = models.ForeignKey(Discovery, on_delete=models.CASCADE, related_name="candidates")
    geometry = models.MultiPolygonField(srid=4326)
    area_ha = models.FloatField()
    source_ref = models.TextField()
    name = models.CharField(max_length=200, null=True)
    expires_at = models.DateTimeField()


class Export(Entity):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    run = models.ForeignKey(AnalysisRun, on_delete=models.CASCADE)
    format = models.CharField(max_length=10)
    state = models.CharField(max_length=20, default="queued")
    artifact_path = models.TextField(blank=True)
    checksum = models.CharField(max_length=64, blank=True)
    manifest_checksum = models.CharField(max_length=64, blank=True)
    expires_at = models.DateTimeField()


class Job(Entity):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    kind = models.CharField(max_length=20)
    state = models.CharField(max_length=20, default="queued", db_index=True)
    stage = models.CharField(max_length=40, default="validating")
    progress = models.FloatField(null=True)
    attempt = models.PositiveSmallIntegerField(default=1)
    heartbeat_at = models.DateTimeField(null=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    dispatched_at = models.DateTimeField(null=True)
    cancel_requested = models.BooleanField(default=False)
    retryable = models.BooleanField(default=False)
    error = models.JSONField(null=True)
    run = models.ForeignKey(AnalysisRun, on_delete=models.CASCADE, null=True, related_name="jobs")
    discovery = models.ForeignKey(Discovery, on_delete=models.CASCADE, null=True, related_name="jobs")
    export = models.ForeignKey(Export, on_delete=models.CASCADE, null=True, related_name="jobs")
    parent_job = models.ForeignKey("self", on_delete=models.SET_NULL, null=True)


class IdempotencyRecord(Entity):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    response = models.JSONField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "key"], name="unique_workspace_idempotency")
        ]
