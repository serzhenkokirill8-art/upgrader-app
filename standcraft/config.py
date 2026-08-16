import os
from typing import List

class Config:
    # Токен бота (получить у @BotFather)
    BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
    
    # Токен Crypto Pay (получить у @CryptoBot)
    CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN", "YOUR_CRYPTO_PAY_TOKEN")
    CRYPTO_PAY_API_URL = "https://pay.crypt.bot/api"
    
    # Базовый URL для вебхуков (должен быть доступен извне)
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-domain.com")
    
    # Список администраторов и модераторов (Telegram ID)
    ADMINS: List[int] = [int(id) for id in os.getenv("ADMINS", "123456789").split(",")]
    MODERATORS: List[int] = [int(id) for id in os.getenv("MODERATORS", "").split(",") if id]
    
    # URL базы данных (SQLite + aiosqlite)
    DATABASE_URL = "sqlite+aiosqlite:///./db.sqlite3"
    
    # Секретный ключ для подписи initData (может быть любым, но лучше из переменных)
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-me")
    
    # Секрет для вебхуков Crypto Pay (если не задан, проверка подписи отключается)
    CRYPTO_PAY_SECRET = os.getenv("CRYPTO_PAY_SECRET", "")