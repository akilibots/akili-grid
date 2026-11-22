FROM python:3.15.2-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
RUN apt-get update && apt-get install -y --no-install-recommends pkg-config libsecp256k1-dev && rm -rf /var/lib/apt/lists/*
RUN apt-get update && apt-get install -y --no-install-recommends cargo && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements.txt build-constraints.txt ./
RUN --mount=type=cache,target=/root/.cache/pip PIP_BUILD_CONSTRAINT=/build/build-constraints.txt pip wheel --wheel-dir=/wheels -r requirements.txt

FROM python:3.15.2-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt && pip check && rm -rf /wheels
COPY . .
CMD ["python3", "run.py"]

FROM runtime AS test
RUN --mount=type=cache,target=/root/.cache/pip pip install pytest==9.2.0
CMD ["python3", "-m", "pytest", "-q", "-p", "no:cacheprovider"]

FROM runtime AS production
