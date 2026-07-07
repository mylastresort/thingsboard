# aob-tb-loader

Quarkus CLI that pulls IBM Research's [AssetOpsBench](https://huggingface.co/datasets/ibm-research/AssetOpsBench)
scenarios from HuggingFace and pushes them into a ThingsBoard CE instance as:

1. **Topology** (Option A model): one TB **Asset** per physical asset named in the
   scenarios (e.g. `Chiller 6`), one TB **Device** per sensor on that asset class,
   related via a `Contains` relation.
2. **Scenario fixtures**: every scenario row (utterance, agent type, category,
   `deterministic` flag, `characteristic_form`, notes) pushed as `SERVER_SCOPE`
   attributes on one umbrella asset (`AOB_Benchmark_Scenarios`), keyed
   `scenario_<id>`. Your ADK agents / eval harness read these back through the
   ThingsBoard MCP server instead of re-hitting HuggingFace every run.

## Why no parquet parsing

Rows come straight from HF's `datasets-server` JSON API
(`https://datasets-server.huggingface.co/rows`), which serves any HF dataset
as plain JSON with pagination — no need to download/parse `.parquet` files.

## Why raw REST instead of `thingsboard-java-client`

`thingsboard-java-client` isn't published to Maven Central, and its
handwritten wrapper's method names for attribute/telemetry saves aren't
documented publicly (only `saveDevice`-style CRUD and `getTenantDevices` are
shown in the README). `TbGateway` talks to ThingsBoard's stable public REST
API directly (`/api/auth/login`, `/api/asset`, `/api/device`, `/api/relation`,
`/api/plugins/telemetry/.../attributes/SERVER_SCOPE`) — zero dependency risk.

If you build `thingsboard-java-client` locally and want to swap it in later,
everything else in this project only depends on `TbGateway`'s interface, so
you only need to rewrite that one class:

```bash
git clone https://github.com/thingsboard/thingsboard-java-client
cd thingsboard-java-client && mvn install -pl ce -am
# then re-point TbGateway's method bodies at ThingsboardClient,
# checking method names against the jar's bundled api-docs/*.md
```

## Build

```bash
./gradlew quarkusBuild
```

(No wrapper jar is included in this drop — run `gradle wrapper` once first if
you don't already have `gradlew` in the project, or just use your installed
`gradle` directly: `gradle quarkusBuild`.)

## Run

```bash
export TB_URL=http://localhost:8080
export TB_USERNAME=tenant@thingsboard.org
export TB_PASSWORD=tenant

# see what's actually in the dataset first
java -jar build/aob-tb-loader-1.0.0-SNAPSHOT-runner.jar pull-push --list-configs

# dry run: pull + parse + print a summary, touch nothing in ThingsBoard
java -jar build/aob-tb-loader-1.0.0-SNAPSHOT-runner.jar pull-push --dry-run

# full run against the default config, filtered to chiller/AHU (application.properties)
java -jar build/aob-tb-loader-1.0.0-SNAPSHOT-runner.jar pull-push

# pull a specific asset-class config (e.g. "compressor") instead of default
java -jar build/aob-tb-loader-1.0.0-SNAPSHOT-runner.jar pull-push --config compressor --split train

# only push scenario fixtures, skip topology (e.g. topology already exists)
java -jar build/aob-tb-loader-1.0.0-SNAPSHOT-runner.jar pull-push --scenarios-only

# inspect a partial run instead of auto-rolling it back
java -jar build/aob-tb-loader-1.0.0-SNAPSHOT-runner.jar pull-push --no-rollback
```

Or skip the jar entirely during development:

```bash
./gradlew quarkusRun --quarkus-args='pull-push --dry-run'
```

## Test connections

```bash
# test both ThingsBoard and HuggingFace
java -jar build/aob-tb-loader-1.0.0-SNAPSHOT-runner.jar test-connection

# test only ThingsBoard login plus token-authenticated API access
java -jar build/aob-tb-loader-1.0.0-SNAPSHOT-runner.jar test-connection --thingsboard-client

# test only HuggingFace /splits and /rows endpoints
java -jar build/aob-tb-loader-1.0.0-SNAPSHOT-runner.jar test-connection --huggingface-url
```

## Config knobs (`application.properties` / env vars)

| Property | Env var | Purpose |
|---|---|---|
| `agents.hf.dataset` | - | HF dataset id (`ibm-research/AssetOpsBench`) |
| `agents.hf.config` / `agents.hf.split` | - | default config/split, overridable via `--config`/`--split` |
| `agents.hf.token` | `HF_TOKEN` | only needed if the dataset/config is gated |
| `agents.tb.url` | `TB_URL` | ThingsBoard base URL |
| `agents.tb.username` / `agents.tb.password` | `TB_USERNAME` / `TB_PASSWORD` | tenant admin creds |
| `agents.tb.asset-class-filter` | - | CSV filter, e.g. `chiller,ahu`; empty = push every recognized class |
| `agents.tb.scenario-store-asset` | - | name of the umbrella scenario-fixture asset |

## Extending asset coverage

`AssetClassSensors` currently maps `chiller`, `ahu`, `compressor`, `pump` to
their known sensor sets. AssetOpsBench spans 9 asset classes total and is
growing via community contribution — add new classes there as you cover more
of the benchmark. Rows whose asset class isn't in that map still get their
scenario JSON pushed (via `--scenarios-only` semantics) but no topology,
since there's no sensor list to build Devices from yet.

## Session rollback on failure

Every `pull-push` run keeps an in-memory undo log (`TbSessionLedger`). If any
step fails partway through — a dropped connection mid-run, a bad HF row, TB
rejecting a payload — the run rolls back everything **it** created, in
reverse order, before exiting non-zero:

- Assets/Devices this run actually created get deleted (existing ones it
  merely found are left untouched).
- `Contains` relations get deleted explicitly only when both endpoints
  already existed; if either endpoint gets rolled back, ThingsBoard cascades
  the relation deletion for you.
- Scenario attribute keys that were brand new get deleted; keys that already
  had a value get restored to what they were before this run touched them.

Rollback is best-effort, not transactional (ThingsBoard's REST API has no
cross-entity transaction), so each undo step is attempted independently -
one failing undo doesn't stop the rest. Any that fail are logged clearly so
you know exactly what to clean up by hand.

Pass `--no-rollback` to skip this and leave partial state in place, e.g. to
inspect what got created before a failure.

## Caveats / not yet done

- No **Vibration** agent topology (FFT/envelope-spectrum sensors) — add a
  sensor class for it once your ThingsBoard telemetry actually carries
  vibration data.
- `characteristic_form` is stored as raw text (it's sometimes itself a small
  JSON blob, sometimes a rule prose) — your eval harness/grader is expected
  to parse it per scenario `category`, same as IBM's own benchmark does.
- Relation/attribute saves aren't wrapped in a "skip if already identical"
  check beyond TB's own dedupe-on-identical-relation behavior — reruns are
  safe but will re-PUT existing attributes each time.
