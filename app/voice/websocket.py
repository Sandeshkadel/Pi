"""Per-connection adapter from validated audio messages to the voice pipeline."""

import logging
from collections.abc import Awaitable, Callable

from fastapi import WebSocket

from app.server.schemas import (
    AudioChunk,
    IncomingMessage,
    Listening,
    ProtocolError,
    Speak,
    VoiceControl,
)
from app.server.websocket import MessageHandler, MessageHandlerFactory
from app.voice.pipeline import (
    VoiceBackendError,
    VoicePipeline,
    VoicePipelineBusyError,
    VoiceUpdate,
)

TranscriptHandler = Callable[[str], Awaitable[str]]
VoicePipelineFactory = Callable[[], VoicePipeline]
logger = logging.getLogger(__name__)


def create_voice_message_handler_factory(
    pipeline_factory: VoicePipelineFactory,
    transcript_handler: TranscriptHandler,
) -> MessageHandlerFactory:
    """Create one isolated voice pipeline for each authenticated connection."""

    def create_session() -> MessageHandler:
        pipeline = pipeline_factory()

        async def send_update(update: VoiceUpdate, websocket: WebSocket) -> None:
            if update.listening_started:
                await websocket.send_json(Listening(type="listening").model_dump(mode="json"))
            if update.speech is not None:
                await websocket.send_json(
                    Speak(type="speak", text=update.speech, interrupt=True).model_dump(
                        mode="json"
                    )
                )
            if update.transcript is not None:
                response = await transcript_handler(update.transcript)
                await websocket.send_json(
                    Speak(type="speak", text=response, interrupt=True).model_dump(
                        mode="json"
                    )
                )
                await pipeline.complete_response()

        async def handle_message(websocket: WebSocket, message: IncomingMessage) -> bool:
            try:
                if isinstance(message, VoiceControl):
                    update = (
                        await pipeline.begin_listening()
                        if message.action == "start"
                        else await pipeline.finish_listening()
                    )
                elif isinstance(message, AudioChunk):
                    update = await pipeline.process_chunk(message)
                else:
                    return False
            except VoiceBackendError:
                await pipeline.stop()
                await pipeline.reset()
                logger.warning("Local voice backend failed; the session was reset.")
                await websocket.send_json(
                    ProtocolError(
                        type="error",
                        code="voice_backend_error",
                        message="Local voice processing failed. Check the Pi model setup.",
                    ).model_dump(mode="json")
                )
                return True
            except (VoicePipelineBusyError, ValueError):
                await pipeline.stop()
                await pipeline.reset()
                await websocket.send_json(
                    ProtocolError(
                        type="error",
                        code="voice_session_error",
                        message="The voice message does not match the current session.",
                    ).model_dump(mode="json")
                )
                return True

            await send_update(update, websocket)
            return True

        return handle_message

    return create_session
