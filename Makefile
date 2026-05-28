# Use docker-compose to build and manage services
COMPOSE=docker compose

# Default: compile all modules (Java + rebuild all Docker images)
# all: compile-all (old make target)
all: up
	@echo "✅ All services are up and running!"

# Compile all modules: Java code + rebuild all Docker services
compile-all: compile build-all
	@echo "✅ All modules compiled successfully!"

backup:
	-cp ./application/target/thingsboard-3.7.0-boot.jar ../thingsboard-3.7.0-boot.jar

clean:
	rm -rf **/target
	rm -rf ./ui-ngx/.angular

clean-mvn:
	$(COMPOSE) run --rm thingsboard mvn clean

fclean: clean
	rm -rf ./ui-ngx/node_modules/

# Compile Java code using Maven with docker run (12GB memory for UI build)
compile:
	docker run --rm \
		--memory=12g --memory-swap=12g \
		--cpus=4 \
		-v $(PWD):/app \
		-v $(PWD)/../thingsboard_m2_cache:/root/.m2 \
		-v $(PWD)/../thingsboard_npm_cache:/root/.npm \
		-v $(PWD)/../thingsboard_gradle_cache:/root/.gradle \
		-w /app \
		-e NODE_OPTIONS="--max-old-space-size=8192" \
		--network thingsboard_thingsboard \
		thingsboard-thingsboard \
		mvn install -U -DskipTests

# Compile with debug output
compile-debug:
	docker run --rm \
		--memory=12g --memory-swap=12g \
		--cpus=4 \
		-v $(PWD):/app \
		-v $(PWD)/../thingsboard_m2_cache:/root/.m2 \
		-v $(PWD)/../thingsboard_npm_cache:/root/.npm \
		-v $(PWD)/../thingsboard_gradle_cache:/root/.gradle \
		-w /app \
		-e NODE_OPTIONS="--max-old-space-size=8192" \
		--network thingsboard_thingsboard \
		thingsboard-thingsboard \
		mvn -X install -U -DskipTests

# Build all Docker services
build-all:
	$(COMPOSE) build

# Build only thingsboard service
build-thingsboard:
	$(COMPOSE) build thingsboard

# Build only model service
build-model:
	$(COMPOSE) build model

# Build only ui-ngx service
build-ui:
	$(COMPOSE) build ui-ngx

# Rebuild thingsboard and restart
rebuild-thingsboard:
	$(COMPOSE) build thingsboard
	$(COMPOSE) up -d thingsboard

# Rebuild model and restart
rebuild-model:
	$(COMPOSE) build model
	$(COMPOSE) up -d model

# Rebuild ui and restart
rebuild-ui:
	$(COMPOSE) build ui-ngx
	$(COMPOSE) up -d ui-ngx

# Start microservices (default)
up:
	cd docker && ./docker-start-services.sh

# Stop microservices (default)
down:
	cd docker && ./docker-stop-services.sh

# Start monolith services
up-monolith:
	$(COMPOSE) up -d

# Stop monolith services
down-monolith:
	$(COMPOSE) down

# View logs
logs:
	$(COMPOSE) logs -f

# View thingsboard logs
logs-thingsboard:
	$(COMPOSE) logs -f thingsboard

# View model logs
logs-model:
	$(COMPOSE) logs -f model

# View ui logs
logs-ui:
	$(COMPOSE) logs -f ui-ngx

# Restart all services
restart:
	$(COMPOSE) restart

# Restart thingsboard
restart-thingsboard:
	$(COMPOSE) restart thingsboard

# Restart model
restart-model:
	$(COMPOSE) restart model

# Restart ui
restart-ui:
	$(COMPOSE) restart ui-ngx

# Docker microservices installation
install:
	cd docker && ./docker-install-tb.sh

.PHONY: all compile-all backup clean clean-mvn fclean compile compile-debug build-all build-thingsboard build-model build-ui rebuild-thingsboard rebuild-model rebuild-ui up down up-monolith down-monolith logs logs-thingsboard logs-model logs-ui restart restart-thingsboard restart-model restart-ui install