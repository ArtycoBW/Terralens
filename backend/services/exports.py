"""Воспроизводимые файлы результата и сопроводительные метаданные."""

import csv
import io
import json

from terralens_ml.io import canonical_hash


def csv_value(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def build_export(export):
    run = export.run
    points = [point.data for point in run.points.all()]
    anomalies = [event.data | {"id": str(event.id), "run_id": str(run.id)} for event in run.anomalies.all()]
    content = {
        "run_id": str(run.id),
        "result_version": run.result_version,
        "state": run.state,
        "period": {"from": str(run.period_from), "to": str(run.period_to)},
        "polygon_id": str(run.polygon_version.polygon_id),
        "polygon_version": run.polygon_version.version,
        "geometry_hash": run.polygon_version.geometry_hash,
        "model_id": run.model_version.model_id,
        "model_manifest": run.model_version.manifest,
        "model_artifact_hash": run.model_version.artifact_hash,
        "config": run.config,
        "config_hash": canonical_hash(run.config),
        "summary": run.summary,
        "warnings": run.warnings,
        "units": {"ndvi": "dimensionless", "temperature": "degC", "precipitation": "mm/day", "area": "ha"},
        "snapshots": [
            {
                "id": str(snapshot.id),
                "provider": snapshot.provider,
                "checksum": snapshot.checksum,
                "query_hash": snapshot.query_hash,
                "geometry_hash": snapshot.geometry_hash,
                "retrieved_at": snapshot.created_at.isoformat(),
                "status": snapshot.status,
                "metadata": snapshot.metadata,
            }
            for snapshot in run.snapshots.order_by("created_at", "id")
        ],
        "series": points,
        "anomalies": anomalies,
    }
    if export.format == "csv":
        stream = io.StringIO()
        columns = [
            "date",
            "observed_primary",
            "clean_primary",
            "reconstructed",
            "climatology_mean",
            "climatology_std",
            "zscore",
            "origin",
            "source_sensor",
            "interval_lower",
            "interval_upper",
            "interval_level",
            "interval_method",
            "severity",
            "temperature_c",
            "precipitation_mm",
            "weather_provider",
            "support_count",
            "gap_days",
            "reference_years",
            "quality_flags",
        ]
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for point in points:
            row = {key: point.get(key) for key in columns}
            interval = point["prediction_interval"]
            row.update({f"interval_{key}": interval[key] for key in ["lower", "upper", "level", "method"]})
            severities = {
                event["severity"]
                for event in anomalies
                if event["start_date"] <= point["date"] <= event["end_date"]
            }
            row["severity"] = "critical" if "critical" in severities else "stress" if severities else None
            row.update({key: point["weather"][key] for key in ["temperature_c", "precipitation_mm"]})
            row["weather_provider"] = point["weather"]["provider"]
            row["quality_flags"] = "|".join(point["quality_flags"])
            writer.writerow({key: csv_value(value) for key, value in row.items()})
        text = stream.getvalue()
    elif export.format == "geojson":
        text = json.dumps(
            {
                "type": "Feature",
                "geometry": json.loads(run.polygon_version.geometry.geojson),
                "properties": {key: value for key, value in content.items() if key != "series"},
            },
            ensure_ascii=False,
            allow_nan=False,
        )
    else:
        text = json.dumps(content, ensure_ascii=False, allow_nan=False)
    manifest = {key: value for key, value in content.items() if key not in ["series", "anomalies"]}
    manifest.update({"format": export.format, "series_count": len(points), "anomaly_count": len(anomalies)})
    return text, manifest
