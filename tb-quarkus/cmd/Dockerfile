# syntax=docker/dockerfile:1.7

FROM gradle:8.10.2-jdk21 AS build

WORKDIR /home/gradle/project

COPY --chown=gradle:gradle cmd/settings.gradle cmd/build.gradle cmd/gradle.properties ./
COPY --chown=gradle:gradle cmd/src ./src
COPY --chown=gradle:gradle gateway/src/main/resources/META-INF/openapi.yaml ../gateway/src/main/resources/META-INF/openapi.yaml

RUN gradle --no-daemon quarkusBuild

FROM eclipse-temurin:21-jre

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
