import os
import requests
from dotenv import load_dotenv

load_dotenv()

GIPHY_API_KEY = os.getenv('GIPHY_API_KEY')

def test_giphy():
    """Тестирует доступность GIPHY API"""
    print("=" * 50)
    print("🔍 ТЕСТ GIPHY API")
    print("=" * 50)
    
    print(f"🔑 GIPHY API Key: {GIPHY_API_KEY[:10]}..." if GIPHY_API_KEY else "❌ API Key не найден")
    
    if not GIPHY_API_KEY:
        print("❌ Ошибка: GIPHY_API_KEY не задан в переменных окружения")
        return
    
    # Тест 1: Проверка баланса/статуса
    try:
        url = "https://api.giphy.com/v1/gifs/random"
        params = {
            'api_key': GIPHY_API_KEY,
            'tag': 'cat',
            'rating': 'pg-13'
        }
        
        print("\n📡 Тест 1: Запрос случайной GIF...")
        response = requests.get(url, params=params, timeout=10)
        
        print(f"   Статус код: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('meta'):
                print(f"   Meta status: {data['meta'].get('msg')}")
                print(f"   Meta code: {data['meta'].get('status')}")
            if data.get('data'):
                print(f"✅ Успех! GIF получена")
                print(f"   URL: {data['data']['images']['original']['url'][:50]}...")
                return True
        elif response.status_code == 429:
            print("❌ Лимит API исчерпан (429 Too Many Requests)")
            print("   Лимит GIPHY: 100 запросов в час")
            print("   Попробуйте позже или апгрейдните ключ до production")
        elif response.status_code == 403:
            print("❌ Ошибка авторизации (403 Forbidden)")
            print("   Проверьте правильность ключа")
        else:
            print(f"❌ Неизвестная ошибка: {response.status_code}")
            
    except requests.exceptions.Timeout:
        print("❌ Таймаут - сервер не отвечает")
    except requests.exceptions.ConnectionError:
        print("❌ Ошибка соединения")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    
    print("\n📋 Рекомендации:")
    print("1. Проверьте ключ в Railway Variables")
    print("2. Проверьте лимиты на https://developers.giphy.com/dashboard/")
    print("3. Если нужно больше запросов - апгрейдните до production ключа")
    
    return False

if __name__ == '__main__':
    test_giphy()