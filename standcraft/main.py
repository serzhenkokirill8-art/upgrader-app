import asyncio
import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.types import WebhookInfo
from fastapi import FastAPI

from config import Config
from web_app import app as fastapi_app, init_db
from bot import dp, bot

async def on_startup():
    # Инициализируем БД
    await init_db()
    # Устанавливаем вебхук для бота (опционально, если используем webhook)
    # Если используем polling, то не нужно.
    # await bot.set_webhook(f"{Config.WEBHOOK_URL}/webhook/telegram")
    print("Bot and API started")

async def main():
    # Запускаем FastAPI в отдельной задаче
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    
    # Запускаем бота в режиме polling
    polling_task = asyncio.create_task(dp.start_polling(bot))
    
    # Запускаем сервер
    await server.serve()
    
    # Останавливаем бота (хотя сервер никогда не завершится)
    polling_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())