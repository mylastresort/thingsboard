import os

from dotenv import load_dotenv
from tb_ce_client import ThingsboardClient

_client = None


def get_client() -> ThingsboardClient:
    global _client

    if _client is None:
        load_dotenv()

        tb_host = os.getenv("TB_HOST", "http://thingsboard:8080")
        tb_username = os.getenv("TB_USERNAME", "tenant@thingsboard.org")
        tb_password = os.getenv("TB_PASSWORD", "tenant")

        _client = ThingsboardClient(
            tb_host,
            username=tb_username,
            password=tb_password,
        )

        # tmp fix, package should handle this automatically
        _t = _client.get_token()
        if _t is None:
            raise Exception("Failed to get token from Thingsboard client")
        assert _t is not None, "Failed to get token from Thingsboard client"
        _client.api_client.configuration.api_key["ApiKeyForm"] = _t

    return _client
