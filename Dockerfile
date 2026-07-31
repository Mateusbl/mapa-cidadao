
FROM docker.io/python:3.12-slim
 
RUN apt-get update && apt-get install -y \
    gdal-bin libgdal-dev \
    libgeos-dev \
    proj-bin libproj-dev \
    postgresql-client \
    git \
    && rm -rf /var/lib/apt/lists/*
 
WORKDIR /workspace
 
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
 
