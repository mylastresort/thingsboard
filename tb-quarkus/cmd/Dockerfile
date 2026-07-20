# syntax=docker/dockerfile:1.7

FROM node:22-slim AS node

FROM gradle:8.10.2-jdk21 AS build

WORKDIR /home/gradle/project

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

COPY tb-quarkus/cmd/settings.gradle tb-quarkus/cmd/build.gradle tb-quarkus/cmd/gradle.properties ./
COPY api-specs/openapi ./openapi-source
COPY tb-quarkus/cmd/src ./src

RUN --mount=type=cache,target=/home/gradle/.gradle \
    gradle --no-daemon test
RUN --mount=type=cache,target=/home/gradle/.gradle \
    gradle --no-daemon quarkusBuild

FROM eclipse-temurin:21-jre

LABEL org.opencontainers.image.title="tb-quarkus-cmd" \
      org.opencontainers.image.description="ThingsBoard Quarkus command-line tool"

WORKDIR /app

COPY --from=build /home/gradle/project/build/*-runner.jar /app/tb-quarkus-cmd.jar

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1001 appuser \
    && useradd --uid 1001 --gid 1001 --create-home --shell /bin/bash appuser \
    && printf '#!/bin/sh\nexec java -jar /app/tb-quarkus-cmd.jar "$@"\n' > /usr/local/bin/tb-quarkus-cmd \
    && chmod 755 /usr/local/bin/tb-quarkus-cmd \
    && chown -R appuser:appuser /app

USER appuser

ENTRYPOINT ["tb-quarkus-cmd"]
CMD ["--help"]
