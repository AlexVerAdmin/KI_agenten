import os
import google.generativeai as genai
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

def list_supported_models():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("❌ ОШИБКА: GOOGLE_API_KEY не найден в .env файле.")
        return

    print(f"🔍 Проверка моделей для ключа: {api_key[:5]}...{api_key[-5:]}")
    
    try:
        genai.configure(api_key=api_key)
        
        print("\n✅ Доступные модели (которые поддерживают генерацию контента):")
        print("-" * 50)
        
        models = genai.list_models()
        found = False
        for m in models:
            if 'generateContent' in m.supported_generation_methods:
                print(f"Moded ID: {m.name}")
                print(f"Display Name: {m.display_name}")
                print(f"Description: {m.description}")
                print("-" * 50)
                found = True
        
        if not found:
            print("⚠️ Модели с поддержкой генерации не найдены.")
            
    except Exception as e:
        print(f"❌ Произошла ошибка при обращении к API: {str(e)}")

if __name__ == "__main__":
    list_supported_models()
