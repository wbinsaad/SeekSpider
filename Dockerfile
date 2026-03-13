# syntax=docker/dockerfile:1

############################
# Stage 1: Frontend deps
############################
FROM node:20-alpine AS frontend-deps

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH

WORKDIR /app/frontend

# Keep pnpm version explicit, same as current behavior
RUN corepack enable && corepack prepare pnpm@10.19.0 --activate

# Copy only dependency metadata first for better cache reuse
COPY frontend/package.json frontend/pnpm-lock.yaml* ./

# Pre-fetch packages into pnpm store; designed by pnpm for Docker builds
RUN --mount=type=cache,target=/pnpm/store \
    pnpm fetch

############################
# Stage 2: Build frontend
############################
FROM node:20-alpine AS frontend-builder

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH

# Build-time memory knob.
# Default kept conservative for low-memory hosts; override at build time if needed:
# docker build --build-arg NODE_OPTIONS="--max-old-space-size=1024" ...
ARG NODE_OPTIONS="--max-old-space-size=768"
ENV NODE_OPTIONS=$NODE_OPTIONS

WORKDIR /app/frontend

RUN corepack enable && corepack prepare pnpm@10.19.0 --activate

COPY frontend/package.json frontend/pnpm-lock.yaml* ./

# Reuse the fetched store and install from it
RUN --mount=type=cache,target=/pnpm/store \
    pnpm install --frozen-lockfile --prefer-offline

COPY frontend/ ./

RUN pnpm build

############################
# Stage 3: Runtime
############################
FROM python:3.11-slim AS runtime

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/pipeline:/app:/app/src:/app/scraper:${PYTHONPATH}
ENV SCRAPY_SETTINGS_MODULE=SeekSpider.settings
ENV TZ=Australia/Perth

# Install runtime/system packages in one layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    curl \
    gcc \
    gnupg \
    libxml2-dev \
    libxslt-dev \
    wget \
    xauth \
    xvfb \
    && rm -rf /var/lib/apt/lists/* \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone

# Copy Python dependency metadata first
COPY pyproject.toml setup.cfg MANIFEST.in requirements.txt ./

# Copy Python package source needed by editable install
COPY src/ ./src/

# Install Python deps in a single layer
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
      -e . \
      -r requirements.txt \
      pandas \
      python-dateutil \
      pyvirtualdisplay \
      selenium \
      undetected-chromedriver

# Copy frontend build artifacts from previous stage
# Preserve the current path assumption from your existing Dockerfile.
COPY --from=frontend-builder /app/src/plombery/static ./src/plombery/static

# Copy application code that changes more often after dependency layers
COPY pipeline/ ./pipeline/
COPY scraper/ ./scraper/

RUN mkdir -p /app/data /app/logs /app/output

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

WORKDIR /app/pipeline

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]