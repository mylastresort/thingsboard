# Stage 1 — Build Angular frontend
FROM node:22-bookworm-slim AS frontend-builder

WORKDIR /app

RUN apt-get update && apt-get install -y git python3 make g++ default-jre-headless && rm -rf /var/lib/apt/lists/*

COPY ui-ngx/package.json ui-ngx/yarn.lock ./
RUN yarn install --non-interactive --network-concurrency 4 --network-timeout 100000 --mutex network --ignore-engines

COPY ui-ngx/ .
COPY api-specs /api-specs
RUN yarn run generate:api
RUN yarn build:prod

# Stage 2 — Build the Express proxy server
FROM node:22-bookworm-slim AS server-builder

WORKDIR /build

COPY msa/web-ui/package.json msa/web-ui/yarn.lock ./
RUN yarn install --non-interactive --network-concurrency 4 --network-timeout 100000 --mutex network --ignore-engines

COPY msa/web-ui/server.ts msa/web-ui/tsconfig.json ./
COPY msa/web-ui/config/logger.ts ./config/logger.ts
RUN yarn build

# Stage 3 — Lean production image
FROM node:22-bookworm-slim AS production

ENV NODE_ENV=production
ENV DOCKER_MODE=true

WORKDIR /usr/share/tb-web-ui

# Built Angular assets
COPY --from=frontend-builder /app/target/generated-resources/public ./web/public

# Compiled server + logger
COPY --from=server-builder /build/target/src/server.js ./server.js
COPY --from=server-builder /build/target/src/config/logger.js ./config/logger.js

# Production deps only
COPY msa/web-ui/package.json msa/web-ui/yarn.lock ./
RUN yarn install --production --non-interactive --network-concurrency 4 --network-timeout 100000 --mutex network && \
    yarn cache clean --all

# Config files
COPY msa/web-ui/config/default.yml ./config/production.yml
COPY msa/web-ui/config/custom-environment-variables.yml ./config/custom-environment-variables.yml

# Startup script
COPY msa/web-ui/start-web-ui.sh /usr/bin/start-web-ui.sh
RUN chmod +x /usr/bin/start-web-ui.sh && \
    chown -R node:node /usr/share/tb-web-ui

USER node
EXPOSE 8090

CMD ["start-web-ui.sh"]