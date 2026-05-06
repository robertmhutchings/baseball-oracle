"""Baseball Oracle — FastAPI web layer.

Phase 3C Layer 1-2: local-only chat UI for the agent. Stateless server;
the browser holds conversation history and POSTs it back on each turn.

Run from C:\\BaseballOracle (project root):
    C:\\BaseballOracle\\.venv\\Scripts\\python.exe -m uvicorn web.server:app --reload

Then open http://localhost:8000 in a browser.

The server is local-only by design — Retrosheet data does not leave this
machine. Don't pass --host 0.0.0.0; the default 127.0.0.1 binding is correct.
"""

import os
from contextlib import asynccontextmanager

import anthropic
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.config import get_anthropic_api_key
from agent.main import answer_question
from agent.tools import ClarificationRequested


# ---------------------------------------------------------------------------
# Lifespan: instantiate the Anthropic client once at startup, reuse across
# requests. The client manages its own connection pool internally; recreating
# it per request would defeat that pooling and add unnecessary overhead.
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # API key check happens here (not at first request) so a missing key
    # surfaces as "server won't start" rather than "first chat 500s."
    api_key = get_anthropic_api_key()
    app.state.anthropic_client = anthropic.Anthropic(api_key=api_key)
    print("Open http://localhost:8000 in your browser to chat.")
    yield
    # No explicit close needed; httpx connections clean up on GC.


app = FastAPI(lifespan=lifespan, title="Baseball Oracle")


# ---------------------------------------------------------------------------
# Error format: uniform {"error": str} envelope for HTTPException, matching
# the API contract. (FastAPI's default is {"detail": ...} — overriding it
# here keeps the frontend error path simple.)
# ---------------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
    )


# ---------------------------------------------------------------------------
# /chat — single agent turn. Browser holds full history; sends it back each
# call. Server is stateless.
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    question: str
    history: list[dict] | None = None


class ChatResponse(BaseModel):
    response: str
    history: list[dict]
    trace: list[dict]


def _web_ask_user_handler(question: str) -> str:
    """ask_user handler for the web layer.

    Always raises ClarificationRequested. The web layer does not support
    inline mid-turn clarification — the agent's question becomes the
    assistant response, and the user's reply on the next chat turn
    naturally drives the agent to continue.
    """
    raise ClarificationRequested(question)


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request) -> ChatResponse:
    # Sync def (not async) so FastAPI runs answer_question — which makes
    # synchronous Anthropic calls — in a threadpool, keeping the event loop
    # free.
    client: anthropic.Anthropic = request.app.state.anthropic_client
    try:
        response_text, updated_history, trace = answer_question(
            client,
            req.question,
            history=req.history,
            ask_user_handler=_web_ask_user_handler,
        )
    except Exception as e:
        # Bounded error message — type + str only; no stack trace surfaced
        # to the browser.
        raise HTTPException(
            status_code=500,
            detail=f"{type(e).__name__}: {e}",
        )

    return ChatResponse(
        response=response_text,
        history=updated_history,
        trace=trace.serialize(),
    )


# ---------------------------------------------------------------------------
# Static UI: chat page at /, assets at /static/*.
# ---------------------------------------------------------------------------

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/")
def root() -> FileResponse:
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))
