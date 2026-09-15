FROM python:3.12-slim

ARG RAIJIN_SERVICE_VERSION=0.5.0
ARG RAIJIN_BUILD_REVISION=development
ENV RAIJIN_SERVICE_VERSION=${RAIJIN_SERVICE_VERSION} \
    RAIJIN_BUILD_REVISION=${RAIJIN_BUILD_REVISION}

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
