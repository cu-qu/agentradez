# Local image for Compose and the Dev Container
FROM node:22-bookworm-slim

ENV NEXT_TELEMETRY_DISABLED=1 \
    NPM_CONFIG_UPDATE_NOTIFIER=false

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000

ENTRYPOINT ["bash", "/app/scripts/docker-entrypoint.sh"]
CMD ["sleep", "infinity"]
