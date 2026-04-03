import pytest
from httpx import AsyncClient, ASGITransport

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent import app


TEST_AGENT_KEY = "test-agent-secret-key"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Agent-Key": TEST_AGENT_KEY},
    ) as ac:
        yield ac
