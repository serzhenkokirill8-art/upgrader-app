from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    balance = Column(Float, default=0.0)
    custom_win_rate = Column(Float, nullable=True)          # в процентах (0-100) или NULL
    created_at = Column(DateTime, server_default=func.now())

    inventory = relationship("Inventory", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")

class Skin(Base):
    __tablename__ = "skins"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    value = Column(Float, nullable=False)                   # стоимость в условных единицах
    image_url = Column(String, nullable=True)

class Inventory(Base):
    __tablename__ = "inventory"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    skin_id = Column(Integer, ForeignKey("skins.id"), nullable=False)
    acquired_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="inventory")
    skin = relationship("Skin")

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    type = Column(String, nullable=False)                  # deposit, withdrawal, upgrade, promo
    description = Column(String, nullable=True)
    timestamp = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="transactions")

class PromoCode(Base):
    __tablename__ = "promo_codes"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False)
    type = Column(String, nullable=False)                  # 'balance' или 'item'
    reward = Column(String, nullable=False)                # для balance: строка с числом, для item: название скина
    max_uses = Column(Integer, default=1)
    used_count = Column(Integer, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class UpgradeLog(Base):
    __tablename__ = "upgrade_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    skin_from_id = Column(Integer, ForeignKey("skins.id"), nullable=True)
    skin_to_id = Column(Integer, ForeignKey("skins.id"), nullable=True)
    success = Column(Boolean, nullable=False)
    timestamp = Column(DateTime, server_default=func.now())

# Для хранения информации о созданных инвойсах (необязательно, но упрощает отслеживание)
class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(String, unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="USD")
    status = Column(String, default="pending")             # pending, paid, expired
    created_at = Column(DateTime, server_default=func.now())
    paid_at = Column(DateTime, nullable=True)