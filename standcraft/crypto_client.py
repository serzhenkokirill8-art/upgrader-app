import aiohttp
import hmac
import hashlib
import json
from config import Config

class CryptoPayClient:
    def __init__(self):
        self.token = Config.CRYPTO_PAY_TOKEN
        self.base_url = Config.CRYPTO_PAY_API_URL
        self.headers = {"Crypto-Pay-API-Token": self.token}

    async def create_invoice(self, amount: float, currency: str = "USD", 
                             description: str = "", payload: str = ""):
        """
        Создаёт инвойс в Crypto Pay.
        Возвращает результат API (содержит invoice_id, pay_url и др.)
        """
        url = f"{self.base_url}/createInvoice"
        data = {
            "amount": amount,
            "currency": currency,
            "description": description,
            "hidden_message": "Пополнение баланса",
            "payload": payload,          # передаём user_id для вебхука
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=data) as resp:
                result = await resp.json()
                if result.get("ok"):
                    return result["result"]
                else:
                    raise Exception(f"Crypto Pay error: {result}")

    async def get_invoice_status(self, invoice_id: str):
        """Проверка статуса инвойса (для пулинга)"""
        url = f"{self.base_url}/getInvoices"
        params = {"invoice_ids": invoice_id}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers, params=params) as resp:
                result = await resp.json()
                if result.get("ok") and result["result"].get("items"):
                    return result["result"]["items"][0]
                return None

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        """
        Проверяет подпись вебхука от Crypto Pay (если задан секрет).
        """
        if not Config.CRYPTO_PAY_SECRET:
            return True
        computed = hmac.new(
            Config.CRYPTO_PAY_SECRET.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(computed, signature)