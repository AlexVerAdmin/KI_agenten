import os
import tempfile
import uuid
import asyncio
import edge_tts
import logging

async def generate_voice(text: str, agent_type: str = 'general') -> str:
    """
    Asynchronous function to generate voice from text using edge-tts.
    Returns path to the generated mp3 file.
    """
    voice = "de-DE-ConradNeural" if agent_type == 'german' else "ru-RU-SvetlanaNeural"
    
    try:
        temp_dir = tempfile.gettempdir()
        output_path = os.path.join(temp_dir, f"voice_{uuid.uuid4().hex[:8]}.mp3")
        
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        return output_path
    except Exception as e:
        logging.error(f"Generate Voice Error: {e}")
        return None

def text_to_speech(text: str, agent_type: str = 'general') -> str:
    """
    Synchronous wrapper for edge-tts.
    Returns path to the generated mp3 file.
    """
    # de-DE for German, ru-RU for others
    voice = "de-DE-ConradNeural" if agent_type == 'german' else "ru-RU-SvetlanaNeural"
    
    try:
        temp_dir = tempfile.gettempdir()
        output_path = os.path.join(temp_dir, f"speech_{uuid.uuid4().hex[:8]}.mp3")
        
        async def _internal():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_path)
            
        asyncio.run(_internal())
        return output_path
    except Exception as e:
        logging.error(f"TTS Error: {p}")
        return None

def speech_to_text():
    return None
