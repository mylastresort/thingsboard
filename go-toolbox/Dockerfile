# Single multi-stage Dockerfile for all go-toolbox units. `base` installs the
# Go toolchain once; each unit stage installs its own binary on top. Compose
# picks a stage via `target:`, so there's no separate base image to build
# first and no cross-service FROM resolution to fight with BuildKit.
FROM golang:1.25-bookworm AS base
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ENV GOPATH=/go
ENV PATH=$GOPATH/bin:$PATH
WORKDIR /src
COPY . .

FROM base AS load
RUN go install ./cmd/load
CMD ["load"]

FROM base AS interpreter
RUN go install ./cmd/interpreter
CMD ["interpreter"]

FROM base AS dash
RUN apt-get update && apt-get install -y --no-install-recommends \
    mosquitto-clients \
    && rm -rf /var/lib/apt/lists/*
RUN go install ./cmd/dash
CMD ["dash"]

FROM base AS darktheme-build
RUN go build -o /darktheme ./cmd/darktheme

FROM node:22-alpine AS darktheme
COPY --from=darktheme-build /darktheme /usr/local/bin/darktheme
ENTRYPOINT ["darktheme"]
