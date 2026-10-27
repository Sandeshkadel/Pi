"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.server.dashboard import DASHBOARD_HTML
from app.server.schemas import HealthResponse
from app.server.websocket import MessageHandlerFactory, create_agent_router


def create_app(
    message_handler_factory: MessageHandlerFactory | None = None,
    token_hash: str | None = None,
) -> FastAPI:
    """Build an application with explicit agent-channel dependencies."""
    if message_handler_factory is None:
        from app.voice.runtime import create_configured_voice_handler_factory

        message_handler_factory = create_configured_voice_handler_factory()

    application = FastAPI(title="PiAgent", version="0.1.0")
    application.include_router(
        create_agent_router(
            message_handler_factory=message_handler_factory,
            token_hash=token_hash,
        )
    )

    @application.get("/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        """Report that the HTTP service is available."""
        return HealthResponse(status="ok", service="piagent")

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard() -> str:
        """Serve the local status dashboard."""
        return DASHBOARD_HTML

    return application


app = create_app()
