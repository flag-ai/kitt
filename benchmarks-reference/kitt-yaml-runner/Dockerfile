# kitt-yaml-runner — shared runtime for YAML-kind benchmarks.
#
# Reads a YAML spec (dataset / prompt / sampling / parse / score) and
# runs it against an OpenAI-compatible engine endpoint, emitting the
# standard /results/out.json.
FROM python:3.12-slim

# Keep the layer lean — just HTTP + YAML + HF datasets. No torch, no
# CUDA — the runner never does inference locally, it only talks to the
# engine via HTTP.
RUN pip install --no-cache-dir \
    httpx==0.27.2 \
    pyyaml==6.0.2 \
    datasets==3.0.1

WORKDIR /app
COPY entrypoint.py /app/entrypoint.py

# Results volume is expected to be mounted by BONNIE's paired-run
# helper; create the default path for smoke tests that don't mount.
RUN mkdir -p /results

ENTRYPOINT ["python", "/app/entrypoint.py"]
