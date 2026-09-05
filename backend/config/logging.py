"""Структурированные сообщения без тел запросов и секретов провайдеров."""

import json
import logging
from datetime import UTC, datetime


class JSONFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "run_id", "job_id", "status_code", "duration_ms", "stage"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            # Исключения HTTP/rasterio могут включать URL с временной подписью.
            # Тип достаточен для корреляции; текст провайдеров нормализует адаптер.
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False, default=str)
