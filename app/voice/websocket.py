"""Per-connection adapter from validated audio messages to the voice pipeline."""

from collections.abc import Awaitable, Callable

from fastapi import WebSocket

from app.server.schemas import (
    AudioChunk,
    IncomingMessage,
    Listening,
    Speak,
)
from app.server.websocket import MessageHandler, MessageHandlerFactory
from app.voice.pipeline import VoicePipeline

TranscriptHandler = Callable[[str], Awaitable[str]]
VoicePipelineFactory = Callable[[], VoicePipeline]


def create_voice_message_handler_factory(
    pipeline_factory: VoicePipelineFactory,
    transcript_handler: TranscriptHandler,
) -> MessageHandlerFactory:
    """Create one isolated voice pipeline for each authenticated connection."""

    def create_session() -> MessageHandler:
        pipeline = pipeline_factory()

        async def handle_message(websocket: WebSocket, message: IncomingMessage) -> bool:
            if not isinstance(message, AudioChunk):
                return False

            update = await pipeline.process_chunk(message)
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
            return True

        return handle_message

    return create_session
