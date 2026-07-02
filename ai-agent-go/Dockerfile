FROM golang:1.25-alpine AS build

WORKDIR /src

COPY go.mod ./
COPY go.sum ./
COPY *.go ./

# COPY ollamamodel ./ollamamodel

RUN go mod tidy
RUN CGO_ENABLED=0 go build -o /out/ai-agent .

FROM alpine:3.22

WORKDIR /srv/ai-agent

COPY --from=build /out/ai-agent /usr/local/bin/ai-agent

ENV PORT=8300
CMD ["ai-agent"]
