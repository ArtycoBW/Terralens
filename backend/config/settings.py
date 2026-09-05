import os
import sys
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parents[2]
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "local-development-only-change-before-deployment")
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
CSRF_TRUSTED_ORIGINS = os.getenv(
    "CSRF_TRUSTED_ORIGINS", "http://localhost:8000,http://localhost:3000,http://127.0.0.1:8000"
).split(",")
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.gis",
    "rest_framework",
    "drf_spectacular",
    "apps.core",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {
    "default": (
        dj_database_url.parse(os.environ["DATABASE_URL"], conn_max_age=60)
        if os.getenv("DATABASE_URL")
        else {
            "NAME": os.getenv("POSTGRES_DB", "terralens"),
            "USER": os.getenv("POSTGRES_USER", "terralens"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", "terralens"),
            "HOST": os.getenv("POSTGRES_HOST", "127.0.0.1"),
            "PORT": os.getenv("POSTGRES_PORT", "54329"),
            "CONN_MAX_AGE": 60,
        }
    )
}
DATABASES["default"]["ENGINE"] = "django.contrib.gis.db.backends.postgis"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "ru"
APPEND_SLASH = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SESSION_COOKIE_AGE = 7 * 24 * 3600
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["apps.core.access.WorkspacePermission"],
    "DEFAULT_PARSER_CLASSES": ["apps.core.parsers.BoundedJSONParser"],
    "EXCEPTION_HANDLER": "apps.core.errors.exception_handler",
    "UNAUTHENTICATED_USER": None,
}
SPECTACULAR_SETTINGS = {
    "TITLE": "TerraLens API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "EstimateOriginEnum": [
            "observed",
            "interpolated",
            "extrapolated",
            "climatology_fallback",
            "unavailable",
        ],
        "CropOriginEnum": ["user", "provider", "unknown"],
    },
}
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:56379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_SOFT_TIME_LIMIT = 1800
CELERY_TASK_TIME_LIMIT = 1860
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE = {
    "reconcile-jobs": {"task": "apps.core.tasks.reconcile", "schedule": 30.0},
    "cleanup-retention": {"task": "apps.core.tasks.cleanup_retention", "schedule": 3600.0},
}
ARTIFACT_ROOT = Path(os.getenv("ARTIFACT_ROOT", BASE_DIR / "artifacts")).resolve()
ACTIVE_MODEL_MANIFEST = Path(
    os.getenv("ACTIVE_MODEL_MANIFEST", BASE_DIR / "ml/artifacts/final/manifest.json")
)
MAX_POLYGON_AREA_HA = float(os.getenv("MAX_POLYGON_AREA_HA", "10000"))
MAX_VERTICES = int(os.getenv("MAX_VERTICES", "5000"))
MAX_SCENES = int(os.getenv("MAX_SCENES", "80"))
MAX_ACTIVE_JOBS = int(os.getenv("MAX_ACTIVE_JOBS", "3"))
MAX_PERIOD_DAYS = int(os.getenv("MAX_PERIOD_DAYS", "366"))
WORKSPACE_DAYS = int(os.getenv("WORKSPACE_DAYS", "7"))
MAX_POLYGONS = int(os.getenv("MAX_POLYGONS", "20"))
EXPORT_DAYS = int(os.getenv("EXPORT_DAYS", "1"))
SNAPSHOT_RETENTION_DAYS = int(os.getenv("SNAPSHOT_RETENTION_DAYS", "30"))
ARTIFACT_ORPHAN_GRACE_HOURS = int(os.getenv("ARTIFACT_ORPHAN_GRACE_HOURS", "24"))
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "config.logging.JSONFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

# Локальная разработка macOS использует те же GEOS/GDAL из установленных wheels.
# В контейнере динамические библиотеки устанавливаются системным пакетным менеджером.
if sys.platform == "darwin":
    import rasterio
    import shapely

    for name, package, pattern in [
        ("GEOS_LIBRARY_PATH", shapely, "libgeos_c*.dylib"),
        ("GDAL_LIBRARY_PATH", rasterio, "libgdal*.dylib"),
    ]:
        candidates = list((Path(package.__file__).parent / ".dylibs").glob(pattern))
        if candidates:
            globals()[name] = str(candidates[0])
