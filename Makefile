PROJECT         := thingsboard-dev
TB_SERVICE      := thingsboard
WEB_SERVICE     := tb-web-ui-dev
WEB_PROD        := tb-web-ui
MODEL_SERVICE   := model
CONFIG_SERVICE  := config-api
MCP_SERVICE     := thingsboard-mcp
POSTGRES        := postgres
TB_PREV_VERSION ?= 4.2.2.2

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
COMPOSE := docker compose --project-directory . $(DEV_FILES)

.DEFAULT_GOAL  := help

# ─── help ────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── lifecycle ───────────────────────────────────────────────────────────────

.PHONY: up
up: ## Start the full dev stack (core + toolbox + dev web ui)
	$(COMPOSE) up -d

.PHONY: up-ui
up-ui: ## Start the full dev stack (core + toolbox + dev web ui)
	$(COMPOSE) up -d $(WEB_SERVICE)

.PHONY: up-prod
up-prod: ## Start prod-only stack (core: tb, model, config-api)
	docker compose --project-directory . $(CORE_FILES) up -d

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

.PHONY: restart-model
restart-model: ## Restart only the predictive-maintenance model service
	$(COMPOSE) restart $(MODEL_SERVICE)

# ─── install / seed ──────────────────────────────────────────────────────────

.PHONY: db-up
db-up: ## Start postgres and wait until pg_isready passes
	$(COMPOSE) up -d $(POSTGRES)
	@until $(COMPOSE) exec $(POSTGRES) pg_isready -U postgres -d thingsboard; do \
		echo "waiting for postgres..."; \
		sleep 2; \
	done

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

.PHONY: build-web
build-web: ## Build / rebuild tb-web-ui-dev image only
	$(COMPOSE) build $(WEB_SERVICE)

.PHONY: build-web-prod
build-web-prod: ## Build / rebuild the production tb-web-ui image
	docker compose --project-directory . $(CORE_FILES) build $(WEB_PROD)

.PHONY: pull
pull: ## Pull latest base images
	$(COMPOSE) pull

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

.PHONY: logs-model
logs-model: ## Tail predictive-maintenance model logs
	$(COMPOSE) logs -f $(MODEL_SERVICE)

.PHONY: logs-config
logs-config: ## Tail config-api logs
	$(COMPOSE) logs -f $(CONFIG_SERVICE)

.PHONY: lazydocker
lazydocker: ## Launch lazydocker pre-wired to the split compose files (project-local config, doesn't touch your global lazydocker config)
	XDG_CONFIG_HOME="$(CURDIR)/.lazydocker" lazydocker -p tb-lts-monolith-dev

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

.PHONY: shell-model
shell-model: ## Open a shell in the model service
	$(COMPOSE) exec $(MODEL_SERVICE) bash

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

# ─── lifecycle (add alongside restart-model) ─────────────────────────────────
.PHONY: restart-mcp
restart-mcp: ## Restart only thingsboard-mcp
	$(COMPOSE) restart $(MCP_SERVICE)

# ─── shell access (add alongside shell-model) ────────────────────────────────
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