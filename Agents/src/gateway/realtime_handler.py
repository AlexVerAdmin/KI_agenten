import asyncio
import json
import logging
import base64
from fastapi import WebSocket, WebSocketDisconnect
from google import generativeai as genai
from src.config import GEMINI_API_KEY, get_effective_settings

logger = logging.getLogger(__name__)

async def handle_realtime_voice(websocket: WebSocket, agent: str, user_id: str = "alex"):
    """
    Обработчик WebSocket для Gemini Multimodal Live API.
    Транслирует аудио между клиентом (браузер) и Google Gemini.
    """
    settings = get_effective_settings(agent, user_id)
    
    if not GEMINI_API_KEY:
        await websocket.send_json({"type": "error", "text": "GEMINI_API_KEY not found"})
        await websocket.close()
        return

    genai.configure(api_key=GEMINI_API_KEY)
    
    # Настройка модели (используем 2.0 Flash для Live, так как она поддерживает Multimodal Live)
    model_id = "gemini-2.0-flash-exp" 
    
    config = {
        "specs": {
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {
                    "prebuilt_voice_config": {
                        "voice_name": "Puck" # Можно будет вынести в настройки
                    }
                }
            }
        },
        "system_instruction": settings.get("system_prompt", "")
    }

    try:
        # В текущем SDK Multimodal Live реализуется через асинхронный итерируемый сеанс
        # Примечание: Реальная имплементация может зависеть от версии SDK.
        # Здесь приведена концептуальная схема интеграции.
        
        async with genai.GenerativeModel(model_id).aio.live_connect(config=config) as session:
            
            async def send_to_gemini():
                """Получает аудио от браузера и шлет в Gemini"""
                try:
                    while True:
                        message = await websocket.receive()
                        if "bytes" in message:
                            # Бинарные данные (аудио-фреймы)
                            await session.send(message["bytes"], end_of_turn=False)
                        elif "text" in message:
                            data = json.loads(message["text"])
                            if data.get("type") == "end_of_turn":
                                await session.send(b"", end_of_turn=True)
                except Exception as e:
                    logger.error(f"Error sending to Gemini: {e}")

            async def receive_from_gemini():
                """Получает аудио от Gemini и шлет в браузер"""
                try:
                    async for response in session:
                        if response.audio:
                            await websocket.send_bytes(response.audio)
                        if response.text:
                            await websocket.send_json({"type": "text", "text": response.text})
                except Exception as e:
                    logger.error(f"Error receiving from Gemini: {e}")

            # Запускаем оба цикла параллельно
            await asyncio.gather(send_to_gemini(), receive_from_gemini())

    except WebSocketDisconnect:
        logger.info("Realtime WebSocket disconnected")
    except Exception as e:
        logger.error(f"Realtime Voice Error: {e}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "text": str(e)})
        except:
            pass
