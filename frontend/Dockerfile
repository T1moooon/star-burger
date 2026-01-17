FROM node:18-bookworm-slim
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
  python3 build-essential ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY package*.json ./
RUN npm ci --no-audit --fund=false

COPY bundles-src ./bundles-src
