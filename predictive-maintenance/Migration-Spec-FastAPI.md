# Migration Spec: In-Process Threading → Redis Streams (Quarkus ⇄ Python, no FastAPI, no Celery)

**Target repos:** `tb-quarkus` (failure mode records service) + `predictive-maintenance` (Python worker, `thingsboard-dev` monorepo)
**Scope:** Delete the FastAPI process entirely — websocket handling, threading-based prediction jobs, and in-memory job state. Quarkus becomes the control plane (enqueues work, exposes status/logs to the Angular frontend over its own WebSocket endpoint). Python becomes a pure worker process with no HTTP framework, driven by a Redis Stream. A dedicated Redis instance is the only thing connecting the two.

There is no Celery anywhere in this design — no broker abstraction, no result backend, no `apply_async`. Everything Celery gave you (queueing, self-rescheduling, crash recovery) is done with four native Redis primitives.

---

## 0. Redis decision — still a dedicated instance, still not TB's Redis

Same reasoning as before, unchanged by dropping Celery:

1. **Eviction policy conflict.** TB's Redis is typically tuned for cache eviction (`allkeys-lru`/`volatile-lru`), instance-wide across all logical DBs. Stream entries, scheduled ticks, and job hashes must never be silently evicted.
2. **Namespace isolation ≠ eviction isolation.** A separate logical DB avoids key collisions but not instance-wide `FLUSHALL`/eviction/maintenance.
3. **Performance isolation.** Per-log-line and per-iteration Pub/Sub publishes are a write-heavy, fan-out pattern, different from TB's read-heavy entity cache.
4. **Blast radius.** TB restarting/flushing its Redis shouldn't take the job queue down, and a runaway prediction job shouldn't degrade TB's cache latency.

**Decision:** new `redis-jobs` service, own container, own volume, own port (`6380` externally, TB keeps `6379`). All keys still prefixed `predmaint:` as defense-in-depth.

---

## 1. Architecture after migration

```
┌───────────────────────┐        XADD / HSET          ┌──────────────────────┐
│  Quarkus (tb-quarkus)  │ ────────────────────────────▶│  redis-jobs           │
│  - REST + own WebSocket│                              │  - Stream:            │
│    endpoint for Angular│◀──── SUBSCRIBE (Pub/Sub) ────│    predmaint:tasks    │
│  - control plane only, │                              │  - ZSET:              │
│    never runs a model  │                              │    predmaint:scheduled│
└───────────────────────┘                              │  - Hash: job state     │
                                                        │  - Pub/Sub: logs/     │
                                                        │    status/progress    │
                                                        └──────────────────────┘
                                                                   ▲  │
                                                    XREADGROUP /   │  │ PUBLISH
                                                    XAUTOCLAIM     │  ▼
                                                        ┌──────────────────────┐
                                                        │  Python worker        │
                                                        │  (no FastAPI, no      │
                                                        │   Celery — plain      │
                                                        │   consumer process)   │
                                                        └──────────────────────┘
```

- **Quarkus** never runs prediction/training logic and never talks to the Python process directly. It only touches Redis: `XADD` to enqueue, `HSET`/`HGET` for control flags and status reads, and `SUBSCRIBE` to forward logs/status/progress to its own WebSocket sessions.
- **Python worker** never accepts inbound connections. It only touches Redis: `XREADGROUP`/`XAUTOCLAIM` to pull work, `HGET`/`HSET` for job state, `ZADD` to schedule its own next tick, and `PUBLISH` for logs/status/progress.

---

## 2. Redis key/channel namespace

| Purpose | Key / Channel | Type |
|---|---|---|
| Task queue | `predmaint:tasks` | Stream |
| Worker consumer group | `predmaint-workers` (group on the stream above) | Consumer group |
| Delayed / self-rescheduling ticks | `predmaint:scheduled` | Sorted set, score = due time (epoch ms) |
| Job state | `predmaint:job:{model_id}` | Hash — `status`, `model_type`, `device_id`, `paused` (`0`/`1`), `start_time`, `last_run`, `iterations`, `training_progress` |
| Log history | `predmaint:logs:{model_id}:history` | List — `RPUSH` + `LTRIM -1000 -1` |
| Live log fan-out | `predmaint:logs:{model_id}` | Pub/Sub |
| Job status fan-out | `predmaint:job_status:{model_id}` | Pub/Sub |
| Model status fan-out | `predmaint:model_status:{forecast_id}` | Pub/Sub |
| Training progress fan-out | `predmaint:training_progress:{model_id}` | Pub/Sub |

No `threading.Lock()`, no `active_jobs` dict, no Celery broker/result DBs. A single logical Redis DB is enough — the keyspace is already namespaced by prefix, and `HSET`/`XADD`/`ZADD` are atomic per-key on their own.

---

## 3. Quarkus side — control plane (replaces the FastAPI REST+WS layer entirely)

Add `quarkus-redis-client` (Lettuce underneath — no protocol to emulate) and `quarkus-websockets` for the Angular-facing stream.

`pom.xml` additions:

```xml
<dependency>
    <groupId>io.quarkus</groupId>
    <artifactId>quarkus-redis-client</artifactId>
</dependency>
<dependency>
    <groupId>io.quarkus</groupId>
    <artifactId>quarkus-websockets</artifactId>
</dependency>
```

Enqueue + control flags — one class, no queue library, no serialization framework beyond plain string maps:

```java
@ApplicationScoped
public class PredictionJobService {

    @Inject
    RedisDataSource redis;

    StreamCommands<String, String, String> stream;
    HashCommands<String, String, String> hash;

    @PostConstruct
    void init() {
        stream = redis.stream(String.class);
        hash = redis.hash(String.class);
    }

    public String startJob(String modelId, String modelType, String deviceId) {
        String jobKey = "predmaint:job:" + modelId;

        if ("running".equals(hash.hget(jobKey, "status"))) {
            return null; // already running
        }

        hash.hset(jobKey, Map.of(
            "model_id", modelId,
            "model_type", modelType,
            "device_id", deviceId == null ? "" : deviceId,
            "status", "running",
            "paused", "0",
            "start_time", Instant.now().toString(),
            "iterations", "0"
        ));

        return stream.xadd("predmaint:tasks", Map.of(
            "task_type", "prediction_iteration",
            "model_id", modelId,
            "model_type", modelType,
            "device_id", deviceId == null ? "" : deviceId,
            "iteration", "0"
        ));
    }

    public String startTraining(String modelId, String modelType, String datasetRef) {
        return stream.xadd("predmaint:tasks", Map.of(
            "task_type", "train_model",
            "model_id", modelId,
            "model_type", modelType,
            "dataset_ref", datasetRef
        ));
    }

    public boolean stopJob(String modelId) {
        String jobKey = "predmaint:job:" + modelId;
        if (hash.hget(jobKey, "status") == null) return false;
        hash.hset(jobKey, "status", "stopped");
        return true; // the worker's next scheduled tick reads this and stops rescheduling
    }

    public boolean pauseJob(String modelId) {
        String jobKey = "predmaint:job:" + modelId;
        if (!"running".equals(hash.hget(jobKey, "status"))) return false;
        hash.hset(jobKey, "paused", "1");
        return true;
    }

    public boolean unpauseJob(String modelId) {
        String jobKey = "predmaint:job:" + modelId;
        if (!"running".equals(hash.hget(jobKey, "status"))) return false;
        hash.hset(jobKey, "paused", "0");
        return true;
    }

    public Map<String, String> getJobStatus(String modelId) {
        return hash.hgetall("predmaint:job:" + modelId);
    }
}
```

*(Method names on `RedisDataSource`/`StreamCommands` above are sketched to match the current `quarkus-redis-client` shape — double-check exact signatures against whatever Quarkus BOM version `tb-quarkus` is pinned to; this is a drop-in replacement for the old REST handlers, not a redesign of them.)*

Forwarding logs/status/progress to the frontend — Quarkus subscribes directly and rebroadcasts over its own WebSocket, replacing the old `create_log_callback` / `asyncio.run_coroutine_threadsafe` bridge entirely:

```java
@ServerEndpoint("/ws/predmaint/logs/{modelId}")
@ApplicationScoped
public class PredictionLogSocket {

    @Inject RedisDataSource redis;
    private final Map<String, PubSubCommands.Subscription> subs = new ConcurrentHashMap<>();

    @OnOpen
    public void onOpen(Session session, @PathParam("modelId") String modelId) {
        PubSubCommands<String> pubsub = redis.pubsub(String.class);
        var subscription = pubsub.subscribe(
            "predmaint:logs:" + modelId,
            message -> session.getAsyncRemote().sendText(message)
        );
        subs.put(session.getId(), subscription);
    }

    @OnClose
    public void onClose(Session session) {
        var s = subs.remove(session.getId());
        if (s != null) s.unsubscribe();
    }
}
```

Same pattern for `predmaint:job_status:{model_id}`, `predmaint:model_status:{forecast_id}`, and `predmaint:training_progress:{model_id}` — each gets its own tiny `@ServerEndpoint`, or one endpoint that multiplexes several channels per connection if the Angular client prefers a single socket.

---

## 4. Python worker — plain consumer process, no framework

No FastAPI, no Celery, no ASGI server. The entire "app" is a `while True` loop with two responsibilities: promote due scheduled ticks, and drain the stream.

`src/redis_client.py`:

```python
import os
import redis

REDIS_JOBS_URL = os.getenv("REDIS_JOBS_URL", "redis://redis-jobs:6379/0")
redis_client = redis.from_url(REDIS_JOBS_URL, decode_responses=True)

STREAM = "predmaint:tasks"
GROUP = "predmaint-workers"
SCHEDULED_ZSET = "predmaint:scheduled"

def ensure_group() -> None:
    try:
        redis_client.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise
```

**Delayed/self-rescheduling ticks — the sorted-set replacement for `countdown=`.**
A worker never sleeps or blocks a slot waiting for the next iteration. It writes its own next-run time into `predmaint:scheduled`, and a promotion step (run by every worker, on every loop) atomically moves due entries into the stream. The promotion is a Lua script so concurrent workers never double-promote the same entry:

`src/promote_due.lua`:

```lua
-- KEYS[1] = scheduled zset, KEYS[2] = stream
-- ARGV[1] = now (ms), ARGV[2] = max items per pass
local due = redis.call('ZRANGEBYSCORE', KEYS[1], 0, ARGV[1], 'LIMIT', 0, ARGV[2])
for _, member in ipairs(due) do
    redis.call('ZREM', KEYS[1], member)
    redis.call('XADD', KEYS[2], '*', 'payload', member)
end
return #due
```

```python
with open("src/promote_due.lua") as f:
    _PROMOTE_SCRIPT = redis_client.register_script(f.read())

def promote_due_tasks(now_ms: int, batch: int = 50) -> int:
    return _PROMOTE_SCRIPT(keys=[SCHEDULED_ZSET, STREAM], args=[now_ms, batch])

def schedule_tick(payload: dict, delay_seconds: float) -> None:
    import time, json, uuid
    due_ms = int((time.time() + delay_seconds) * 1000)
    # unique member per tick so same model_id/iteration never collides in the zset
    entry = {**payload, "_tick_id": uuid.uuid4().hex}
    redis_client.zadd(SCHEDULED_ZSET, {json.dumps(entry): due_ms})
```

**Crash recovery — `XAUTOCLAIM` replaces `task_acks_late`.**
If a worker dies mid-iteration, its pending stream entry sits unacknowledged. Any live worker reclaims entries idle longer than a threshold and reprocesses them — same "resume after crash" guarantee Celery gave you, with no broker abstraction in between:

```python
import socket, os

CONSUMER_NAME = f"worker-{socket.gethostname()}-{os.getpid()}"
MIN_IDLE_MS = 60_000

def reclaim_stale(consumer: str = CONSUMER_NAME):
    cursor = "0-0"
    while True:
        cursor, claimed, _ = redis_client.xautoclaim(
            STREAM, GROUP, consumer, min_idle_time=MIN_IDLE_MS, start=cursor, count=50
        )
        for msg_id, fields in claimed:
            handle_task(msg_id, fields)
        if cursor == "0-0":
            break
```

**Main loop** — this is the entire "worker process," no server, no event loop from a web framework:

```python
import time

def run_worker() -> None:
    ensure_group()
    while True:
        promote_due_tasks(int(time.time() * 1000))
        reclaim_stale()

        resp = redis_client.xreadgroup(
            GROUP, CONSUMER_NAME, {STREAM: ">"}, count=10, block=5000
        )
        if not resp:
            continue
        for _, messages in resp:
            for msg_id, fields in messages:
                handle_task(msg_id, fields)
```

**Task dispatch** — `task_type` distinguishes a one-shot training job from a self-rescheduling prediction iteration; both arrive on the same stream:

```python
import json

INTERVAL_ANOMALY = 24 * 60 * 60 * 60  # unchanged (unusually long) interval, kept as-is
INTERVAL_FORECAST = 5

def handle_task(msg_id: str, fields: dict) -> None:
    task_type = fields.get("task_type")
    try:
        if task_type == "train_model":
            train_model_task(fields)
        else:
            run_prediction_iteration(fields)
    finally:
        redis_client.xack(STREAM, GROUP, msg_id)

def run_prediction_iteration(fields: dict) -> None:
    model_id = fields["model_id"]
    model_type = fields["model_type"]
    device_id = fields.get("device_id", "")
    iteration = int(fields.get("iteration", 0))
    job_key = f"predmaint:job:{model_id}"

    status = redis_client.hget(job_key, "status")
    if status != "running":
        add_model_log(model_id, "info", "Job stopped by user")
        return

    if redis_client.hget(job_key, "paused") == "1":
        schedule_tick(dict(fields), delay_seconds=1)  # re-check shortly, do no work
        return

    try:
        add_model_log(model_id, "info", f"Running prediction iteration #{iteration}")
        if model_type == "AnomalyPredictor":
            anomaly_predict_model(model_id, iteration, device_id)  # unchanged body
        else:
            forecast_predict_model(model_id, iteration, device_id)  # unchanged body
        redis_client.hset(job_key, mapping={"iterations": iteration, "last_run": _now_iso()})
        publish_job_status(model_id)
    except Exception as e:
        add_model_log(model_id, "error", f"Prediction failed: {e}")
        return  # keep current behavior: stop looping on exception

    interval = INTERVAL_ANOMALY if model_type == "AnomalyPredictor" else INTERVAL_FORECAST
    next_fields = {**fields, "iteration": str(iteration + 1)}
    schedule_tick(next_fields, delay_seconds=interval)

def train_model_task(fields: dict) -> None:
    # one-shot, no rescheduling — train_and_save_model body unchanged aside from
    # update_training_progress no longer spinning its own thread (see Section 6)
    train_and_save_model(fields["model_id"], fields["model_type"], fields.get("dataset_ref"))
```

`add_model_log` is untouched from the Celery version aside from dropping the import — still a plain publish + capped list:

```python
def add_model_log(model_id: str, level: str, message) -> None:
    log_entry = {...}  # same shape as before
    payload = json.dumps(log_entry, default=to_native)
    redis_client.rpush(f"predmaint:logs:{model_id}:history", payload)
    redis_client.ltrim(f"predmaint:logs:{model_id}:history", -1000, -1)
    redis_client.publish(f"predmaint:logs:{model_id}", payload)
```

There is no `src/model/job.py` control layer on the Python side anymore — `start`/`stop`/`pause`/`unpause` and the initial enqueue all moved to Quarkus (Section 3). Python only ever *reads* `status`/`paused` and *writes* `iterations`/`last_run`/`training_progress`.

---

## 5. What gets deleted vs. what's untouched

**Deleted entirely:**
- The FastAPI process, its ASGI server, its router, `unified_model_stream.py`, the `token` query-param websocket auth check (auth now lives at whatever layer sits in front of Quarkus's WebSocket endpoint).
- Celery, `celery_app.py`, `Dockerfile.celery`'s `celery -A ... worker` entrypoint, the broker/result-backend DB split.
- `active_jobs`/`job_lock`, `log_callbacks`/`job_status_callbacks`/`model_status_callbacks`, every `threading.Thread`/`asyncio.run_coroutine_threadsafe` bridge.

**Unchanged:**
- `AnomalyPredictor`, `ForecastModel`, `DataRegistry`, `predict_failure`, `train_model` — already just called with data, never tied to threading or a web framework.
- Alarm creation via `get_client().save_alarm(...)` inside `anomaly_predict_model` — now runs inside the worker's task-handling call instead of a thread, otherwise identical.
- `add_model_log` payload shape, log list capping at 1000 entries.

## 6. Training progress — same hash+pubsub, no thread

```python
def update_training_progress(model_id: str, progress: dict | None) -> None:
    key = f"predmaint:job:{model_id}"
    redis_client.hset(key, "training_progress", json.dumps(progress) if progress else "")
    redis_client.publish(f"predmaint:training_progress:{model_id}", json.dumps(progress or {}))
```

No thread needed — `train_model_task` already runs inside the worker's own process, off Quarkus's request path entirely, so this was already safe to call synchronously.

---

## 7. `docker-compose.jobs.yml` (additive file, consistent with the existing multi-compose-file pattern)

```yaml
services:
  redis-jobs:
    image: redis:7-alpine
    container_name: redis-jobs
    command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy noeviction
    ports:
      - "6380:6379"
    volumes:
      - redis-jobs-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    networks:
      - tb-net

  predmaint-worker:
    build:
      context: ./predictive-maintenance
      dockerfile: Dockerfile.worker
    container_name: predmaint-worker
    command: python -m src.worker
    environment:
      - REDIS_JOBS_URL=redis://redis-jobs:6379/0
      - DATABASE_URL=${DATABASE_URL:-postgresql://postgres:postgres@postgres:5432/thingsboard}
    depends_on:
      redis-jobs:
        condition: service_healthy
      postgres:
        condition: service_started
    networks:
      - tb-net
    restart: unless-stopped
    # scale horizontally for more throughput — consumer group handles
    # multiple consumers on predmaint:tasks without any coordination code:
    # docker compose -f docker-compose.jobs.yml up --scale predmaint-worker=3

volumes:
  redis-jobs-data:

networks:
  tb-net:
    external: true   # matches the existing HAProxy/compose network
```

The Python service no longer publishes any port — it has no inbound API surface at all. `tb-quarkus` (already on `tb-net`) is the only thing the frontend talks to.

---

## 8. `Dockerfile.worker` (predictive-maintenance service)

No ASGI server, no `uvicorn`, no `celery[redis]` — just the `redis` client and whatever ML deps `library` already needs:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt redis

COPY . .

CMD ["python", "-m", "src.worker"]
```

If the current `predictive-maintenance/Dockerfile` uses Poetry, swap the install step accordingly and drop `fastapi`/`uvicorn`/`celery` from the dependency list entirely — nothing in this design needs them.

---

## 9. Environment variables

| Var | Where | Value |
|---|---|---|
| `REDIS_JOBS_URL` | Quarkus (`quarkus.redis.hosts`) + `predmaint-worker` | `redis://redis-jobs:6379/0` |
| `DATABASE_URL` | `predmaint-worker` (already exists for Quarkus, now also needed by the worker) | same as before |

For Quarkus specifically, `application.properties`:

```properties
quarkus.redis.hosts=redis://redis-jobs:6379/0
```

---

## 10. Migration/cutover checklist

1. Add `redis-jobs` service; confirm `docker compose exec redis-jobs redis-cli ping` → `PONG`.
2. Add `quarkus-redis-client` + `quarkus-websockets` to `tb-quarkus`; wire up `PredictionJobService` (Section 3).
3. Add `src/redis_client.py`, `src/promote_due.lua`, `src/worker.py` to `predictive-maintenance`; port `add_model_log`, `anomaly_predict_model`, `forecast_predict_model`, `train_and_save_model` bodies over unchanged.
4. Delete `src/model/job.py`'s control functions, `active_jobs`/`job_lock`, `unified_model_stream.py`, and the FastAPI app entrypoint entirely.
5. Add the `PredictionLogSocket`-style endpoints in Quarkus for logs/status/progress; point the Angular `TimeSeriesTelemetryComponent`/dashboard at Quarkus's WebSocket paths instead of the old FastAPI ones.
6. `ensure_group()` once against `predmaint:tasks` (or let `mkstream=True` handle first run).
7. Build and run `predmaint-worker` alongside `tb-quarkus`; trigger `startJob(...)` from Quarkus, confirm logs arrive over Quarkus's WebSocket via Redis Pub/Sub.
8. Kill the `predmaint-worker` container mid-job → confirm `XAUTOCLAIM` on a second worker (or the same one restarting) picks the pending entry back up and the job resumes without lost iterations.
9. Scale `predmaint-worker` to 2–3 replicas → confirm the consumer group fans work out without duplicate processing (the Lua promotion script is the only place duplication could sneak in — verify under load).
10. Load-check: `predmaint:scheduled` cardinality stays bounded, `predmaint:logs:*:history` lists stay capped at 1000, and Pub/Sub fan-out doesn't lag under the anomaly-detection interval.

---

## 11. Things deliberately *not* changed

- `AnomalyPredictor`, `ForecastModel`, `DataRegistry`, `predict_failure`, `train_model` — no changes needed.
- Alarm creation via `get_client().save_alarm(...)` — unchanged, now runs inside a plain function call from `handle_task` instead of a thread or Celery task.
- Log entry shape, 1000-entry cap, job-hash field names — all identical to the original design, only the transport around them changed.
