FROM python:3.12-slim

# System deps for Docker CLI (used by engines)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc python3-dev docker.io curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Poetry
RUN pip install --no-cache-dir poetry build

# Copy dependency files first (for layer caching)
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-root --without dev -E web

# Copy source
COPY src/ ./src/
COPY configs/ ./configs/
COPY agent-package/ ./agent-package/
COPY docker/web/Dockerfile ./docker/web/Dockerfile
COPY README.md ./
RUN poetry install --only-root

# Default data directories
RUN mkdir -p /data/certs /data/results

ENV KITT_SECRET_KEY=""
ENV KITT_AUTH_TOKEN=""

EXPOSE 8080

ENTRYPOINT ["kitt", "web"]
CMD ["--host", "0.0.0.0", "--port", "8080"]
