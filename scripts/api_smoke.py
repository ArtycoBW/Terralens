"""HTTP → очередь → реальные источники; сохраняет доказательства без session cookies."""

import argparse
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np


def await_job(client, job_id, timeout=1800):
    deadline, last = time.monotonic() + timeout, None
    while time.monotonic() < deadline:
        response = client.get(f"/jobs/{job_id}")
        response.raise_for_status()
        job = response.json()
        status = (job["state"], job["stage"], job["progress"])
        if status != last:
            print(json.dumps({"state": status[0], "stage": status[1], "progress": status[2]}), flush=True)
            last = status
        if job["state"] in ["succeeded", "failed", "cancelled"]:
            return job
        time.sleep(2)
    raise RuntimeError("Превышено время smoke-теста")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--geometry", default="backend/tests/fixtures/potsdam.geojson")
    parser.add_argument("--from", dest="start", default="2024-06-01")
    parser.add_argument("--to", dest="end", default="2024-06-10")
    parser.add_argument("--reference-years", type=int, default=0)
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=["sentinel2", "landsat", "era5_land"],
        default=["sentinel2", "landsat", "era5_land"],
    )
    parser.add_argument("--skip-exports", action="store_true")
    parser.add_argument("--read-checks", type=int, default=40)
    parser.add_argument("--output", default="artifacts/api-smoke")
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists() and any(output.iterdir()):
        parser.error("Для нового запуска укажите пустой --output: старые доказательства не перезаписываются")
    output.mkdir(parents=True, exist_ok=True)
    feature = json.loads(Path(args.geometry).read_text())
    with httpx.Client(base_url=args.base_url + "/api/v1", timeout=30) as client:
        session = client.post("/session", json={}, headers={"Origin": args.base_url})
        session.raise_for_status()
        client.headers["X-CSRFToken"] = session.json()["csrf_token"]
        response = client.post(
            "/polygons", json={"name": feature["properties"]["name"], "geometry": feature["geometry"]}
        )
        response.raise_for_status()
        polygon = response.json()
        payload = {
            "polygon_id": polygon["id"],
            "polygon_version": polygon["current_version"],
            "period": {"from": args.start, "to": args.end},
            "mode": "retrospective",
            "sources": args.sources,
            "options": {"climatology_years": args.reference_years},
        }
        started = time.perf_counter()
        created = client.post(
            "/analyses", json=payload, headers={"Idempotency-Key": f"smoke-{polygon['id']}"}
        )
        created.raise_for_status()
        creation_ms = (time.perf_counter() - started) * 1000
        refs = created.json()
        print(json.dumps(refs), flush=True)
        job = await_job(client, refs["job_id"])
        run = client.get(f"/analyses/{refs['run_id']}")
        run.raise_for_status()
        result = run.json()
        for name, value in [("request", payload), ("polygon", polygon), ("job", job), ("run", result)]:
            (output / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2))
        points, cursor = [], None
        while True:
            params = {"limit": 200, **({"cursor": cursor} if cursor else {})}
            series = client.get(f"/analyses/{refs['run_id']}/series", params=params)
            series.raise_for_status()
            page = series.json()
            points.extend(page["items"])
            cursor = page["next_cursor"]
            if not cursor:
                break
        (output / "series.json").write_text(
            json.dumps(
                {"items": points, "next_cursor": None, "actual_resolution": "daily"},
                ensure_ascii=False,
                indent=2,
            )
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if job["state"] != "succeeded" or not result["summary"]["observed_days"]:
            raise RuntimeError("Расчёт не дал пригодных наблюдений")
        if not args.skip_exports:
            for export_format in ("csv", "geojson", "json"):
                response = client.post(
                    "/exports",
                    json={"run_id": refs["run_id"], "format": export_format},
                    headers={"Idempotency-Key": f"smoke-{refs['run_id']}-{export_format}"},
                )
                response.raise_for_status()
                exported = response.json()
                if await_job(client, exported["job_id"], timeout=120)["state"] != "succeeded":
                    raise RuntimeError("Не удалось создать экспорт")
                metadata = client.get(f"/exports/{exported['export_id']}").json()
                download = client.get(f"/exports/{exported['export_id']}/download")
                download.raise_for_status()
                if hashlib.sha256(download.content).hexdigest() != metadata["hash"]:
                    raise RuntimeError("Контрольная сумма экспорта не совпала")
                (output / f"export.{export_format}").write_bytes(download.content)
                manifest = client.get(f"/exports/{exported['export_id']}/manifest")
                manifest.raise_for_status()
                (output / f"export.{export_format}.manifest.json").write_bytes(manifest.content)
        if args.read_checks > 0:

            def measure(index):
                endpoint = [f"/analyses/{refs['run_id']}", f"/polygons/{polygon['id']}", "/models"][index % 3]
                start = time.perf_counter()
                response = client.get(endpoint)
                response.raise_for_status()
                return (time.perf_counter() - start) * 1000

            with ThreadPoolExecutor(max_workers=4) as pool:
                timings = list(pool.map(measure, range(args.read_checks)))
            evidence = {
                "requests": len(timings),
                "concurrency": 4,
                "p95_ms": float(np.percentile(timings, 95)),
                "max_ms": max(timings),
                "analysis_post_ms": creation_ms,
                "scope": "local HTTP smoke, warm small database; not a capacity benchmark",
            }
            (output / "latency.json").write_text(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
