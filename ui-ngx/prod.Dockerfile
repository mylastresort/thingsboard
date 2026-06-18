# Stage 1 — Build the Angular frontend
FROM node:22-bookworm-slim AS frontend-builder

WORKDIR /build/ui

RUN apt-get update && apt-get install -y git python3 make g++ && rm -rf /var/lib/apt/lists/*

# Clone only the ui-ngx part (or COPY if you have it locally)
COPY ui-ngx/ .

RUN npm install -g yarn && \
    yarn install --non-interactive --network-concurrency 4 --network-timeout 100000 && \
    yarn build:prod

# Stage 2 — Build the Node.js web server
FROM node:22-bookworm-slim AS server-builder

WORKDIR /build/server

COPY src/package.json src/yarn.lock ./
RUN yarn install --non-interactive --network-concurrency 4 --network-timeout 100000

COPY src/ .
RUN yarn tsc || npx tsc

# Stage 3 — Production image
FROM node:22-bookworm-slim AS production

ENV NODE_ENV=production
ENV DOCKER_MODE=true

WORKDIR /usr/share/tb-web-ui

# Copy built frontend
COPY --from=frontend-builder /build/ui/dist/public ./web/public

# Copy compiled server
COPY --from=server-builder /build/server/target/src ./
COPY --from=server-builder /build/server/node_modules ./node_modules

# Copy config files
COPY conf/ ./conf/
COPY conf/ ./config/

# Startup script
COPY start-web-ui.sh /usr/bin/start-web-ui.sh
RUN chmod +x /usr/bin/start-web-ui.sh && \
    chown -R node:node /usr/share/tb-web-ui

USER node

EXPOSE 8090

CMD ["start-web-ui.sh"]