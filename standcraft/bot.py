from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from config import Config

bot = Bot(token=Config.BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_command(message: types.Message):
    # Создаём кнопку с Web App
    web_app_url = Config.WEBHOOK_URL  # должен указывать на корень FastAPI
    if not web_app_url:
        await message.answer("Web App URL не настроен")
        return
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Открыть апгрейдер", web_app=WebAppInfo(url=web_app_url))]
        ],
        resize_keyboard=True
    )
    await message.answer(
        "Добро пожаловать в апгрейдер! Нажмите кнопку, чтобы открыть игру.",
        reply_markup=keyboard
    )

# Дополнительные команды для админов (опционально)
@dp.message(Command("admin"))
async def admin_command(message: types.Message):
    if message.from_user.id not in Config.ADMINS and message.from_user.id not in Config.MODERATORS:
        await message.answer("У вас нет прав.")
        return
    # Можно отправить ссылку на админ-панель (если есть отдельный URL)
    await message.answer("Админ-панель доступна через Web App (вкладка Админ).")

# Обработчик неизвестных сообщений
@dp.message()
async def echo(message: types.Message):
    await message.answer("Используйте /start для начала.")