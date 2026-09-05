import io

from django.conf import settings
from rest_framework.parsers import JSONParser

from .errors import DomainError


class BoundedJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        # Ограничиваем чтение и для запросов без достоверного Content-Length.
        limit = settings.DATA_UPLOAD_MAX_MEMORY_SIZE
        payload = stream.read(limit + 1)
        if len(payload) > limit:
            raise DomainError("payload_too_large", "Тело запроса превышает допустимый размер", 413)
        return super().parse(io.BytesIO(payload), media_type=media_type, parser_context=parser_context)
