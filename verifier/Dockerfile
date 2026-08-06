FROM docker.io/python:3.12.13-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi==0.115.6 uvicorn==0.34.0

COPY main.py .

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

USER appuser

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
