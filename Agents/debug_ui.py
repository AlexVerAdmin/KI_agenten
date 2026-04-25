import asyncio
from playwright.async_api import async_playwright
import os

async def check_ui():
    async with async_playwright() as p:
        # Запускаем браузер
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # URL для локальной проверки
        url = "http://127.0.0.1:8081"
        
        print(f"Открываю {url}...")
        try:
            await page.goto(url, wait_until="networkidle", timeout=10000)
            
            # 1. Проверка главной страницы
            title = await page.title()
            print(f"Заголовок страницы: {title}")
            
            # Делаем скриншот главной
            os.makedirs("debug_screenshots", exist_ok=True)
            await page.screenshot(path="debug_screenshots/main_page.png")
            print("Скриншот главной сохранен в debug_screenshots/main_page.png")

            # 2. Проверка настроек
            print("Перехожу в /settings...")
            await page.goto(f"{url}/settings", wait_until="networkidle")
            await page.screenshot(path="debug_screenshots/settings_page.png")
            
            # Ищем текст "Realtime Voice"
            content = await page.content()
            if "Realtime Voice" in content:
                print("✅ Секция 'Realtime Voice' найдена в исходном коде страницы!")
            else:
                print("❌ Секция 'Realtime Voice' НЕ найдена в коде.")

            # 3. Проверка кнопки Live в чате
            await page.goto(url, wait_until="networkidle")
            # Ждем немного для загрузки настроек агента
            await asyncio.sleep(2) 
            live_btn = await page.query_selector("#realtime-toggle")
            if live_btn:
                is_visible = await live_btn.is_visible()
                print(f"Кнопка Live найдена. Видимость: {is_visible}")
            else:
                print("❌ Кнопка #realtime-toggle не найдена в DOM.")

        except Exception as e:
            print(f"Ошибка при проверке: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(check_ui())
