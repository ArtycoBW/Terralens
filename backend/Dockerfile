FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends libgdal32 libgeos-c1v5 libproj25 curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN pip install --require-hashes -r requirements.lock
COPY ml /app/ml
COPY backend /app/backend
COPY uv.lock /app/uv.lock
RUN pip install --no-deps ./ml ./backend && useradd --uid 10001 --create-home terralens && mkdir -p /app/artifacts && chown -R terralens:terralens /app
WORKDIR /app/backend
USER terralens
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", "--access-logfile", "-"]
