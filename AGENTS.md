# Repository Guidelines

## Project Structure & Module Organization

This repo treats ThingsBoard as an upstream containerized dependency, not code to build or modify. The active project code is the Angular UI in `ui-ngx/`, the Quarkus gateway in `tb-quarkus/gateway/`, PdM workers in `predictive-maintenance/`, MCP services in `thingsboard-mcp/` and `pandas-mcp-server/`, and agent tooling in `ai-agent/` and `assetopsbench/`. Contracts live in `api-specs/openapi.yaml` (bundled output) and `api-specs/asyncapi.yaml`. The OpenAPI source is split into `api-specs/openapi/` with individual schema, parameter, and path files linked via `$ref`; `npx @redocly/cli bundle` reassembles them into the single file consumers parse. ThingsBoard Java/Python API clients are generated from OpenAPI or pulled from GitHub as dependencies.

## Local Runtime & Compose Workflow

Use the root `Makefile` as the entrypoint. It merges split files from `docker-compose/`: `CORE_FILES` run the production-like stack; `DEV_FILES` add dev UI, Quarkus dev, websocket seeding, and toolbox services. Run from the repo root.

- `make up`: start the full dev stack: upstream `thingsboard` image, Postgres, Redis, Kafka, schema registry, Quarkus, web UI, model workers, config API, MCP, and toolbox.
- `make up-prod`: start only the core production-like stack.
- `make install-demo`: initialize schema and demo data.
- `make upgrade-db`: run the ThingsBoard database upgrade flow using `TB_PREV_VERSION`.
- `make ps`, `make health`, `make config`: inspect containers and merged config.
- `make logs-tb`, `make logs-web`, `make logs-tb-quarkus`, `make logs-pdm-workers`, `make logs-mcp`: follow logs.
- `make up-recreate`: recreate dev and reset PdM Kafka/Redis state.
- `make reset-pdm-state`: clear PdM Kafka topics and Redis runtime state; run this when rebuilding or recreating backend/frontend containers to keep tests clean and reproducible.

Ports: ThingsBoard `8080`, Angular dev UI `4200`, web UI `8090`, Quarkus JVM `8083`, Quarkus dev `8082`, Postgres `5431`, config API `9000`, MCP `8201`.

## Worktree Workflow for PR Testing

Use `wt-*` Makefile targets to test PR branches in isolated Docker environments. Each worktree gets its own postgres data, redis, kafka, and build caches. Worktrees share host ports with the main stack — **stop it before running a worktree**. All `wt-*` targets run from the main repo dir.

- `make wt-setup BRANCH=name`: create worktree, isolated volumes, copy tb-config, restore postgres from backup.
- `make wt-up BRANCH=name` / `make wt-up-prod BRANCH=name`: start full dev or prod-only stack.
- `make wt-down BRANCH=name` / `make wt-destroy BRANCH=name`: stop containers / stop + remove volumes.
- `make wt-install BRANCH=name` / `make wt-install-demo BRANCH=name`: seed DB schema / demo data.
- `make wt-install-restore BRANCH=name`: restore postgres from backup.
- `make wt-switch BRANCH=name PR=42`: switch worktree to a different PR.
- `make wt-teardown BRANCH=name`: remove worktree, branch, volumes, and /etc/hosts entry.
- `make wt-list`, `make wt-hosts`, `make wt-ps`, `make wt-logs`: inspect worktrees.

Worktrees live at `../thingsboard-wt-<branch>/`, isolated volumes at `.worktrees/<branch>/`. Domains are `<branch>.localhost` (add to `/etc/hosts` with `make wt-hosts`). Compose files resolve from the main repo via `--project-directory $(CURDIR)` — the worktree override remaps bind-mounts for data isolation. Teardown uses an alpine container to force-remove root-owned Docker artifacts. Postgres 18 init restart is handled with a `SELECT 1` readiness check.

## Schema-First API Workflow

Treat `api-specs/` as the source of truth. Edit the split files under `api-specs/openapi/` (schemas, paths, parameters, responses) before REST changes and `api-specs/asyncapi.yaml` before event model changes. Run `make bundle-openapi` to reassemble the split files into `api-specs/openapi.yaml`, or any dependent target (`make up`, `make build`) will do it automatically. Then regenerate: `cd ui-ngx && yarn generate:api` for Angular, or `make tb-quarkus-gen-openapi` / `cd tb-quarkus/gateway && ./gradlew openApiGenerate` for Quarkus. Implement or override generated Quarkus interfaces under `tb-quarkus/gateway/src/main/java/...`; do not bypass OpenAPI with standalone public endpoints.

## Database per Service

Each service owns its own database schema. Any action that adds a new service database integration must define its schema (tables, columns, types, indexes) before writing application code. Use versioned migration scripts in the service module (e.g. `tb-quarkus/gateway/src/main/resources/db/migration/`). Every schema change must be a versioned migration and must not use the `default` schema.

## ThingsBoard Upgrade Workflow

Do not build ThingsBoard from this repo. Update the upstream image version through `.env` variables such as `TB_VERSION`, `DOCKER_REPO`, or `TB_NODE_DOCKER_NAME`, then set `TB_PREV_VERSION` in `Makefile` to the version being upgraded from. Run `make upgrade-db` to destroy/recreate the DB service, build the `thingsboard` container wrapper, and execute the `UPGRADE_TB=true` path with `FROM_VERSION=$(TB_PREV_VERSION)`. After upgrade, use `make up` or `make up-prod` with the new upstream image tag.

## Build, Test, and Development Commands

- `make tb-quarkus-dev-up-with-deps`: run Quarkus dev with dependencies.
- `make tb-quarkus-dev-smoke`: start, wait, and curl the smoke endpoint.
- `cd ui-ngx && npm run lint`: lint the Angular UI.
- `cd tb-quarkus/gateway && ./gradlew test`: run Quarkus gateway tests.

## Coding Style & Naming Conventions

Follow existing packages and generated-code boundaries. `tb-quarkus/gateway` uses Java 21. Use `UpperCamelCase` classes, `lowerCamelCase` methods/fields, and `UPPER_SNAKE_CASE` constants. Preserve license headers. For `ui-ngx`, use two-space indentation, four-space JSON indentation, and this Angular class member order: public/protected/private static fields; public/protected/private instance fields; public/protected/private constructors; public/protected/private static methods; public/protected/private instance methods.

## Testing Guidelines

Prefer focused tests and smoke checks. Quarkus tests run from `tb-quarkus/gateway` with Gradle. Frontend checks run from `ui-ngx/`. For API changes, verify generated clients and the implementing endpoint. Do not add tests for untouched upstream ThingsBoard internals.

## Commit & Pull Request Guidelines

Recent commits use Conventional Commit style, for example `feat(ai-agent): ...`, `refactor: ...`, and `deploy(k8s): ...`. PRs should follow `pull_request_template.md`: include scope, linked issue, labels, milestone, docs notes, compatibility details, and UI screenshots.

## Security & Configuration Tips

Do not commit `.env` secrets, database volumes, Kafka data, model caches, or runtime cache directories. Document new config near the YAML/property. Keep Avro schemas in `tb-quarkus/gateway/src/main/avro` compatible with schema registry settings.
