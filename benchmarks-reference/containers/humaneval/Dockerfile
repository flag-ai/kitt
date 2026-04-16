# HumanEval — code execution sandbox.
#
# The reference image does NOT run untrusted code in production-grade
# isolation; that's the orchestrator's responsibility (BONNIE runs the
# container with resource limits). This image sandboxes within the
# container: resource.setrlimit + a subprocess exec per candidate with
# a short timeout.
FROM python:3.12-slim
RUN pip install --no-cache-dir httpx==0.27.2
WORKDIR /app
COPY entrypoint.py /app/entrypoint.py
RUN mkdir -p /results
ENTRYPOINT ["python", "/app/entrypoint.py"]
