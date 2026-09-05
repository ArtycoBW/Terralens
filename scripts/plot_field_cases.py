"""Построить графики опубликованных полевых рядов без изменения исходных данных."""

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "docs/analysis/field-cases"
NAMES = {"potsdam": "Потсдам", "seville": "Севилья", "voronezh": "Воронежская область"}


def main():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
    for name, title in NAMES.items():
        report = json.loads((FOLDER / f"{name}.json").read_text(encoding="utf-8"))
        rows = report["daily"]
        dates = [datetime.fromisoformat(row["date"]) for row in rows]
        fig, ax = plt.subplots(figsize=(12, 5.6), layout="constrained")
        fig.set_facecolor("#fafbf6")
        ax.set_facecolor("#fafbf6")
        ax.plot(
            dates, [r["reconstructed"] for r in rows], color="#526824", label="Восстановленный ряд", lw=1.8
        )
        for key, color, marker, label in [
            ("clean_primary", "#142727", "o", "Пригодные наблюдения"),
            ("climatology_mean", "#8d6aaf", "D", "Историческая норма (при наличии)"),
        ]:
            selected = [i for i, r in enumerate(rows) if r[key] is not None]
            ax.scatter(
                [dates[i] for i in selected],
                [rows[i][key] for i in selected],
                s=30,
                marker=marker,
                color=color,
                label=label,
                zorder=4,
            )
        for i, event in enumerate(report["events"]):
            start = datetime.fromisoformat(event["start_date"])
            end = datetime.fromisoformat(event["end_date"]) + timedelta(days=1)
            ax.axvspan(start, end, alpha=0.13, color="#b74222", label="Событие алгоритма" if i == 0 else None)
        ax.set(title=f"{title} · 01.06–31.07.2024", ylabel="NDVI", ylim=(0, 1), xlim=(dates[0], dates[-1]))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
        ax.grid(axis="y", alpha=0.22)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(loc="upper left", bbox_to_anchor=(0, -0.12), ncol=2, frameon=False)
        note = (
            "Сигнал ниже исторической нормы; причина не подтверждена. Текущий NDVI может расти."
            if report["events"]
            else "Событий нет; исторической нормы недостаточно для статуса «Норма»."
        )
        fig.supxlabel(note, fontsize=10)
        for extension in ("svg", "png"):
            fig.savefig(FOLDER / f"{name}.{extension}", dpi=160)
        svg_path = FOLDER / f"{name}.svg"
        svg_path.write_text(
            "\n".join(line.rstrip() for line in svg_path.read_text(encoding="utf-8").splitlines()) + "\n",
            encoding="utf-8",
        )
        plt.close(fig)
        with (FOLDER / f"{name}-daily.csv").open("w", newline="", encoding="utf-8") as stream:
            columns = [
                "date",
                "clean_primary",
                "reconstructed",
                "origin",
                "source_sensor",
                "climatology_mean",
                "climatology_std",
                "zscore",
            ]
            writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    main()
