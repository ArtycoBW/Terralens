import json


def polygon_data(polygon):
    version = polygon.versions.get(version=polygon.current_version)
    latest = (
        polygon.versions.filter(version=polygon.current_version, analysisrun__isnull=False)
        .order_by("-analysisrun__created_at")
        .values_list("analysisrun__id", flat=True)
        .first()
    )
    return {
        "id": str(polygon.id),
        "workspace_id": str(polygon.workspace_id),
        "region_id": str(polygon.region_id) if polygon.region_id else None,
        "name": polygon.name,
        "current_version": polygon.current_version,
        "geometry": json.loads(version.geometry.geojson),
        "geometry_hash": version.geometry_hash,
        "area_ha": version.area_ha,
        "source": polygon.source,
        "source_ref": polygon.source_ref,
        "crop_type": polygon.crop_type,
        "crop_seasons": [
            {
                "id": str(season.id),
                "season_start": str(season.season_start),
                "season_end": str(season.season_end),
                "crop_type": season.crop_type,
                "origin": season.origin,
            }
            for season in polygon.cropseason_set.order_by("season_start", "id")
        ],
        "created_at": polygon.created_at,
        "updated_at": polygon.updated_at,
        "latest_run_id": str(latest) if latest else None,
    }


def run_data(run):
    job = run.jobs.order_by("-created_at").first()
    return {
        "id": str(run.id),
        "polygon_id": str(run.polygon_version.polygon_id),
        "polygon_version": run.polygon_version.version,
        "mode": run.mode,
        "period": {"from": str(run.period_from), "to": str(run.period_to)},
        "state": run.state,
        "job_id": str(job.id) if job else None,
        "model_version": run.model_version.model_id,
        "config_version": "v1",
        "created_at": run.created_at,
        "completed_at": run.completed_at,
        "snapshots": [
            {
                "id": str(s.id),
                "provider": s.provider,
                "checksum": s.checksum,
                "retrieved_at": s.created_at,
                "status": s.status,
            }
            for s in run.snapshots.all()
        ],
        "warnings": run.warnings,
        "summary": run.summary,
        "result_version": run.result_version,
    }


def job_data(job):
    ref = job.run_id or job.discovery_id or job.export_id
    return {
        "id": str(job.id),
        "kind": job.kind,
        "state": job.state,
        "stage": job.stage,
        "progress": job.progress,
        "attempt": job.attempt,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "cancel_requested": job.cancel_requested,
        "retryable": job.retryable,
        "error": job.error,
        "result": {"type": job.kind, "id": str(ref)} if ref else None,
        "parent_job_id": str(job.parent_job_id) if job.parent_job_id else None,
    }


def region_data(region):
    return {
        "id": str(region.id),
        "name": region.name,
        "country_code": region.country_code,
        "bbox": region.bbox,
        "provider": region.provider,
        "external_id": region.external_id,
        "fetched_at": region.updated_at,
        "geometry": json.loads(region.geometry.geojson) if region.geometry else None,
    }


def candidate_data(candidate):
    return {
        "candidate_id": str(candidate.id),
        "geometry": json.loads(candidate.geometry.geojson),
        "bbox": list(candidate.geometry.extent),
        "area_ha": candidate.area_ha,
        "name": candidate.name,
        "source": "osm",
        "source_ref": candidate.source_ref,
        "source_date": None,
        "confidence": None,
        "boundary_kind": "mapped_landuse",
        "expires_at": candidate.expires_at,
    }
