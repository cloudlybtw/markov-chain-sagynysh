import pytest_asyncio

from sagynysh.db import connect


@pytest_asyncio.fixture
async def conn():
    connection = await connect(":memory:")
    try:
        yield connection
    finally:
        await connection.close()
