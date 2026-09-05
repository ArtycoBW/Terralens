from rest_framework.exceptions import APIException


class DomainError(APIException):
    def __init__(self, code, message, status=422, details=None, retryable=False):
        self.status_code = status
        self.domain_code, self.domain_details, self.retryable = code, details or {}, retryable
        super().__init__(message, code)


def exception_handler(exc, context):
    from django.core.exceptions import RequestDataTooBig
    from rest_framework.views import exception_handler as drf_exception_handler

    if isinstance(exc, RequestDataTooBig):
        exc = DomainError("payload_too_large", "Тело запроса превышает допустимый размер", 413)
    response = drf_exception_handler(exc, context)
    if response is None:
        import logging

        from django.db import OperationalError
        from redis.exceptions import RedisError
        from rest_framework.response import Response

        logging.getLogger(__name__).exception(
            "api_request_failed request_id=%s", getattr(context.get("request"), "request_id", None)
        )
        status = 503 if isinstance(exc, (OperationalError, RedisError)) else 500
        return Response(
            {
                "error": {
                    "code": "service_unavailable" if status == 503 else "internal_error",
                    "message": "Сервис временно недоступен"
                    if status == 503
                    else "Не удалось обработать запрос",
                    "details": {},
                    "retryable": status == 503,
                    "request_id": getattr(context.get("request"), "request_id", None),
                }
            },
            status=status,
        )
    request = context.get("request")
    response.data = {
        "error": {
            "code": getattr(exc, "domain_code", getattr(exc, "default_code", "invalid_request")),
            "message": str(exc.detail)
            if isinstance(exc, DomainError)
            else "Запрос отклонён. Проверьте параметры и доступ.",
            "details": getattr(exc, "domain_details", response.data),
            "retryable": getattr(exc, "retryable", False),
            "request_id": getattr(request, "request_id", None),
        }
    }
    return response
