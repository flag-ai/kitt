FROM python:3.12-slim
RUN pip install --no-cache-dir httpx==0.27.2
WORKDIR /app
COPY entrypoint.py /app/entrypoint.py
RUN mkdir -p /results
ENTRYPOINT ["python", "/app/entrypoint.py"]
