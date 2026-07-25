"""Run the current API against legacy data without startup mutations.

This is an operator-only preview helper. It deliberately skips migrations and
background recovery so an incompatible legacy SQLite database remains untouched
while the current frontend is reviewed.
"""

from contextlib import asynccontextmanager

import uvicorn

from backend.main import app


@asynccontextmanager
async def read_preview_lifespan(_app):
    yield


app.router.lifespan_context = read_preview_lifespan
uvicorn.run(app, host="127.0.0.1", port=8031)
