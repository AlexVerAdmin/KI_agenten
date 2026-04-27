import asyncio
import json
import logging
import google.genai as genai
from google.genai import types
from fastapi import WebSocket, WebSocketDisconnect
from Agents.src.config import GEMINI_API_KEY, get_effective_settings

logger = logging.getLogger(__name__)

# gemini-2.0-flash не поддерживает bidiGenerateContent (Gemini Live)
# Используем gemini-3.1-flash-live-preview
MODEL_ID = "gemini-3.1-flash-live-preview"


async def handle_realtime_voice(websocket: WebSocket, agent: str, user_id: str = "alex"):
    """
    WebSocket-обработчик для Gemini Live API (новый google.genai SDK).
    Браузер → PCM Int16 16kHz → Gemini → PCM Int16 24kHz → браузер.
    """
    await websocket.accept()

    settings = get_effective_settings(agent, user_id)

    if not GEMINI_API_KEY:
        await websocket.send_json({"type": "error", "text": "GEMINI_API_KEY not found"})
        await websocket.close()
        return

    # Инициализируем клиента с v1alpha для поддержки Gemini Live (bidiGenerateContent)
    client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1alpha'})
    voice_name = settings.get("tts_voice", "Puck")
    system_prompt = settings.get("system_prompt", "") or None

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
            )
        ),
        system_instruction=system_prompt,
    )

    try:
        async with client.aio.live.connect(model=MODEL_ID, config=config) as session:

            async def send_to_gemini():
                try:
                    while True:
                        message = await websocket.receive()
                        if "bytes" in message and message["bytes"]:
                            await session.send_realtime_input(
                                audio=types.Blob(
                                    data=message["bytes"],
                                    mime_type="audio/pcm;rate=16000",
                                )
                            )
                        elif "text" in message:
                            data = json.loads(message["text"])
                            if data.get("type") == "end_of_turn":
                                await session.send_client_content(
                                    turns=types.Content(
                                        role="user",
                                        parts=[types.Part(text=" ")]
                                    ),
                                    turn_complete=True,
                                )
                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    logger.error(f"send_to_gemini error: {e}")

            async def receive_from_gemini():
                try:
                    async for response in session.receive():
                        sc = response.server_content
                        if sc and sc.model_turn:
                            for part in sc.model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    await websocket.send_bytes(part.inline_data.data)
                                elif part.text:
                                    await websocket.send_json({"type": "text", "text": part.text})
                        if sc and sc.interrupted:
                            await websocket.send_json({"type": "interrupted"})
                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    logger.error(f"receive_from_gemini error: {e}")

            await asyncio.gather(send_to_gemini(), receive_from_gemini())

    except WebSocketDisconnect:
        logger.info("Realtime WebSocket disconnected")
    except Exception as e:
        logger.error(f"Realtime handler error: {e}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "text": str(e)})
        except Exception:
            pass
