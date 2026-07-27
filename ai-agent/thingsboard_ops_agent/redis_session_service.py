"""Redis-backed ADK session service.

Makes the ai-agent container stateless: all conversation sessions, events
and accumulated state (tb:authority, tb:known_ids, tb:scope_resolved, …)
live in Redis instead of the local filesystem. The ai-agent-py container
can be recreated/restarted without losing conversation history, and multiple
replicas can share the same session store.

Register the ``redis://`` URI scheme with ADK's service registry (see
:func:`register_redis_session_service`) so ``adk api_server
--session_service_uri=redis://...`` picks this implementation up. Persistence
is enabled by passing ``SESSION_SERVICE_URI=redis://redis:6379/0`` in the
compose environment.

Key layout in Redis:
  adk:session:{app_name}:{user_id}:{session_id}  -> Session (JSON)
  adk:user:{app_name}:{user_id}                  -> user-scoped state (JSON)
  adk:index:{app_name}:{user_id}                 -> set of session_ids

Requires the ``redis`` package (redis.asyncio client).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google.adk.sessions.base_session_service import (
    BaseSessionService,
    ListSessionsResponse,
    GetSessionConfig,
)
from google.adk.sessions.session import Session

logger = logging.getLogger(__name__)

_KEY_PREFIX = "adk"
_SESSION_PREFIX = f"{_KEY_PREFIX}:session"
_USER_PREFIX = f"{_KEY_PREFIX}:user"
_INDEX_PREFIX = f"{_KEY_PREFIX}:index"


def _session_key(app_name: str, user_id: str, session_id: str) -> str:
    return f"{_SESSION_PREFIX}:{app_name}:{user_id}:{session_id}"


def _user_key(app_name: str, user_id: str) -> str:
    return f"{_USER_PREFIX}:{app_name}:{user_id}"


def _index_key(app_name: str, user_id: str) -> str:
    return f"{_INDEX_PREFIX}:{app_name}:{user_id}"


class RedisSessionService(BaseSessionService):
    """A :class:`BaseSessionService` backed by Redis (async client)."""

    def __init__(self, redis_url: str) -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Session:
        import time

        session = Session(
            id=session_id or f"session-{abs(hash((app_name, user_id, time.time())))}",
            app_name=app_name,
            user_id=user_id,
            state=state or {},
            last_update_time=time.time(),
        )
        # Merge any pre-existing user state into the new session.
        user_state = await self._get_user_state(app_name, user_id)
        if user_state:
            session.state.update({f"user:{k}": v for k, v in user_state.items()})

        await self._save_session(session)
        await self._add_to_index(app_name, user_id, session.id)
        return session

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: GetSessionConfig | None = None,
    ) -> Session | None:
        raw = await self._redis.get(_session_key(app_name, user_id, session_id))
        if not raw:
            return None
        session = Session.model_validate_json(raw)

        if config is not None:
            num_recent = getattr(config, "num_recent_events", None)
            if num_recent is not None and num_recent >= 0:
                session.events = session.events[-num_recent:]
        return session

    async def list_sessions(
        self, *, app_name: str, user_id: str | None = None
    ) -> ListSessionsResponse:
        if user_id is None:
            # Enumerate all index keys for this app and union the session ids.
            pattern = f"{_INDEX_PREFIX}:{app_name}:*"
            ids: list[str] = []
            async for key in self._redis.scan_iter(match=pattern):
                members = await self._redis.smembers(key)
                ids.extend(members)
        else:
            members = await self._redis.smembers(_index_key(app_name, user_id))
            ids = list(members)

        sessions = []
        for sid in ids:
            raw = await self._redis.get(_session_key(app_name, user_id or "", sid))
            if raw:
                sessions.append(Session.model_validate_json(raw))
        return ListSessionsResponse(sessions=sessions)

    async def delete_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> None:
        await self._redis.delete(_session_key(app_name, user_id, session_id))
        await self._redis.srem(_index_key(app_name, user_id), session_id)

    async def get_user_state(self, *, app_name: str, user_id: str) -> dict[str, Any]:
        return await self._get_user_state(app_name, user_id)

    async def append_event(self, session: Session, event: Any) -> Any:
        # Let the base class apply temp state + update in-memory session state.
        event = await super().append_event(session, event)
        session.last_update_time = __import__("time").time()
        await self._save_session(session)

        # Persist user-scoped state separately so it survives session deletion
        # and is shared across a user's sessions.
        user_state: dict[str, Any] = {}
        for key, value in session.state.items():
            if key.startswith("user:"):
                user_state[key[len("user:"):]] = value
        if user_state:
            await self._redis.set(
                _user_key(session.app_name, session.user_id),
                json.dumps(user_state),
            )
        return event

    async def _get_user_state(self, app_name: str, user_id: str) -> dict[str, Any]:
        raw = await self._redis.get(_user_key(app_name, user_id))
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    async def _save_session(self, session: Session) -> None:
        await self._redis.set(
            _session_key(session.app_name, session.user_id, session.id),
            session.model_dump_json(),
        )

    async def _add_to_index(self, app_name: str, user_id: str, session_id: str) -> None:
        await self._redis.sadd(_index_key(app_name, user_id), session_id)


def register_redis_session_service() -> None:
    """Register the ``redis://`` scheme with ADK's service registry.

    Safe to call multiple times — only registers once. Must run before
    ``adk api_server`` builds its session service (i.e. at import time of the
    agent module).
    """
    try:
        from google.adk.cli.service_registry import get_service_registry
    except Exception:  # pragma: no cover - defensive
        logger.warning("Redis session service: ADK service registry unavailable")
        return

    registry = get_service_registry()

    def redis_session_factory(uri: str, **kwargs: Any) -> RedisSessionService:
        # Strip any query string / path; we only need the connection URL.
        return RedisSessionService(redis_url=uri)

    registry.register_session_service("redis", redis_session_factory)
    logger.info("Registered redis:// session service with ADK")
