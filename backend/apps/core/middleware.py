import logging
import time
import uuid

logger = logging.getLogger(__name__)


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.monotonic()
        request.request_id = str(uuid.uuid4())
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        response["Cache-Control"] = "private, no-store"
        logger.info(
            "api_request",
            extra={
                "request_id": request.request_id,
                "status_code": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            },
        )
        return response
