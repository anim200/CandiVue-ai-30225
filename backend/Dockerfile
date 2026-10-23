# Two images from one file:
#   runtime - the backend app (used by "docker compose up")
#   test    - runtime plus test tools (used by "docker compose run --rm tests")

FROM python:3.13.16-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Tesseract OCR reads scanned CVs (F1 OCR fallback); English only (A7).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Face models for the identity check (F7) from the OpenCV Model Zoo, pinned
# to one commit and checked: YuNet (MIT) and SFace (Apache 2.0).
ARG ZOO=https://github.com/opencv/opencv_zoo/raw/47534e27c9851bb1128ccc0102f1145e27f23f98/models
ADD --chmod=644 --checksum=sha256:8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4     ${ZOO}/face_detection_yunet/face_detection_yunet_2023mar.onnx /opt/face-models/
ADD --chmod=644 --checksum=sha256:0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79     ${ZOO}/face_recognition_sface/face_recognition_sface_2021dec.onnx /opt/face-models/
RUN chmod 755 /opt/face-models  # the folder must be enterable by appuser

# Install dependencies first so Docker can cache this layer.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

# Run as a normal user, not root. The CV intake folder is created here so
# the named volume mounted on it belongs to that user.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data/cv_intake && chown appuser /data/cv_intake
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
