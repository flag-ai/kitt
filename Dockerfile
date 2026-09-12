FROM python:3.12-slim

# Install system deps for psutil/pynvml compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc python3-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Install Docker CLI (static binary — works on both amd64 and arm64)
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then DOCKER_ARCH=x86_64; \
    elif [ "$ARCH" = "aarch64" ]; then DOCKER_ARCH=aarch64; \
    else DOCKER_ARCH=$ARCH; fi && \
    curl -fsSL "https://download.docker.com/linux/static/stable/${DOCKER_ARCH}/docker-27.5.1.tgz" \
    | tar xz --strip-components=1 -C /usr/local/bin docker/docker

WORKDIR /app

# Configure Poetry to create venv in-project so the path is predictable
ENV POETRY_VIRTUALENVS_IN_PROJECT=1

# Install poetry and project dependencies
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --no-root --without dev --extras web --extras devon \
    && poetry run pip install build

COPY README.md ./
COPY src/ ./src/
COPY configs/ ./configs/
COPY agent-package/ ./agent-package/
RUN poetry install --only-root --extras web --extras devon

# Expose the venv bin so "kitt" is callable without "poetry run"
ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["kitt"]
