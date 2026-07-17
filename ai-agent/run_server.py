"""Bootstrap the ADK api_server with the redis session-service scheme registered.

ADK builds its session service at startup (inside ``adk api_server``) *before*
the agent module is imported, so registering the ``redis://`` scheme from
within ``agent.py`` runs too late. This bootstrap registers the scheme in the
same process that launches the server, then delegates to the ``api_server``
Click command.
"""

from __future__ import annotations

import sys

from google.adk.cli import main as adk_cli

# Register the redis:// session-service scheme before the server builds its
# session service. Importing the module runs register_redis_session_service()
# at import time.
from thingsboard_ops_agent.redis_session_service import register_redis_session_service  # noqa: E402

register_redis_session_service()


def _build_argv() -> list[str]:
    argv = ["api_server", "--with_ui", "--host", "0.0.0.0"]

    port = sys.argv[1] if len(sys.argv) > 1 else None
    if port is None:
        import os

        port = os.environ.get("PORT", "8300")
    argv += ["--port", str(port)]

    session_uri = sys.argv[2] if len(sys.argv) > 2 else None
    if session_uri is None:
        import os

        session_uri = os.environ.get("SESSION_SERVICE_URI")
    if session_uri:
        argv += ["--session_service_uri", session_uri]

    # Pass the agents directory (adk api_server expects a path to the agents
    # root; the agent package lives at ./thingsboard_ops_agent).
    argv.append("thingsboard_ops_agent")
    return argv


if __name__ == "__main__":
    # Ensure the current working dir is on the path so the package imports.
    sys.path.insert(0, ".")
    adk_cli.main(_build_argv())
