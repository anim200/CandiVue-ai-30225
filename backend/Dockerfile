# Two images from one file:
#   runtime - the backend app (used by "docker compose up")
#   test    - runtime plus test tools (used by "docker compose run --rm tests")

FROM python:3.13.16-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so Docker can cache this layer.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

# Run as a normal user, not root.
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000
# Bring the database schema up to date, then start the API.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]


FROM runtime AS test

USER root
COPY requirements-dev.txt pytest.ini ./
RUN pip install -r requirements-dev.txt
COPY tests ./tests
USER appuser

# The image folder is read-only for appuser, so no pytest cache.
CMD ["pytest", "-p", "no:cacheprovider"]
