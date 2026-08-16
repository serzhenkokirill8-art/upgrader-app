from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from datetime import datetime
import hashlib
import hmac
import json
from urllib.parse import parse_qs, unquote
import random

from database import get_db, engine
from models import Base, User, Skin, Inventory, Transaction, PromoCode, UpgradeLog, Invoice
from config import Config
from crypto_client import CryptoPayClient

# Создаём таблицы (при первом запуске)
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Добавим несколько скинов-заглушек, если таблица пуста
        from sqlalchemy import text
        result = await conn.execute(text("SELECT COUNT(*) FROM skins"))
        count = result.scalar()
        if count == 0:
            skins = [
                {"name": "Лапка", "value": 10},
                {"name": "Коготок", "value": 25},
                {"name": "Клык", "value": 50},
                {"name": "Хвост", "value": 100},
                {"name": "Грива", "value": 250},
                {"name": "Крыло", "value": 500},
                {"name": "Рог", "value": 1000},
                {"name": "Корона", "value": 2500},
            ]
            for s in skins:
                await conn.execute(
                    text("INSERT INTO skins (name, value) VALUES (:name, :value)"),
                    {"name": s["name"], "value": s["value"]}
                )

# Валидация initData
def validate_init_data(init_data: str) -> dict:
    params = parse_qs(init_data)
    if 'hash' not in params:
        return None
    hash_str = params.pop('hash')[0]
    sorted_params = sorted(params.items())
    data_check_string = "\n".join([f"{k}={v[0]}" for k, v in sorted_params])
    secret_key = hashlib.sha256(Config.BOT_TOKEN.encode()).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if computed_hash != hash_str:
        return None
    user_data = json.loads(params['user'][0])
    return user_data

# Зависимость для получения текущего пользователя по initData
async def get_current_user(init_data: str = Header(..., alias="X-Init-Data"),
                           db: AsyncSession = Depends(get_db)):
    user_data = validate_init_data(init_data)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid init data")
    telegram_id = user_data.get('id')
    username = user_data.get('username')
    # Получаем или создаём пользователя
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(telegram_id=telegram_id, username=username)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        # обновляем username
        if user.username != username and username:
            user.username = username
            await db.commit()
    return user

# Проверка прав администратора/модератора
async def check_admin(user: User = Depends(get_current_user)):
    if user.telegram_id not in Config.ADMINS and user.telegram_id not in Config.MODERATORS:
        raise HTTPException(status_code=403, detail="Access denied")
    return user

# Инициализация FastAPI
app = FastAPI()
templates = Jinja2Templates(directory="templates")
crypto_client = CryptoPayClient()

# ---- Эндпоинты Web App ----

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/auth")
async def auth(init_data: str = Header(..., alias="X-Init-Data"),
               db: AsyncSession = Depends(get_db)):
    user = await get_current_user(init_data, db)
    # Получаем инвентарь
    inv_result = await db.execute(
        select(Inventory).where(Inventory.user_id == user.id).join(Skin)
    )
    inventory = []
    for inv in inv_result.scalars():
        inventory.append({
            "id": inv.id,
            "skin_id": inv.skin_id,
            "name": inv.skin.name,
            "value": inv.skin.value,
        })
    is_admin = user.telegram_id in Config.ADMINS
    is_moderator = user.telegram_id in Config.MODERATORS
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "username": user.username,
        "balance": user.balance,
        "custom_win_rate": user.custom_win_rate,
        "inventory": inventory,
        "is_admin": is_admin,
        "is_moderator": is_moderator,
    }

@app.get("/api/user/me")
async def get_me(user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    # аналогично /auth, но без создания
    inv_result = await db.execute(
        select(Inventory).where(Inventory.user_id == user.id).join(Skin)
    )
    inventory = []
    for inv in inv_result.scalars():
        inventory.append({
            "id": inv.id,
            "skin_id": inv.skin_id,
            "name": inv.skin.name,
            "value": inv.skin.value,
        })
    is_admin = user.telegram_id in Config.ADMINS
    is_moderator = user.telegram_id in Config.MODERATORS
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "username": user.username,
        "balance": user.balance,
        "custom_win_rate": user.custom_win_rate,
        "inventory": inventory,
        "is_admin": is_admin,
        "is_moderator": is_moderator,
    }

@app.post("/api/upgrade")
async def upgrade_skin(data: dict, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    """
    Апгрейд предмета (скина).
    Ожидает: {"inventory_id": int}
    """
    inventory_id = data.get("inventory_id")
    if not inventory_id:
        raise HTTPException(400, "inventory_id required")
    
    # Получаем выбранный инвентарь
    inv_result = await db.execute(
        select(Inventory).where(Inventory.id == inventory_id, Inventory.user_id == user.id)
        .join(Skin)
    )
    inv = inv_result.scalar_one_or_none()
    if not inv:
        raise HTTPException(404, "Item not found")
    
    current_skin = inv.skin
    # Находим все скины дороже текущего
    skins_result = await db.execute(
        select(Skin).where(Skin.value > current_skin.value)
    )
    possible_skins = skins_result.scalars().all()
    if not possible_skins:
        raise HTTPException(400, "No higher skins available")
    
    # Выбираем случайный целевой скин (можно взвешенно, но для простоты равномерно)
    target_skin = random.choice(possible_skins)
    
    # Расчёт шанса
    if user.custom_win_rate is not None:
        win_chance = user.custom_win_rate
    else:
        # Базовый шанс: чем больше разница, тем меньше шанс
        diff = target_skin.value - current_skin.value
        if diff <= 0:
            win_chance = 100
        else:
            # Пример: шанс = 100 - (diff / target_skin.value) * 100, но ограничим
            raw = 100 - (diff / target_skin.value) * 100
            win_chance = max(5, min(95, raw))  # от 5% до 95%
    
    # Бросаем кубик
    roll = random.random() * 100
    success = roll <= win_chance
    
    # Логируем апгрейд
    log = UpgradeLog(
        user_id=user.id,
        skin_from_id=current_skin.id,
        skin_to_id=target_skin.id if success else None,
        success=success
    )
    db.add(log)
    
    if success:
        # Удаляем старый предмет, добавляем новый
        await db.delete(inv)
        new_inv = Inventory(user_id=user.id, skin_id=target_skin.id)
        db.add(new_inv)
        # Запись транзакции (можно опционально)
        trans = Transaction(
            user_id=user.id,
            amount=0,
            type="upgrade",
            description=f"Апгрейд {current_skin.name} -> {target_skin.name}"
        )
        db.add(trans)
        result_skin = target_skin
    else:
        # При неудаче предмет сгорает
        await db.delete(inv)
        trans = Transaction(
            user_id=user.id,
            amount=0,
            type="upgrade",
            description=f"Неудачный апгрейд {current_skin.name}"
        )
        db.add(trans)
        result_skin = None
    
    await db.commit()
    
    return {
        "success": success,
        "win_chance": win_chance,
        "target_skin": {
            "id": target_skin.id,
            "name": target_skin.name,
            "value": target_skin.value
        } if success else None,
        "message": "Успешно!" if success else "Неудача, предмет потерян."
    }

@app.post("/api/upgrade_balance")
async def upgrade_balance(data: dict, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """
    Апгрейд баланса (ставка).
    Ожидает: {"amount": float, "multiplier": float} (multiplier например 1.5, 2, 3)
    """
    amount = data.get("amount")
    multiplier = data.get("multiplier", 2.0)
    if not amount or amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    if amount > user.balance:
        raise HTTPException(400, "Insufficient balance")
    if multiplier < 1.0:
        raise HTTPException(400, "Multiplier must be >= 1.0")
    
    # Расчёт шанса: чем выше множитель, тем меньше шанс
    if user.custom_win_rate is not None:
        win_chance = user.custom_win_rate
    else:
        # Базовый шанс: 100 / multiplier, но ограничим 5-95%
        raw = 100 / multiplier
        win_chance = max(5, min(95, raw))
    
    roll = random.random() * 100
    success = roll <= win_chance
    
    # Списываем сумму
    user.balance -= amount
    if success:
        win_amount = amount * multiplier
        user.balance += win_amount
        trans = Transaction(
            user_id=user.id,
            amount=win_amount - amount,   # чистый выигрыш
            type="upgrade",
            description=f"Выигрыш в апгрейде баланса (x{multiplier})"
        )
        db.add(trans)
    else:
        trans = Transaction(
            user_id=user.id,
            amount=-amount,
            type="upgrade",
            description=f"Проигрыш в апгрейде баланса (x{multiplier})"
        )
        db.add(trans)
    
    await db.commit()
    return {
        "success": success,
        "win_chance": win_chance,
        "new_balance": user.balance,
        "win_amount": amount * multiplier if success else 0,
        "message": "Вы выиграли!" if success else "Вы проиграли ставку."
    }

@app.post("/api/invoice/create")
async def create_invoice(data: dict, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    amount = data.get("amount")
    if not amount or amount <= 0:
        raise HTTPException(400, "Invalid amount")
    # Создаём инвойс через Crypto Pay
    try:
        result = await crypto_client.create_invoice(
            amount=amount,
            currency="USD",
            description=f"Пополнение баланса для {user.username or user.telegram_id}",
            payload=str(user.id)
        )
        # Сохраняем инвойс в БД для отслеживания
        invoice = Invoice(
            invoice_id=result["invoice_id"],
            user_id=user.id,
            amount=amount,
            currency="USD",
            status="pending"
        )
        db.add(invoice)
        await db.commit()
        return {
            "invoice_id": result["invoice_id"],
            "pay_url": result["pay_url"],
            "status": "pending"
        }
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/invoice/check")
async def check_invoice(data: dict, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    invoice_id = data.get("invoice_id")
    if not invoice_id:
        raise HTTPException(400, "invoice_id required")
    # Проверяем в БД
    result = await db.execute(select(Invoice).where(Invoice.invoice_id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    return {"status": invoice.status, "paid_at": invoice.paid_at}

# ---- Вебхук для Crypto Pay ----
@app.post("/webhook/crypto")
async def crypto_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("Crypto-Pay-API-Signature", "")
    # Проверяем подпись
    if not crypto_client.verify_webhook_signature(body, signature):
        raise HTTPException(401, "Invalid signature")
    
    data = await request.json()
    # Проверяем статус
    if data.get("payload", {}).get("status") == "paid":
        invoice_id = data["payload"].get("invoice_id")
        amount = float(data["payload"].get("amount"))
        user_id = int(data["payload"].get("payload", "0"))
        if user_id == 0:
            raise HTTPException(400, "No user_id in payload")
        
        # Обновляем инвойс в БД
        invoice_result = await db.execute(
            select(Invoice).where(Invoice.invoice_id == invoice_id)
        )
        invoice = invoice_result.scalar_one_or_none()
        if invoice and invoice.status != "paid":
            invoice.status = "paid"
            invoice.paid_at = datetime.utcnow()
            # Зачисляем средства пользователю
            user_result = await db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one()
            if user:
                user.balance += amount
                trans = Transaction(
                    user_id=user.id,
                    amount=amount,
                    type="deposit",
                    description=f"Пополнение через Crypto Pay (invoice {invoice_id})"
                )
                db.add(trans)
                await db.commit()
    return {"ok": True}

# ---- Админские эндпоинты ----

@app.post("/api/admin/set_win_rate")
async def set_win_rate(data: dict, admin: User = Depends(check_admin),
                       db: AsyncSession = Depends(get_db)):
    """Установка custom_win_rate для пользователя."""
    target_id = data.get("target_id")      # telegram_id пользователя
    rate = data.get("rate")                # от 0 до 100 или null для сброса
    if not target_id:
        raise HTTPException(400, "target_id required")
    user_result = await db.execute(select(User).where(User.telegram_id == target_id))
    target_user = user_result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(404, "User not found")
    if rate is not None:
        if not (0 <= rate <= 100):
            raise HTTPException(400, "Rate must be 0-100")
        target_user.custom_win_rate = rate
    else:
        target_user.custom_win_rate = None
    await db.commit()
    return {"message": "Win rate updated", "new_rate": target_user.custom_win_rate}

@app.post("/api/admin/create_promo")
async def create_promo(data: dict, admin: User = Depends(check_admin),
                       db: AsyncSession = Depends(get_db)):
    """Создание промокода."""
    code = data.get("code")
    promo_type = data.get("type")          # 'balance' или 'item'
    reward = data.get("reward")            # число или название скина
    max_uses = data.get("max_uses", 1)
    if not code or not promo_type or not reward:
        raise HTTPException(400, "Missing fields")
    # Проверка уникальности
    existing = await db.execute(select(PromoCode).where(PromoCode.code == code))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Code already exists")
    promo = PromoCode(
        code=code,
        type=promo_type,
        reward=str(reward),
        max_uses=max_uses,
        created_by=admin.id
    )
    db.add(promo)
    await db.commit()
    return {"message": "Promo code created", "code": code}

@app.post("/api/admin/delete_promo")
async def delete_promo(data: dict, admin: User = Depends(check_admin),
                       db: AsyncSession = Depends(get_db)):
    code = data.get("code")
    if not code:
        raise HTTPException(400, "code required")
    result = await db.execute(delete(PromoCode).where(PromoCode.code == code))
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "Promo code not found")
    return {"message": "Deleted"}

@app.get("/api/admin/promos")
async def list_promos(admin: User = Depends(check_admin),
                      db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PromoCode))
    promos = result.scalars().all()
    return [{
        "code": p.code,
        "type": p.type,
        "reward": p.reward,
        "max_uses": p.max_uses,
        "used_count": p.used_count,
        "created_at": p.created_at.isoformat()
    } for p in promos]

@app.get("/api/admin/users")
async def search_users(query: str, admin: User = Depends(check_admin),
                       db: AsyncSession = Depends(get_db)):
    """Поиск пользователей по ID или username."""
    if query.isdigit():
        telegram_id = int(query)
        result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    else:
        result = await db.execute(
            select(User).where(User.username.contains(query))
        )
    users = result.scalars().all()
    return [{
        "id": u.id,
        "telegram_id": u.telegram_id,
        "username": u.username,
        "balance": u.balance,
        "custom_win_rate": u.custom_win_rate
    } for u in users]

# ---- Промокоды для пользователей ----
@app.post("/api/promo/use")
async def use_promo(data: dict, user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    code = data.get("code")
    if not code:
        raise HTTPException(400, "code required")
    promo_result = await db.execute(select(PromoCode).where(PromoCode.code == code))
    promo = promo_result.scalar_one_or_none()
    if not promo:
        raise HTTPException(404, "Promo code not found")
    if promo.used_count >= promo.max_uses:
        raise HTTPException(400, "Promo code expired")
    
    # Активация
    if promo.type == "balance":
        amount = float(promo.reward)
        user.balance += amount
        trans = Transaction(
            user_id=user.id,
            amount=amount,
            type="promo",
            description=f"Промокод {code}"
        )
        db.add(trans)
    elif promo.type == "item":
        # Ищем скин по имени
        skin_result = await db.execute(select(Skin).where(Skin.name == promo.reward))
        skin = skin_result.scalar_one_or_none()
        if not skin:
            raise HTTPException(400, "Skin not found")
        # Проверяем, нет ли уже такого скина у пользователя (можно разрешить дубли, но лучше избежать)
        existing = await db.execute(
            select(Inventory).where(Inventory.user_id == user.id, Inventory.skin_id == skin.id)
        )
        if existing.scalar_one_or_none():
            # Можно выдать что-то ещё, но для простоты выдадим как есть
            pass
        new_inv = Inventory(user_id=user.id, skin_id=skin.id)
        db.add(new_inv)
        trans = Transaction(
            user_id=user.id,
            amount=0,
            type="promo",
            description=f"Промокод {code} -> {skin.name}"
        )
        db.add(trans)
    else:
        raise HTTPException(400, "Invalid promo type")
    
    promo.used_count += 1
    await db.commit()
    return {"message": "Promo code activated successfully", "type": promo.type, "reward": promo.reward}