PROJECT         ?= thingsboard
TB_SERVICE      := thingsboard
WEB_SERVICE     := tb-web-ui-dev
WEB_PROD        := tb-web-ui
PDM_FORECAST_WORKER := pdm-forecast-worker
PDM_ANOMALY_WORKER  := pdm-anomaly-worker
PDM_FORECAST_WORKERS ?= 5
PDM_ANOMALY_WORKERS  ?= 5
PDM_KAFKA_PARTITIONS ?= 16
PDM_KAFKA_TOPICS := pdm-commands pdm-events pdm-job-state
RESET_PDM_STATE_ON_RECREATE ?= true
CONFIG_SERVICE  := config-api
MCP_SERVICE     := thingsboard-mcp
POSTGRES        := postgres
CASSANDRA_SERVICE := cassandra
TB_QUARKUS      := tb-quarkus
TB_QUARKUS_DEV  := tb-quarkus-dev
TB_PREV_VERSION ?= 4.2.2.2
TB_QUARKUS_CACHE_DIR ?= ./tb_quarkus_cache
TB_QUARKUS_CACHE_DEV_DIR ?= ./tb_quarkus_dev_cache
TB_QUARKUS_DOCKERFILE ?= src/main/docker/Dockerfile.jvm
TB_QUARKUS_SMOKE_URL ?= http://localhost:8081/models/failure-mode-history?limit=1
TB_QUARKUS_DEV_SMOKE_URL ?= http://localhost:8082/models/failure-mode-history?limit=1
AI_AGENT       := ai-agent-py

# ─── compose file sets ───────────────────────────────────────────────────────
COMPOSE_DIR := docker-compose

# core = what runs in production
CORE_FILES := -f $(COMPOSE_DIR)/docker-compose.base.yml -f $(COMPOSE_DIR)/docker-compose.db.yml \
               -f $(COMPOSE_DIR)/docker-compose.tb.yml -f $(COMPOSE_DIR)/docker-compose.gateway.yml \
               -f $(COMPOSE_DIR)/docker-compose.web.yml -f $(COMPOSE_DIR)/docker-compose.model.yml \
               -f $(COMPOSE_DIR)/docker-compose.config.yml -f $(COMPOSE_DIR)/docker-compose.mcp.yml
# dev = core + angular dev server, ws-events seeder, go-toolbox
DEV_FILES  := $(CORE_FILES) -f $(COMPOSE_DIR)/docker-compose.toolbox.yml -f $(COMPOSE_DIR)/docker-compose.dev.yml

# --project-directory pins relative paths (volumes, build context, .env) to the repo
# root regardless of where the -f files live — run `make` from repo root.
# override with `make COMPOSE="docker compose --project-directory . $(CORE_FILES)" <target>`
COMPOSE := docker compose --project-directory . $(DEV_FILES) -p $(PROJECT)

.DEFAULT_GOAL  := help

# ─── help ────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── lifecycle ───────────────────────────────────────────────────────────────

.PHONY: up
up: pdm-gen-openapi-client ## Start the full dev stack (core + toolbox + dev web ui)
	$(COMPOSE) up -d --scale $(PDM_FORECAST_WORKER)=$(PDM_FORECAST_WORKERS) --scale $(PDM_ANOMALY_WORKER)=$(PDM_ANOMALY_WORKERS)

up-recreate: pdm-gen-openapi-client maybe-reset-pdm-state ## Recreate dev stack and reset PdM Kafka/Redis state by default
	$(COMPOSE) up -d --force-recreate --scale $(PDM_FORECAST_WORKER)=$(PDM_FORECAST_WORKERS) --scale $(PDM_ANOMALY_WORKER)=$(PDM_ANOMALY_WORKERS)

.PHONY: make-recreate
make-recreate: up-recreate ## Alias for up-recreate

.PHONY: maybe-reset-pdm-state
maybe-reset-pdm-state:
	@if [ "$(RESET_PDM_STATE_ON_RECREATE)" = "true" ]; then \
		$(MAKE) reset-pdm-state; \
	else \
		echo "Skipping PdM state reset; RESET_PDM_STATE_ON_RECREATE=$(RESET_PDM_STATE_ON_RECREATE)"; \
	fi

.PHONY: reset-pdm-state
reset-pdm-state: reset-pdm-kafka reset-pdm-redis ## Clear PdM Kafka topics and Redis runtime state

.PHONY: reset-pdm-kafka
reset-pdm-kafka: ## Delete and recreate PdM Kafka topics
	$(COMPOSE) up -d --wait kafka
	@set -eu; \
	for spec in "kafka kafka:9092"; do \
		svc=$$(echo $$spec | awk '{print $$1}'); \
		bootstrap=$$(echo $$spec | awk '{print $$2}'); \
		if [ -n "$$($(COMPOSE) ps -q $$svc 2>/dev/null)" ]; then \
			echo "Resetting PdM Kafka topics on $$svc ($$bootstrap)"; \
			for topic in $(PDM_KAFKA_TOPICS); do \
				$(COMPOSE) exec -T $$svc /opt/kafka/bin/kafka-topics.sh --bootstrap-server $$bootstrap --delete --topic $$topic >/dev/null 2>&1 || true; \
			done; \
			sleep 2; \
			$(COMPOSE) exec -T $$svc /opt/kafka/bin/kafka-topics.sh --bootstrap-server $$bootstrap --create --if-not-exists --topic pdm-commands --partitions $(PDM_KAFKA_PARTITIONS) --replication-factor 1; \
			$(COMPOSE) exec -T $$svc /opt/kafka/bin/kafka-topics.sh --bootstrap-server $$bootstrap --create --if-not-exists --topic pdm-events --partitions $(PDM_KAFKA_PARTITIONS) --replication-factor 1; \
			$(COMPOSE) exec -T $$svc /opt/kafka/bin/kafka-topics.sh --bootstrap-server $$bootstrap --create --if-not-exists --topic pdm-job-state --partitions $(PDM_KAFKA_PARTITIONS) --replication-factor 1 --config cleanup.policy=compact; \
		fi; \
	done

.PHONY: reset-pdm-redis
reset-pdm-redis: ## Clear PdM Redis job/log/prediction keys
	$(COMPOSE) up -d redis
	@for pattern in 'job:*' 'logs:*' 'predictions:*'; do \
		echo "Deleting Redis keys matching $$pattern"; \
		$(COMPOSE) exec -T redis sh -lc "redis-cli --scan --pattern '$$pattern' | xargs -r redis-cli del"; \
	done

.PHONY: up-ui
up-ui: ## Start the full dev stack (core + toolbox + dev web ui)
	$(COMPOSE) up -d $(WEB_SERVICE)

.PHONY: up-prod
up-prod: pdm-gen-openapi-client ## Start prod-only stack (core: tb, quarkus, pdm workers, config-api)
	docker compose --project-directory . $(CORE_FILES) -p $(PROJECT) up -d --scale $(PDM_FORECAST_WORKER)=$(PDM_FORECAST_WORKERS) --scale $(PDM_ANOMALY_WORKER)=$(PDM_ANOMALY_WORKERS)

.PHONY: down
down: ## Stop and remove containers (keep volumes)
	$(COMPOSE) down

.PHONY: destroy
destroy: ## Stop and remove containers AND volumes
	$(COMPOSE) down -v

.PHONY: restart
restart: ## Restart all services
	$(COMPOSE) restart

.PHONY: restart-tb
restart-tb: ## Restart only thingsboard
	$(COMPOSE) restart $(TB_SERVICE)

.PHONY: restart-web
restart-web: ## Restart only tb-web-ui-dev
	$(COMPOSE) restart $(WEB_SERVICE)

.PHONY: restart-pdm-workers
restart-pdm-workers: ## Restart predictive-maintenance Kafka workers
	$(COMPOSE) restart $(PDM_FORECAST_WORKER) $(PDM_ANOMALY_WORKER)

# ─── install / seed ──────────────────────────────────────────────────────────

.PHONY: db-up
db-up: ## Start postgres and wait until pg_isready passes
	$(COMPOSE) up -d $(POSTGRES)
	@until $(COMPOSE) exec $(POSTGRES) pg_isready -U postgres -d thingsboard; do \
		echo "waiting for postgres..."; \
		sleep 2; \
	done

install-cassandra: export COMPOSE_PROFILES = cassandra
install-cassandra: export DATABASE_TS_TYPE = cassandra
install-cassandra: export DATABASE_TS_LATEST_TYPE = cassandra

.PHONY: install-cassandra
install-cassandra: db-up ## Run TB schema installation with Cassandra enabled as the time-series backend (sets COMPOSE_PROFILES, DATABASE_TS_TYPE, DATABASE_TS_LATEST_TYPE=cassandra for this invocation)
	$(COMPOSE) up -d $(CASSANDRA_SERVICE)
	@cid="$$($(COMPOSE) ps -q $(CASSANDRA_SERVICE))"; \
	if [ -z "$$cid" ]; then echo "$(CASSANDRA_SERVICE) is not running"; exit 1; fi; \
	for i in $$(seq 1 60); do \
		status="$$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$$cid")"; \
		echo "$(CASSANDRA_SERVICE) health: $$status"; \
		if [ "$$status" = "healthy" ]; then break; fi; \
		if [ "$$status" = "exited" ] || [ "$$status" = "dead" ]; then $(COMPOSE) logs --tail=120 $(CASSANDRA_SERVICE); exit 1; fi; \
		if [ "$$i" = "60" ]; then echo "$(CASSANDRA_SERVICE) never became healthy"; $(COMPOSE) logs --tail=120 $(CASSANDRA_SERVICE); exit 1; fi; \
		sleep 3; \
	done
	$(COMPOSE) run --rm --no-deps \
		-e INSTALL_TB=true \
		$(TB_SERVICE)

up-cassandra: export COMPOSE_PROFILES = cassandra
up-cassandra: export DATABASE_TS_TYPE = cassandra
up-cassandra: export DATABASE_TS_LATEST_TYPE = cassandra

.PHONY: up-cassandra
# Attention: migrating database from postgres is not tested and may cause Undefined Behavior.
up-cassandra: pdm-gen-openapi-client ## Start the full dev stack with Cassandra enabled as the time-series backend. Auto-installs the Cassandra schema on first run if the thingsboard keyspace doesn't exist yet.
	$(COMPOSE) up -d $(CASSANDRA_SERVICE)
	@cid="$$($(COMPOSE) ps -q $(CASSANDRA_SERVICE))"; \
	if [ -z "$$cid" ]; then echo "$(CASSANDRA_SERVICE) is not running"; exit 1; fi; \
	for i in $$(seq 1 60); do \
		status="$$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$$cid")"; \
		echo "$(CASSANDRA_SERVICE) health: $$status"; \
		if [ "$$status" = "healthy" ]; then break; fi; \
		if [ "$$status" = "exited" ] || [ "$$status" = "dead" ]; then $(COMPOSE) logs --tail=120 $(CASSANDRA_SERVICE); exit 1; fi; \
		if [ "$$i" = "60" ]; then echo "$(CASSANDRA_SERVICE) never became healthy"; $(COMPOSE) logs --tail=120 $(CASSANDRA_SERVICE); exit 1; fi; \
		sleep 3; \
	done
	@if $(COMPOSE) exec -T $(CASSANDRA_SERVICE) cqlsh -e "DESCRIBE KEYSPACE thingsboard" >/dev/null 2>&1; then \
		echo "thingsboard keyspace already present, skipping install"; \
	else \
		echo "thingsboard keyspace not found — running install-cassandra first"; \
		exit 1; \
	fi
	$(COMPOSE) up -d --scale $(PDM_FORECAST_WORKER)=$(PDM_FORECAST_WORKERS) --scale $(PDM_ANOMALY_WORKER)=$(PDM_ANOMALY_WORKERS)

.PHONY: install
install: db-up ## Run TB schema installation (INSTALL_TB=true)
	$(COMPOSE) run --rm --no-deps \
		-e INSTALL_TB=true \
		$(TB_SERVICE)

.PHONY: install-demo
install-demo: db-up ## Run TB schema installation + demo data (LOAD_DEMO=true)
	$(COMPOSE) run --rm --no-deps \
		-e INSTALL_TB=true \
		-e LOAD_DEMO=true \
		-e INSTALL_DATA_DIR=/usr/share/thingsboard/data \
		$(TB_SERVICE)

.PHONY: upgrade-db
upgrade-db: destroy db-up ## Run TB database upgrade (UPGRADE_DB=true)
	$(COMPOSE) build $(TB_SERVICE)
	$(COMPOSE) run --rm --no-deps \
		-e UPGRADE_TB=true \
		-e FROM_VERSION=$(TB_PREV_VERSION) \
		-e INSTALL_DATA_DIR=/usr/share/thingsboard/data \
		$(TB_SERVICE)

# ─── build ───────────────────────────────────────────────────────────────────

.PHONY: build
build: ## Build / rebuild all images
	$(COMPOSE) build

.PHONY: build-tb
build-tb: ## Build / rebuild thingsboard image only
	$(COMPOSE) build $(TB_SERVICE)

.PHONY: build-mcp
build-mcp: ## Build / rebuild thingsboard-mcp image only
	$(COMPOSE) build $(MCP_SERVICE)

.PHONY: build-tb-quarkus
build-tb-quarkus: tb-quarkus-build ## Build / rebuild tb-quarkus image only

.PHONY: build-web
build-web: ## Build / rebuild tb-web-ui-dev image only
	$(COMPOSE) build $(WEB_SERVICE)

.PHONY: build-web-prod
build-web-prod: ## Build / rebuild the production tb-web-ui image
	docker compose --project-directory . $(CORE_FILES) build $(WEB_PROD)

.PHONY: pull
pull: ## Pull latest base images
	$(COMPOSE) pull

.PHONY: agent-test
agent-test: ## Run pdm_agent eval tests inside the ai-agent service (brings up its deps first)
	$(COMPOSE) build $(AI_AGENT)
	$(COMPOSE) up -d $(AI_AGENT)
	$(COMPOSE) exec -T $(AI_AGENT) sh scripts/run-agent-evals.sh

# ─── logs ────────────────────────────────────────────────────────────────────

.PHONY: logs
logs: ## Tail logs for all services
	$(COMPOSE) logs -f

.PHONY: logs-tb
logs-tb: ## Tail thingsboard logs
	$(COMPOSE) logs -f $(TB_SERVICE)

.PHONY: logs-web
logs-web: ## Tail tb-web-ui-dev logs
	$(COMPOSE) logs -f $(WEB_SERVICE)

.PHONY: logs-pg
logs-pg: ## Tail postgres logs
	$(COMPOSE) logs -f $(POSTGRES)

.PHONY: logs-pdm-workers
logs-pdm-workers: ## Tail predictive-maintenance Kafka worker logs
	$(COMPOSE) logs -f $(PDM_FORECAST_WORKER) $(PDM_ANOMALY_WORKER)

.PHONY: logs-config
logs-config: ## Tail config-api logs
	$(COMPOSE) logs -f $(CONFIG_SERVICE)

.PHONY: logs-tb-quarkus
logs-tb-quarkus: ## Tail tb-quarkus logs
	$(COMPOSE) logs -f $(TB_QUARKUS)

.PHONY: logs-tb-quarkus-dev
logs-tb-quarkus-dev: ## Tail tb-quarkus dev logs
	$(COMPOSE) logs -f $(TB_QUARKUS_DEV)

.PHONY: lazydocker
lazydocker: ## Launch lazydocker pre-wired to the split compose files (project-local config, doesn't touch your global lazydocker config)
	XDG_CONFIG_HOME="$(CURDIR)/.lazydocker" lazydocker -p $(PROJECT)

generate-kpods:
	# check if directory command exists
	@command -v kompose >/dev/null 2>&1 || { echo >&2 "kompose is required but not installed. Please install kompose to use this target."; exit 1; }
	# create directory if it doesn't exist
	@mkdir -p k8s
	# copy .env file to docker-compose directory
	@cp .env docker-compose/.env
	cd k8s && kompose convert \
		-f ../docker-compose/docker-compose.base.yml \
		-f ../docker-compose/docker-compose.db.yml \
		-f ../docker-compose/docker-compose.tb.yml \
		-f ../docker-compose/docker-compose.gateway.yml \
		-f ../docker-compose/docker-compose.web.yml \
		-f ../docker-compose/docker-compose.model.yml \
		-f ../docker-compose/docker-compose.config.yml \
		-f ../docker-compose/docker-compose.mcp.yml
	@rm docker-compose/.env

# ─── status ──────────────────────────────────────────────────────────────────

.PHONY: ps
ps: ## Show container status
	$(COMPOSE) ps

.PHONY: config
config: ## Print the fully merged compose config
	$(COMPOSE) config

.PHONY: health
health: ## Show healthcheck status for all containers
	@docker inspect --format '{{.Name}}  {{.State.Health.Status}}' \
		$$($(COMPOSE) ps -q) 2>/dev/null \
		|| echo "No containers running"

# ─── shell access ────────────────────────────────────────────────────────────

.PHONY: shell-tb
shell-tb: ## Open a shell in thingsboard
	$(COMPOSE) exec $(TB_SERVICE) bash

.PHONY: shell-web
shell-web: ## Open a shell in tb-web-ui-dev
	$(COMPOSE) exec $(WEB_SERVICE) bash

.PHONY: shell-pg
shell-pg: ## Open a psql shell in postgres
	$(COMPOSE) exec $(POSTGRES) psql -U postgres -d thingsboard

.PHONY: shell-tb-quarkus
shell-tb-quarkus: ## Open a shell in tb-quarkus
	$(COMPOSE) exec $(TB_QUARKUS) sh

.PHONY: shell-tb-quarkus-dev
shell-tb-quarkus-dev: ## Open a shell in tb-quarkus dev
	$(COMPOSE) exec $(TB_QUARKUS_DEV) bash

# ─── tb-quarkus ──────────────────────────────────────────────────────────────

.PHONY: tb-quarkus-cache
tb-quarkus-cache: ## Create tb-quarkus host cache directory
	mkdir -p $(TB_QUARKUS_CACHE_DIR)/gradle $(TB_QUARKUS_CACHE_DIR)/runtime

.PHONY: tb-quarkus-preflight
tb-quarkus-preflight: tb-quarkus-cache ## Check tb-quarkus Docker build prerequisites
	@test -d tb-quarkus/src/main/docker || (echo "Missing tb-quarkus Dockerfiles"; exit 1)
	@test -f tb-quarkus/gradlew || (echo "Missing tb-quarkus Gradle wrapper"; exit 1)

.PHONY: tb-quarkus-build
tb-quarkus-build: tb-quarkus-preflight ## Build tb-quarkus Docker image
	TB_QUARKUS_DOCKERFILE=$(TB_QUARKUS_DOCKERFILE) $(COMPOSE) build $(TB_QUARKUS)

.PHONY: tb-quarkus-build-native
tb-quarkus-build-native: ## Build tb-quarkus native Docker image
	$(MAKE) TB_QUARKUS_DOCKERFILE=src/main/docker/Dockerfile.native tb-quarkus-build

.PHONY: tb-quarkus-up
tb-quarkus-up: tb-quarkus-cache ## Start tb-quarkus without recreating shared stack dependencies
	$(COMPOSE) up -d --no-deps $(TB_QUARKUS)

.PHONY: tb-quarkus-up-with-deps
tb-quarkus-up-with-deps: tb-quarkus-cache ## Start postgres and tb-quarkus
	$(COMPOSE) up -d $(POSTGRES) $(TB_QUARKUS)

.PHONY: tb-quarkus-wait
tb-quarkus-wait: ## Wait until tb-quarkus is healthy
	@cid="$$($(COMPOSE) ps -q $(TB_QUARKUS))"; \
	if [ -z "$$cid" ]; then echo "$(TB_QUARKUS) is not running"; exit 1; fi; \
	for i in $$(seq 1 60); do \
		status="$$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$$cid")"; \
		echo "$(TB_QUARKUS) health: $$status"; \
		if [ "$$status" = "healthy" ]; then exit 0; fi; \
		if [ "$$status" = "exited" ] || [ "$$status" = "dead" ]; then $(COMPOSE) logs --tail=120 $(TB_QUARKUS); exit 1; fi; \
		sleep 2; \
	done; \
	$(COMPOSE) logs --tail=120 $(TB_QUARKUS); \
	exit 1

.PHONY: tb-quarkus-curl
tb-quarkus-curl: ## Curl tb-quarkus smoke endpoint
	curl -fsS "$(TB_QUARKUS_SMOKE_URL)"

.PHONY: tb-quarkus-smoke
tb-quarkus-smoke: tb-quarkus-build tb-quarkus-up tb-quarkus-wait tb-quarkus-curl ## Build, run, wait, and curl tb-quarkus

.PHONY: tb-quarkus-dev-cache
tb-quarkus-dev-cache: ## Create tb-quarkus-dev host cache directory
	mkdir -p $(TB_QUARKUS_CACHE_DEV_DIR)/gradle $(TB_QUARKUS_CACHE_DEV_DIR)/runtime

.PHONY: tb-quarkus-dev-up
tb-quarkus-dev-up: tb-quarkus-dev-cache ## Start tb-quarkus dev container with mounted source
	$(COMPOSE) up -d --no-deps $(TB_QUARKUS_DEV)

.PHONY: tb-quarkus-dev-up-with-deps
tb-quarkus-dev-up-with-deps: tb-quarkus-dev-cache ## Start postgres and tb-quarkus dev container
	$(COMPOSE) up -d $(POSTGRES) $(TB_QUARKUS_DEV)

.PHONY: tb-quarkus-dev-wait
tb-quarkus-dev-wait: ## Wait until tb-quarkus dev is healthy
	@cid="$$($(COMPOSE) ps -q $(TB_QUARKUS_DEV))"; \
	if [ -z "$$cid" ]; then echo "$(TB_QUARKUS_DEV) is not running"; exit 1; fi; \
	for i in $$(seq 1 60); do \
		status="$$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$$cid")"; \
		echo "$(TB_QUARKUS_DEV) health: $$status"; \
		if [ "$$status" = "healthy" ]; then exit 0; fi; \
		if [ "$$status" = "exited" ] || [ "$$status" = "dead" ]; then $(COMPOSE) logs --tail=120 $(TB_QUARKUS_DEV); exit 1; fi; \
		sleep 2; \
	done; \
	$(COMPOSE) logs --tail=120 $(TB_QUARKUS_DEV); \
	exit 1

.PHONY: tb-quarkus-dev-curl
tb-quarkus-dev-curl: ## Curl tb-quarkus dev smoke endpoint
	curl -fsS "$(TB_QUARKUS_DEV_SMOKE_URL)"

.PHONY: tb-quarkus-dev-smoke
tb-quarkus-dev-smoke: tb-quarkus-dev-up tb-quarkus-dev-wait tb-quarkus-dev-curl ## Run, wait, and curl tb-quarkus dev

.PHONY: tb-quarkus-gen-openapi
tb-quarkus-gen-openapi:
	$(COMPOSE) run --rm $(TB_QUARKUS_DEV) ./gradlew openApiGenerate

.PHONY: pdm-gen-openapi-client
pdm-gen-openapi-client: ## Generate ignored Python Quarkus API client for PdM workers
	cd tb-quarkus/gateway && ./gradlew generatePythonApiClient

# ─── cleanup ─────────────────────────────────────────────────────────────────

.PHONY: prune
prune: ## Remove stopped containers and dangling images
	docker system prune -f

# ── Add to your root Makefile ────────────────────────────────────────────────

# Rebuild the JS engine when Dark Reader vendor files change.
# Run once, commit engine.js; only re-run when modifying go-toolbox/cmd/darktheme/engine/
.PHONY: darktheme-engine
darktheme-engine:
	cd go-toolbox/cmd/darktheme && npm ci && npm run build

# Run dark theme generation across ui-ngx SCSS source.
# Requires: node in PATH inside the container (darktheme image is node:22-alpine based)
.PHONY: darktheme
darktheme:
# 	build the image
	$(COMPOSE) build go-toolbox-darktheme
	$(COMPOSE) run --rm go-toolbox-darktheme \
		--path /ui-ngx/src \
		--selector .dark-theme

# ─── logs (add alongside logs-config) ────────────────────────────────────────
.PHONY: logs-mcp
logs-mcp: ## Tail thingsboard-mcp (SSE) logs
	$(COMPOSE) logs -f $(MCP_SERVICE)

.PHONY: ai-agent-chat
ai-agent-chat: ## Send Q="..." to ai-agent on localhost:8300 using qwen2.5:7b-instruct
	@Q="$${Q:-}" MODEL="$${MODEL:-qwen2.5:7b-instruct}" python3 -c 'import json, os, sys, urllib.request; query = os.environ.get("Q", "").strip(); model = os.environ.get("MODEL", "qwen2.5:7b-instruct"); query or sys.exit("Set Q=... to query ai-agent."); payload = {"message": query, "model": model}; request = urllib.request.Request("http://localhost:8300/chat", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}); response = urllib.request.urlopen(request, timeout=240); data = json.load(response); response.close(); print(data.get("answer") or "")'

.PHONY: ai-agent-stdio
ai-agent-stdio: ## Interactive ai-agent conversation over stdin/stdout with one session id
	@docker compose --project-directory . -f docker-compose/docker-compose.base.yml -f docker-compose/docker-compose.db.yml -f docker-compose/docker-compose.tb.yml -f docker-compose/docker-compose.gateway.yml -f docker-compose/docker-compose.web.yml -f docker-compose/docker-compose.model.yml -f docker-compose/docker-compose.config.yml -f docker-compose/docker-compose.mcp.yml exec -T ai-agent ai-agent repl

.PHONY: ai-agent-repl
ai-agent-repl: ai-agent-stdio ## Alias for the interactive ai-agent conversation target

# ─── lifecycle ───────────────────────────────────────────────────────────────
.PHONY: restart-mcp
restart-mcp: ## Restart only thingsboard-mcp
	$(COMPOSE) restart $(MCP_SERVICE)

# ─── shell access ────────────────────────────────────────────────────────────
.PHONY: shell-mcp
shell-mcp: ## Open a shell in thingsboard-mcp
	$(COMPOSE) exec $(MCP_SERVICE) sh

.PHONY: pause unpause
pause: ## Pause all containers
	$(COMPOSE) pause

unpause: ## Unpause all containers
	$(COMPOSE) unpause

# ─── assetopsbench ───────────────────────────────────────────────────────────
# All targets delegate to assetopsbench/Makefile via $(MAKE) -C.
# Override variables at the root level and they are forwarded automatically,
# e.g.:  make assetopsbench-pull OLLAMA_MODEL=llama3.2:3b
#        make assetopsbench-ask  AGENT=deep-agent MODEL_ID=litellm_proxy/llama3.2:3b
#        make assetopsbench-tui-chat Q="List all failure modes of asset Chiller"
 
AGENTS := $(MAKE) -C assetopsbench --no-print-directory
 
.PHONY: assetopsbench-up assetopsbench-down assetopsbench-stop \
        assetopsbench-pause assetopsbench-unpause assetopsbench-ps \
        assetopsbench-pull assetopsbench-ask assetopsbench-examples \
        assetopsbench-smoke assetopsbench-sync \
        assetopsbench-tui-build assetopsbench-tui-install assetopsbench-tui \
        assetopsbench-tui-chat assetopsbench-tui-stack-up assetopsbench-tui-stack-ps \
        assetopsbench-tui-models assetopsbench-tui-pull assetopsbench-tui-smoke \
        assetopsbench-tui-init
 
assetopsbench-up: ## [agents] Start the assetopsbench stack
	@$(AGENTS) up
 
assetopsbench-down: ## [agents] Stop the assetopsbench stack
	@$(AGENTS) down
 
assetopsbench-stop: ## [agents] Stop assetopsbench containers
	@$(AGENTS) stop
 
assetopsbench-pause: ## [agents] Pause assetopsbench containers
	@$(AGENTS) pause
 
assetopsbench-unpause: ## [agents] Unpause assetopsbench containers
	@$(AGENTS) unpause
 
assetopsbench-ps: ## [agents] Show assetopsbench container status
	@$(AGENTS) ps
 
assetopsbench-pull: ## [agents] Pull Ollama model (OLLAMA_MODEL=...)
	@$(AGENTS) pull
 
assetopsbench-ask: ## [agents] Prompt for a query and run it (AGENT=... MODEL_ID=... AGENT_FLAGS=...)
	@$(AGENTS) ask
 
assetopsbench-ask-%: ## [agents] Run a named agent directly, e.g. assetopsbench-ask-plan-execute
	@$(AGENTS) ask-$*
 
assetopsbench-examples: ## [agents] Print canned example queries
	@$(AGENTS) examples
 
assetopsbench-smoke: ## [agents] Ping the LiteLLM proxy health endpoint
	@$(AGENTS) smoke
 
assetopsbench-sync: ## [agents] Sync uv deps on host (dev only)
	@$(AGENTS) sync
 
assetopsbench-tui-build: ## [agents] Build the assetops TUI binary
	@$(AGENTS) tui-build
 
assetopsbench-tui-install: ## [agents] Install assetops TUI to $$GOPATH/bin
	@$(AGENTS) tui-install
 
assetopsbench-tui: ## [agents] Launch the full assetops TUI
	@$(AGENTS) tui
 
assetopsbench-tui-chat: ## [agents] Streaming chat without TUI (Q="your query")
	@$(AGENTS) tui-chat
 
assetopsbench-tui-models: ## [agents] List installed Ollama models
	@$(AGENTS) tui-models
 
assetopsbench-tui-pull: ## [agents] Pull an Ollama model with progress bar (OLLAMA_MODEL=...)
	@$(AGENTS) tui-pull
 
assetopsbench-tui-stack-up: ## [agents] Start stack via TUI CLI
	@$(AGENTS) tui-stack-up
 
assetopsbench-tui-stack-ps: ## [agents] Stack status via TUI CLI
	@$(AGENTS) tui-stack-ps
 
assetopsbench-tui-smoke: ## [agents] Ping LiteLLM proxy via TUI CLI
	@$(AGENTS) tui-smoke
 
assetopsbench-tui-init: ## [agents] Write default TUI config file
	@$(AGENTS) tui-init

tb-quarkus-dev:
	@cd tb-quarkus/gateway && ./gradlew quarkusDev