#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import sqlite3
import logging
import hashlib
import threading
import time
import requests
from datetime import datetime
from typing import Dict, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = "8896855591:AAF837-w09REedQe2RCSzSJhlhT7BKUrEQ0"
ADMIN_IDS = [8563327706]

# FreeKassa
FREAKASSA_MERCHANT_ID = "74630"
FREAKASSA_SECRET_KEY = "989ce9d4a83698f3b510fed671f7f073"

# CryptoBot
CRYPTOBOT_LINK = "https://t.me/send?start=IViV3moF8VZf"

# ========== НАСТРОЙКИ ==========
CURRENCY_SYMBOL = "₽"
BOT_USERNAME = "platezhka_robot"
CURRENCY_UPDATE_INTERVAL = 3600

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ========== КУРС ВАЛЮТ ==========

class CurrencyManager:
    def __init__(self):
        self.usd_to_rub = 0
        self.usdt_to_rub = 0
        self.last_update = None
        self.update_rates()
    
    def update_rates(self):
        try:
            response = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=USDTTRY")
            if response.status_code == 200:
                data = response.json()
                self.usdt_to_rub = float(data['price']) / 10
            else:
                response = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=rub")
                if response.status_code == 200:
                    data = response.json()
                    self.usdt_to_rub = data['tether']['rub']
            
            response = requests.get("https://api.exchangerate-api.com/v4/latest/USD")
            if response.status_code == 200:
                data = response.json()
                self.usd_to_rub = data['rates']['RUB']
            
            self.last_update = datetime.now()
            logger.info(f"✅ Курс обновлён: 1 USDT = {self.usdt_to_rub:.2f} ₽, 1 USD = {self.usd_to_rub:.2f} ₽")
        except Exception as e:
            logger.error(f"❌ Ошибка обновления курса: {e}")
    
    def rub_to_usdt(self, rub_amount):
        if self.usdt_to_rub == 0:
            return 0
        return rub_amount / self.usdt_to_rub

# ========== БАЗА ДАННЫХ ==========

class Database:
    def __init__(self, db_path="sales_bot.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            category TEXT,
            image_url TEXT,
            stock INTEGER DEFAULT 999,
            is_digital BOOLEAN DEFAULT 0,
            digital_content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        
        c.execute("""CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            emoji TEXT,
            sort_order INTEGER DEFAULT 0
        )""")
        
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            phone TEXT,
            balance REAL DEFAULT 0,
            bonus_points INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        
        c.execute("""CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_id INTEGER,
            quantity INTEGER DEFAULT 1,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        
        c.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT UNIQUE,
            user_id INTEGER,
            items TEXT,
            total REAL,
            status TEXT DEFAULT 'pending',
            payment_method TEXT,
            payment_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )""")
        
        c.execute("""CREATE TABLE IF NOT EXISTS promocodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            discount_percent INTEGER,
            active BOOLEAN DEFAULT 1,
            expires_at TIMESTAMP,
            max_uses INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0
        )""")
        
        conn.commit()
        conn.close()
        logger.info("База данных инициализирована")
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def add_category(self, name, emoji="📦", sort_order=0):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO categories (name, emoji, sort_order) VALUES (?, ?, ?)",
                  (name, emoji, sort_order))
        conn.commit()
        conn.close()
    
    def get_categories(self):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT name, emoji FROM categories ORDER BY sort_order")
        categories = [{"name": row[0], "emoji": row[1]} for row in c.fetchall()]
        conn.close()
        return categories
    
    def add_product(self, name, description, price, category=None, image_url=None, stock=999, is_digital=False, digital_content=None):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("""INSERT INTO products 
                    (name, description, price, category, image_url, stock, is_digital, digital_content) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                  (name, description, price, category, image_url, stock, is_digital, digital_content))
        product_id = c.lastrowid
        conn.commit()
        conn.close()
        return product_id
    
    def get_products(self, category=None, limit=50):
        conn = self.get_connection()
        c = conn.cursor()
        if category:
            c.execute("""SELECT id, name, description, price, category, image_url, stock, is_digital, digital_content
                        FROM products WHERE category = ? AND stock > 0 ORDER BY id DESC LIMIT ?""", (category, limit))
        else:
            c.execute("""SELECT id, name, description, price, category, image_url, stock, is_digital, digital_content
                        FROM products WHERE stock > 0 ORDER BY id DESC LIMIT ?""", (limit,))
        products = [{"id": row[0], "name": row[1], "description": row[2], "price": row[3], 
                     "category": row[4], "image_url": row[5], "stock": row[6], "is_digital": row[7],
                     "digital_content": row[8]} 
                    for row in c.fetchall()]
        conn.close()
        return products
    
    def get_product(self, product_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("""SELECT id, name, description, price, category, image_url, stock, is_digital, digital_content 
                    FROM products WHERE id = ?""", (product_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return {"id": row[0], "name": row[1], "description": row[2], "price": row[3], 
                    "category": row[4], "image_url": row[5], "stock": row[6], "is_digital": row[7], 
                    "digital_content": row[8]}
        return None
    
    def delete_product(self, product_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()
        conn.close()
    
    def register_user(self, user_id, username=None, first_name=None, last_name=None):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
                  (user_id, username, first_name, last_name))
        conn.commit()
        conn.close()
    
    def get_user(self, user_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return {"user_id": row[0], "username": row[1], "first_name": row[2], 
                    "last_name": row[3], "phone": row[4], "balance": row[5],
                    "bonus_points": row[6], "created_at": row[7]}
        return None
    
    def add_bonus(self, user_id, points):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET bonus_points = bonus_points + ? WHERE user_id = ?", (points, user_id))
        conn.commit()
        conn.close()
    
    def get_bonus(self, user_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT bonus_points FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else 0
    
    def add_promocode(self, code, discount_percent, expires_at=None, max_uses=1):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO promocodes (code, discount_percent, expires_at, max_uses) VALUES (?, ?, ?, ?)",
                  (code.upper(), discount_percent, expires_at, max_uses))
        conn.commit()
        conn.close()
    
    def apply_promocode(self, code):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT id, discount_percent, max_uses, used_count, expires_at FROM promocodes WHERE code = ? AND active = 1",
                  (code.upper(),))
        row = c.fetchone()
        conn.close()
        if not row:
            return {"success": False, "error": "Промокод не найден"}
        promo_id, discount, max_uses, used_count, expires_at = row
        if expires_at and datetime.now() > datetime.fromisoformat(expires_at):
            return {"success": False, "error": "Промокод истёк"}
        if used_count >= max_uses:
            return {"success": False, "error": "Промокод уже использован"}
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("UPDATE promocodes SET used_count = used_count + 1 WHERE id = ?", (promo_id,))
        conn.commit()
        conn.close()
        return {"success": True, "discount": discount}
    
    def add_to_cart(self, user_id, product_id, quantity=1):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT id, quantity FROM cart WHERE user_id = ? AND product_id = ?", (user_id, product_id))
        row = c.fetchone()
        if row:
            new_qty = row[1] + quantity
            c.execute("UPDATE cart SET quantity = ? WHERE id = ?", (new_qty, row[0]))
        else:
            c.execute("INSERT INTO cart (user_id, product_id, quantity) VALUES (?, ?, ?)", 
                      (user_id, product_id, quantity))
        conn.commit()
        conn.close()
    
    def remove_from_cart(self, user_id, product_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM cart WHERE user_id = ? AND product_id = ?", (user_id, product_id))
        conn.commit()
        conn.close()
    
    def get_cart(self, user_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT c.product_id, p.name, p.price, c.quantity, p.is_digital, p.stock, p.digital_content
            FROM cart c JOIN products p ON c.product_id = p.id WHERE c.user_id = ?
        """, (user_id,))
        cart = [{"product_id": row[0], "name": row[1], "price": row[2], 
                 "quantity": row[3], "is_digital": row[4], "stock": row[5],
                 "digital_content": row[6]} 
                for row in c.fetchall()]
        conn.close()
        return cart
    
    def clear_cart(self, user_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    
    def get_cart_total(self, user_id):
        cart = self.get_cart(user_id)
        return sum(item["price"] * item["quantity"] for item in cart)
    
    def create_order(self, user_id, items, total, payment_method, payment_id=None):
        conn = self.get_connection()
        c = conn.cursor()
        order_number = f"ORD-{datetime.now().strftime('%Y%m%d')}-{user_id}-{int(datetime.now().timestamp()) % 1000}"
        c.execute("""INSERT INTO orders (order_number, user_id, items, total, payment_method, payment_id) 
                    VALUES (?, ?, ?, ?, ?, ?)""",
                  (order_number, user_id, json.dumps(items), total, payment_method, payment_id))
        order_id = c.lastrowid
        c.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        return order_id, order_number
    
    def update_order_status(self, order_id, status):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("UPDATE orders SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", 
                  (status, order_id))
        conn.commit()
        conn.close()
    
    def get_order(self, order_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT id, order_number, user_id, items, total, status, created_at FROM orders WHERE id = ?", (order_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return {"id": row[0], "order_number": row[1], "user_id": row[2], 
                    "items": json.loads(row[3]), "total": row[4], "status": row[5], "created_at": row[6]}
        return None
    
    def get_orders(self, user_id=None, limit=50):
        conn = self.get_connection()
        c = conn.cursor()
        if user_id:
            c.execute("""SELECT id, order_number, items, total, status, created_at 
                        FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT ?""", (user_id, limit))
        else:
            c.execute("""SELECT id, order_number, items, total, status, created_at 
                        FROM orders ORDER BY created_at DESC LIMIT ?""", (limit,))
        orders = [{"id": row[0], "order_number": row[1], "items": json.loads(row[2]), 
                   "total": row[3], "status": row[4], "created_at": row[5]} 
                  for row in c.fetchall()]
        conn.close()
        return orders
    
    def get_pending_orders(self):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("""SELECT id, order_number, user_id, total, created_at 
                    FROM orders WHERE status = 'pending' ORDER BY created_at ASC""")
        orders = [{"id": row[0], "order_number": row[1], "user_id": row[2], 
                   "total": row[3], "created_at": row[4]} 
                  for row in c.fetchall()]
        conn.close()
        return orders
    
    def get_stats(self):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM orders")
        total_orders = c.fetchone()[0]
        c.execute("SELECT SUM(total) FROM orders WHERE status != 'cancelled'")
        total_revenue = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM orders WHERE DATE(created_at) = DATE('now')")
        today_orders = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM products WHERE stock > 0")
        in_stock = c.fetchone()[0]
        conn.close()
        return {
            "total_users": total_users,
            "total_orders": total_orders,
            "total_revenue": total_revenue,
            "today_orders": today_orders,
            "in_stock": in_stock
        }

# ========== ИНИЦИАЛИЗАЦИЯ ==========
db = Database()

db.add_category("CEF Сборки", "💻")
db.add_category("GUI ", "💻")
db.add_category("ENB", "💻")
db.add_category("Услуги", "💻")
db.add_category("Другое", "💻")

if not db.get_products():
    db.add_product("CEF Сборка Pro", "Максимальная производительность для киберспорта", 499.99, "CEF Сборки", None, 999, True, "https://disk.yandex.by/d/vh2uOW6df9BPQQ")
    db.add_product("CEF Сборка Lite", "Самая лучшая сборка из lite коллекции", 199.53, "CEF Сборки", None, 999, True, "https://disk.yandex.by/d/vh2uOW6df9BPQQ")
    db.add_product("CEF Сборка Mid", "Средний уровень для комфортной игры", 320.78, "CEF Сборки", None, 999, True, "https://disk.yandex.by/d/vh2uOW6df9BPQQ")
    db.add_product("CEF Сборка Ultra", "Ультимативная сборка для профессионалов", 820.99, "CEF Сборки", None, 999, True, "https://disk.yandex.by/d/vh2uOW6df9BPQQ")
    db.add_product("Курс по CEF", "Полный гайд по настройке CEF сборок", 389, "CEF Сборки", None, 999, True, "https://disk.yandex.by/d/vh2uOW6df9BPQQ")

db.add_promocode("KVEZOVTEAM", 10, None, 50)
db.add_promocode("SUMMER20", 20, "2026-09-01T00:00:00", 100)

# ========== БОТ ==========

class SalesBot:
    def __init__(self, token):
        self.token = token
        self.db = db
        self.application = None
        self.currency = CurrencyManager()
    
    def start(self):
        self.application = Application.builder().token(self.token).build()
        
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("catalog", self.catalog_command))
        self.application.add_handler(CommandHandler("cart", self.cart_command))
        self.application.add_handler(CommandHandler("orders", self.orders_command))
        self.application.add_handler(CommandHandler("profile", self.profile_command))
        self.application.add_handler(CommandHandler("admin", self.admin_command))
        self.application.add_handler(CommandHandler("cancel", self.cancel_command))
        self.application.add_handler(CommandHandler("update_currency", self.update_currency_command))
        
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        self.start_currency_updater()
        
        logger.info("🚀 Бот запущен!")
        self.application.run_polling()
    
    def start_currency_updater(self):
        def update_loop():
            while True:
                time.sleep(CURRENCY_UPDATE_INTERVAL)
                self.currency.update_rates()
                logger.info("🔄 Автообновление курса выполнено")
        thread = threading.Thread(target=update_loop, daemon=True)
        thread.start()
    
    async def update_currency_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("⛔ *Нет доступа*", parse_mode="Markdown")
            return
        self.currency.update_rates()
        await update.message.reply_text(
            f"✅ *Курс обновлён*\n\n💰 1 USDT = {self.currency.usdt_to_rub:.2f} ₽\n💰 1 USD = {self.currency.usd_to_rub:.2f} ₽",
            parse_mode="Markdown"
        )
    
    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.clear()
        await update.message.reply_text("✅ *Действие отменено*", parse_mode="Markdown")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        self.db.register_user(user.id, user.username, user.first_name, user.last_name)
        text = f"🛍️ *Добро пожаловать в магазин CEF сборок!*\n\nМы рады видеть тебя, {user.first_name}! 👋\n\nЧто тебя интересует?"
        keyboard = [
            [InlineKeyboardButton("📦 Каталог", callback_data="catalog")],
            [InlineKeyboardButton("🛒 Корзина", callback_data="view_cart")],
            [InlineKeyboardButton("📋 Мои заказы", callback_data="my_orders")],
            [InlineKeyboardButton("👤 Профиль", callback_data="profile")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = """
❓ *Помощь и инструкция*

📌 *Команды:*
/start - Главное меню
/catalog - Каталог
/cart - Корзина
/orders - Мои заказы
/profile - Профиль
/admin - Админ-панель (для админов)
/update_currency - Обновить курс валют (админ)

💎 *Бонусы:* 5% от суммы заказа
🎁 *Промокоды:* Введите в корзине
💰 *Курс обновляется автоматически раз в час.*
        """
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]]
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    async def catalog_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        categories = self.db.get_categories()
        keyboard = []
        for cat in categories:
            keyboard.append([InlineKeyboardButton(f"{cat['emoji']} {cat['name']}", callback_data=f"category_{cat['name']}")])
        keyboard.append([InlineKeyboardButton("🔄 Все товары", callback_data="category_all")])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
        text = "📦 *Каталог*\n\nВыбери категорию:"
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    async def cart_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        await self.show_cart(update, user_id, context)
    
    async def orders_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        orders = self.db.get_orders(user_id)
        if not orders:
            text = "📋 *У вас пока нет заказов*"
        else:
            text = "📋 *Ваши заказы:*\n\n"
            for order in orders[:5]:
                status_emoji = "✅" if order['status'] == "paid" else "⏳"
                text += f"📦 #{order['order_number']}\n💰 {order['total']:.2f} {CURRENCY_SYMBOL}\n{status_emoji} Статус: {order['status']}\n📅 {order['created_at'][:10]}\n\n"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    async def profile_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user = self.db.get_user(user_id)
        if not user:
            await update.message.reply_text("❌ Пользователь не найден")
            return
        bonus = self.db.get_bonus(user_id)
        text = f"👤 *Профиль*\n\n• ID: `{user['user_id']}`\n• Имя: {user['first_name'] or 'Не указано'}\n• Username: @{user['username'] or 'Не указан'}\n• Баланс: {user['balance']:.2f} {CURRENCY_SYMBOL}\n💎 Бонусов: {bonus}\n• Дата: {user['created_at'][:10]}"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            if update.message:
                await update.message.reply_text("⛔ *Нет доступа*", parse_mode="Markdown")
            else:
                await update.callback_query.edit_message_text("⛔ *Нет доступа*", parse_mode="Markdown")
            return

        pending = self.db.get_pending_orders()
        pending_count = len(pending)
        text = f"👑 *Админ-панель*\n\n📌 Управление:\n⏳ Заказов на подтверждение: {pending_count}"
        
        keyboard = [
            [InlineKeyboardButton("📦 Товары", callback_data="admin_products")],
            [InlineKeyboardButton("➕ Добавить товар", callback_data="admin_add_product")],
            [InlineKeyboardButton("📋 Заказы", callback_data="admin_orders")],
            [InlineKeyboardButton("💳 Подтвердить оплату", callback_data="admin_confirm_payment")],
            [InlineKeyboardButton("🎁 Добавить промокод", callback_data="admin_add_promocode")],
            [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]
        ]
        
        if update.message:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    async def show_products(self, update: Update, category=None):
        products = self.db.get_products(category)
        if not products:
            text = "📦 *В этой категории пока нет товаров*"
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="catalog")]]
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return
        text = "📦 *Товары:*\n\n"
        keyboard = []
        for p in products:
            digital = "🖥️ " if p.get('is_digital') else ""
            usdt_price = self.currency.rub_to_usdt(p['price'])
            text += f"🔹 {digital}*{p['name']}* — {p['price']:.2f} {CURRENCY_SYMBOL} (~{usdt_price:.2f} USDT)\n"
            keyboard.append([InlineKeyboardButton(f"👉 {p['name']}", callback_data=f"product_{p['id']}")])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="catalog")])
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    async def show_product_detail(self, update: Update, product_id):
        product = self.db.get_product(product_id)
        if not product:
            await update.callback_query.edit_message_text("❌ Товар не найден")
            return
        digital_note = "\n🖥️ *Цифровой товар* — выдача после оплаты" if product.get('is_digital') else ""
        usdt_price = self.currency.rub_to_usdt(product['price'])
        text = f"🛍️ *{product['name']}*\n\n📝 {product['description']}\n💰 *Цена:* {product['price']:.2f} {CURRENCY_SYMBOL} (~{usdt_price:.2f} USDT)\n📦 *В наличии:* {product['stock']} шт.{digital_note}"
        keyboard = [
            [InlineKeyboardButton("🛒 Добавить в корзину", callback_data=f"add_to_cart_{product_id}")],
            [InlineKeyboardButton("🗑 Удалить товар (админ)", callback_data=f"admin_delete_product_{product_id}")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"category_{product['category'] or 'all'}")]
        ]
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    async def show_cart(self, update: Update, user_id, context=None):
        cart = self.db.get_cart(user_id)
        if not cart:
            text = "🛒 *Корзина пуста*"
            keyboard = [[InlineKeyboardButton("📦 В каталог", callback_data="catalog")]]
            if update.callback_query:
                await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            else:
                await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return
        text = "🛒 *Корзина:*\n\n"
        total = 0
        keyboard = []
        for item in cart:
            subtotal = item["price"] * item["quantity"]
            total += subtotal
            text += f"• {item['name']} × {item['quantity']} = {subtotal:.2f} {CURRENCY_SYMBOL}\n"
            keyboard.append([InlineKeyboardButton(f"❌ Убрать {item['name']}", callback_data=f"remove_from_cart_{item['product_id']}")])
        discount = context.user_data.get("promocode_discount", 0) if context else 0
        usdt_total = self.currency.rub_to_usdt(total)
        if discount > 0:
            new_total = total * (1 - discount / 100)
            new_usdt_total = self.currency.rub_to_usdt(new_total)
            text += f"\n🎁 *Скидка:* {discount}%\n"
            text += f"💰 *Итого без скидки:* {total:.2f} {CURRENCY_SYMBOL} (~{usdt_total:.2f} USDT)\n"
            text += f"💰 *Итого со скидкой:* {new_total:.2f} {CURRENCY_SYMBOL} (~{new_usdt_total:.2f} USDT)"
        else:
            text += f"\n💰 *Итого:* {total:.2f} {CURRENCY_SYMBOL} (~{usdt_total:.2f} USDT)"
        keyboard.append([InlineKeyboardButton("🎁 Ввести промокод", callback_data="enter_promocode")])
        keyboard.append([InlineKeyboardButton("🔄 Очистить", callback_data="clear_cart")])
        keyboard.append([InlineKeyboardButton("💳 Оплатить", callback_data="checkout")])
        keyboard.append([InlineKeyboardButton("🔙 В каталог", callback_data="catalog")])
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        user_id = query.from_user.id
        
        if data == "back_to_menu":
            await self.start_command(update, context)
        elif data == "catalog":
            await self.catalog_command(update, context)
        elif data == "help":
            await self.help_command(update, context)
        elif data == "view_cart":
            await self.show_cart(update, user_id, context)
        elif data == "my_orders":
            await self.orders_command(update, context)
        elif data == "profile":
            await self.profile_command(update, context)
        elif data.startswith("category_"):
            category = data.replace("category_", "")
            if category == "all":
                category = None
            await self.show_products(update, category)
        elif data.startswith("product_"):
            product_id = int(data.replace("product_", ""))
            await self.show_product_detail(update, product_id)
        elif data.startswith("add_to_cart_"):
            product_id = int(data.replace("add_to_cart_", ""))
            self.db.add_to_cart(user_id, product_id)
            await query.edit_message_text("✅ *Товар добавлен в корзину!*", parse_mode="Markdown")
        elif data.startswith("remove_from_cart_"):
            product_id = int(data.replace("remove_from_cart_", ""))
            self.db.remove_from_cart(user_id, product_id)
            await self.show_cart(update, user_id, context)
        elif data == "clear_cart":
            self.db.clear_cart(user_id)
            context.user_data.pop("promocode_discount", None)
            await self.show_cart(update, user_id, context)
        elif data == "enter_promocode":
            context.user_data["awaiting_promocode"] = True
            await query.edit_message_text(
                "🎁 *Введите промокод*\n\nОтправьте код одним сообщением.\nДля отмены отправьте /cancel",
                parse_mode="Markdown"
            )
        elif data == "checkout":
            cart = self.db.get_cart(user_id)
            if not cart:
                await query.edit_message_text("❌ *Корзина пуста*", parse_mode="Markdown")
                return
            total = self.db.get_cart_total(user_id)
            discount = context.user_data.get("promocode_discount", 0)
            usdt_total = self.currency.rub_to_usdt(total)
            if discount > 0:
                final_total = total * (1 - discount / 100)
                final_usdt = self.currency.rub_to_usdt(final_total)
                text = f"💳 *Оформление заказа*\n\n💰 *Итого без скидки:* {total:.2f} {CURRENCY_SYMBOL} (~{usdt_total:.2f} USDT)\n🎁 *Скидка:* {discount}%\n💰 *Итого со скидкой:* {final_total:.2f} {CURRENCY_SYMBOL} (~{final_usdt:.2f} USDT)\n\nВыбери способ оплаты:"
            else:
                final_total = total
                text = f"💳 *Оформление заказа*\n\n💰 *Итого:* {total:.2f} {CURRENCY_SYMBOL} (~{usdt_total:.2f} USDT)\n\nВыбери способ оплаты:"
            keyboard = [
                [InlineKeyboardButton("💳 FreeKassa", callback_data="pay_freekassa")],
                [InlineKeyboardButton("🪙 CryptoBot (USDT)", callback_data="pay_cryptobot")],
                [InlineKeyboardButton("💳 Оплатить по реквизитам", callback_data="pay_manual")],
                [InlineKeyboardButton("🔙 Назад", callback_data="view_cart")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
        elif data == "pay_freekassa":
            cart = self.db.get_cart(user_id)
            if not cart:
                await query.edit_message_text("❌ *Корзина пуста*", parse_mode="Markdown")
                return
            total = self.db.get_cart_total(user_id)
            discount = context.user_data.get("promocode_discount", 0)
            final_total = total * (1 - discount / 100) if discount > 0 else total
            order_id, order_number = self.db.create_order(user_id, cart, final_total, "freekassa")
            total_formatted = f"{final_total:.2f}"
            sign = hashlib.md5(f"{FREAKASSA_MERCHANT_ID}:{total_formatted}:{FREAKASSA_SECRET_KEY}:{order_id}".encode()).hexdigest()
            payment_url = f"https://pay.freekassa.ru/?m={FREAKASSA_MERCHANT_ID}&oa={total_formatted}&o={order_id}&s={sign}"
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=f"🛒 *НОВЫЙ ЗАКАЗ!*\n\n📦 Заказ: #{order_number}\n👤 Пользователь: {user_id}\n💰 Сумма: {final_total:.2f} {CURRENCY_SYMBOL}\n📊 Статус: ожидает оплаты\n🕐 {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Ошибка уведомления админа: {e}")
            await query.edit_message_text(
                f"💳 *Оплата через FreeKassa*\n\n📦 Заказ: #{order_number}\n💰 Сумма: {total_formatted} {CURRENCY_SYMBOL}\n\n🔗 Нажми на кнопку для оплаты:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Перейти к оплате", url=payment_url)],
                    [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_order_{order_id}")],
                    [InlineKeyboardButton("🔙 Назад", callback_data="view_cart")]
                ]),
                parse_mode="Markdown"
            )
        
        elif data == "pay_manual":
            cart = self.db.get_cart(user_id)
            if not cart:
                await query.edit_message_text("❌ *Корзина пуста*", parse_mode="Markdown")
                return
            total = self.db.get_cart_total(user_id)
            discount = context.user_data.get("promocode_discount", 0)
            final_total = total * (1 - discount / 100) if discount > 0 else total
            order_id, order_number = self.db.create_order(user_id, cart, final_total, "manual")
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=f"🛒 *НОВЫЙ ЗАКАЗ!*\n\n📦 Заказ: #{order_number}\n👤 Пользователь: {user_id}\n💰 Сумма: {final_total:.2f} {CURRENCY_SYMBOL}\n📊 Статус: ожидает оплаты\n🕐 {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Ошибка уведомления админа: {e}")
            await query.edit_message_text(
                f"💳 *Оплата по реквизитам*\n\n"
                f"📦 Заказ: #{order_number}\n"
                f"💰 Сумма: {final_total:.2f} {CURRENCY_SYMBOL}\n\n"
                f"💳 *Реквизиты для оплаты:*\n"
                f"• Карта: `5208 1300 1478 8552`\n"
                f"• Получатель: Радабольский С.Н.\n"
                f"• Банк: Альфа-Банк\n\n"
                f"📌 *В назначении платежа укажи:* `Заказ #{order_number}`\n\n"
                f"⏳ После оплаты нажми «✅ Я оплатил» и администратор подтвердит заказ.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Я оплатил", callback_data=f"manual_paid_{order_id}")],
                    [InlineKeyboardButton("🔙 Назад", callback_data="view_cart")]
                ]),
                parse_mode="Markdown"
            )
        
        elif data == "pay_cryptobot":
            cart = self.db.get_cart(user_id)
            if not cart:
                await query.edit_message_text("❌ *Корзина пуста*", parse_mode="Markdown")
                return
            total = self.db.get_cart_total(user_id)
            order_id, order_number = self.db.create_order(user_id, cart, total, "cryptobot")
            usdt_amount = self.currency.rub_to_usdt(total)
            await query.edit_message_text(
                f"🪙 *Оплата через CryptoBot*\n\n"
                f"📦 Заказ: #{order_number}\n"
                f"💰 Сумма: {total:.2f} {CURRENCY_SYMBOL} ≈ {usdt_amount:.2f} USDT\n\n"
                f"1️⃣ Напишите @CryptoBot\n"
                f"2️⃣ Нажмите «Создать счёт»\n"
                f"3️⃣ Введите сумму: {usdt_amount:.2f} USDT\n"
                f"4️⃣ Отправьте счёт пользователю\n\n"
                f"После оплаты нажмите «✅ Я оплатил»",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🤖 Перейти в CryptoBot", url=CRYPTOBOT_LINK)],
                    [InlineKeyboardButton("✅ Я оплатил", callback_data=f"manual_paid_{order_id}")],
                    [InlineKeyboardButton("🔙 Назад", callback_data="view_cart")]
                ]),
                parse_mode="Markdown"
            )
        
        elif data.startswith("manual_paid_"):
            order_id = int(data.replace("manual_paid_", ""))
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=f"💰 *Новый запрос на подтверждение оплаты!*\n\n📦 Заказ: #{order_id}\n👤 Пользователь: {user_id}\n⏳ Ждёт подтверждения.\n\nИспользуй кнопку в админ-панели для подтверждения.",
                        parse_mode="Markdown"
                    )
                except:
                    pass
            await query.edit_message_text(
                f"✅ *Заявка на оплату отправлена!*\n\n"
                f"📦 Заказ: #{order_id}\n"
                f"⏳ Администратор проверит оплату и подтвердит заказ.\n\n"
                f"Спасибо за ожидание! 🙏",
                parse_mode="Markdown"
            )
        
        elif data.startswith("check_order_"):
            order_id = int(data.replace("check_order_", ""))
            order = self.db.get_order(order_id)
            if not order:
                await query.edit_message_text("❌ *Заказ не найден*", parse_mode="Markdown")
                return
            if order['status'] == "paid":
                await query.edit_message_text("✅ *Заказ оплачен!*\n\nСпасибо за покупку! 🎉", parse_mode="Markdown")
            elif order['status'] == "pending":
                await query.edit_message_text("⏳ *Заказ ожидает подтверждения оплаты*\n\nАдминистратор проверит оплату в ближайшее время.", parse_mode="Markdown")
            else:
                await query.edit_message_text(f"📊 *Статус заказа:* {order['status']}", parse_mode="Markdown")
        
        elif data == "admin":
            await self.admin_command(update, context)
        
        elif data == "admin_products":
            products = self.db.get_products(limit=100)
            if not products:
                text = "📦 *Товаров пока нет*"
            else:
                text = "📦 *Товары:*\n\n"
                for p in products[:20]:
                    digital = "🖥️ " if p.get('is_digital') else ""
                    usdt_price = self.currency.rub_to_usdt(p['price'])
                    text += f"• {digital}{p['name']} — {p['price']:.2f} {CURRENCY_SYMBOL} (~{usdt_price:.2f} USDT) (в наличии: {p['stock']})\n"
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
        elif data == "admin_add_product":
            context.user_data["admin_mode"] = "add_product"
            await query.edit_message_text(
                "📝 *Добавление товара*\n\n"
                "Отправь данные в формате:\n"
                "`Название | Описание | Цена | Категория | Количество | is_digital | ссылка`\n\n"
                "Примеры:\n"
                "`CEF Сборка Pro | Максимальная мощность | 4999 | CEF Сборки | 999`\n"
                "`Курс по CEF | Полный гайд | 999 | CEF Сборки | 999 | True | https://example.com/file.zip`\n\n"
                "Для цифровых товаров: is_digital = True, ссылка на файл\n"
                "Для отмены отправь /cancel",
                parse_mode="Markdown"
            )
        
        elif data == "admin_add_promocode":
            context.user_data["admin_mode"] = "add_promocode"
            await query.edit_message_text(
                "🎁 *Добавление промокода*\n\n"
                "Отправь данные в формате:\n"
                "`КОД | СКИДКА% | МАКС_ИСПОЛЬЗОВАНИЙ`\n\n"
                "Пример:\n"
                "`WELCOME10 | 10 | 50`\n\n"
                "Для отмены отправь /cancel",
                parse_mode="Markdown"
            )
        
        elif data.startswith("admin_delete_product_"):
            if user_id not in ADMIN_IDS:
                await query.edit_message_text("⛔ *Нет доступа*", parse_mode="Markdown")
                return
            product_id = int(data.replace("admin_delete_product_", ""))
            product = self.db.get_product(product_id)
            if product:
                self.db.delete_product(product_id)
                await query.edit_message_text(f"✅ *Товар удалён:* {product['name']}", parse_mode="Markdown")
            else:
                await query.edit_message_text("❌ *Товар не найден*", parse_mode="Markdown")
        
        elif data == "admin_orders":
            orders = self.db.get_orders()
            if not orders:
                text = "📋 *Нет заказов*"
            else:
                text = "📋 *Последние заказы:*\n\n"
                for order in orders[:10]:
                    status_emoji = "✅" if order['status'] == "paid" else "⏳"
                    text += f"📦 #{order['order_number']} — {order['total']:.2f} {CURRENCY_SYMBOL} — {status_emoji} {order['status']}\n"
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
        elif data == "admin_confirm_payment":
            pending_orders = self.db.get_pending_orders()
            if not pending_orders:
                await query.edit_message_text("📋 *Нет заказов, ожидающих подтверждения*", parse_mode="Markdown")
                return
            text = "💳 *Заказы на подтверждение:*\n\n"
            keyboard = []
            for order in pending_orders[:10]:
                text += f"📦 #{order['order_number']} — {order['total']:.2f} {CURRENCY_SYMBOL}\n"
                keyboard.append([InlineKeyboardButton(
                    f"✅ Подтвердить #{order['order_number']}",
                    callback_data=f"admin_confirm_{order['id']}"
                )])
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin")])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
        elif data.startswith("admin_confirm_"):
            if user_id not in ADMIN_IDS:
                await query.edit_message_text("⛔ *Нет доступа*", parse_mode="Markdown")
                return
            order_id = int(data.replace("admin_confirm_", ""))
            order = self.db.get_order(order_id)
            if not order:
                await query.edit_message_text("❌ *Заказ не найден*", parse_mode="Markdown")
                return
            self.db.update_order_status(order_id, "paid")
            bonus_points = int(order['total'] * 5)
            self.db.add_bonus(order['user_id'], bonus_points)
            digital_links = []
            for item in order['items']:
                product = self.db.get_product(item["product_id"])
                if product and product.get('is_digital') and product.get('digital_content'):
                    digital_links.append(f"• {product['name']}: {product['digital_content']}")
            try:
                user_text = f"✅ *Ваш заказ #{order['order_number']} подтверждён и оплачен!*\n\nСпасибо за покупку! 🎉"
                if digital_links:
                    user_text += f"\n\n📦 *Цифровые товары:*\n\n" + "\n".join(digital_links)
                user_text += f"\n\n💎 *Начислено бонусов:* {bonus_points}"
                await context.bot.send_message(
                    chat_id=order['user_id'],
                    text=user_text,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Ошибка уведомления пользователя: {e}")
            await query.edit_message_text(f"✅ *Заказ #{order['order_number']} подтверждён!*\n\n💎 Начислено бонусов: {bonus_points}", parse_mode="Markdown")
            await self.admin_command(update, context)
        
        elif data == "admin_stats":
            stats = self.db.get_stats()
            text = f"📊 *Статистика*\n\n"
            text += f"👥 Пользователей: {stats['total_users']}\n"
            text += f"📦 Заказов: {stats['total_orders']}\n"
            text += f"💰 Выручка: {stats['total_revenue']:.2f} {CURRENCY_SYMBOL}\n"
            text += f"📅 Заказов сегодня: {stats['today_orders']}\n"
            text += f"📦 Товаров в наличии: {stats['in_stock']}"
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text
        
        if context.user_data.get("admin_mode") == "add_product":
            if user_id not in ADMIN_IDS:
                await update.message.reply_text("⛔ *Нет доступа*", parse_mode="Markdown")
                context.user_data["admin_mode"] = None
                return
            if text == "/cancel":
                context.user_data["admin_mode"] = None
                await update.message.reply_text("❌ *Добавление отменено*", parse_mode="Markdown")
                return
            parts = text.split("|")
            if len(parts) < 5:
                await update.message.reply_text(
                    "❌ *Неверный формат*\n\n"
                    "Нужно: `Название | Описание | Цена | Категория | Количество | is_digital | ссылка`\n\n"
                    "Пример:\n"
                    "`CEF Сборка Pro | Максимальная мощность | 4999 | CEF Сборки | 999`\n"
                    "`Курс по CEF | Полный гайд | 999 | CEF Сборки | 999 | True | https://example.com/file.zip`",
                    parse_mode="Markdown"
                )
                return
            try:
                name = parts[0].strip()
                description = parts[1].strip()
                price = float(parts[2].strip())
                category = parts[3].strip()
                stock = int(parts[4].strip())
                is_digital = False
                digital_content = None
                if len(parts) >= 7:
                    is_digital = parts[5].strip().lower() == "true"
                    digital_content = parts[6].strip()
                product_id = self.db.add_product(name, description, price, category, stock=stock, 
                                                  is_digital=is_digital, digital_content=digital_content)
                context.user_data["admin_mode"] = None
                await update.message.reply_text(
                    f"✅ *Товар добавлен!*\n\n"
                    f"📦 {name}\n"
                    f"💰 {price:.2f} {CURRENCY_SYMBOL}\n"
                    f"📂 {category}\n"
                    f"📊 В наличии: {stock}\n"
                    f"🖥️ Цифровой: {is_digital}\n"
                    f"🆔 ID: {product_id}",
                    parse_mode="Markdown"
                )
            except Exception as e:
                await update.message.reply_text(f"❌ *Ошибка:* {str(e)}", parse_mode="Markdown")
            return
        
        if context.user_data.get("admin_mode") == "add_promocode":
            if user_id not in ADMIN_IDS:
                await update.message.reply_text("⛔ *Нет доступа*", parse_mode="Markdown")
                context.user_data["admin_mode"] = None
                return
            if text == "/cancel":
                context.user_data["admin_mode"] = None
                await update.message.reply_text("❌ *Добавление отменено*", parse_mode="Markdown")
                return
            parts = text.split("|")
            if len(parts) < 3:
                await update.message.reply_text(
                    "❌ *Неверный формат*\n\n"
                    "Нужно: `КОД | СКИДКА% | МАКС_ИСПОЛЬЗОВАНИЙ`\n\n"
                    "Пример:\n"
                    "`WELCOME10 | 10 | 50`",
                    parse_mode="Markdown"
                )
                return
            try:
                code = parts[0].strip().upper()
                discount = int(parts[1].strip())
                max_uses = int(parts[2].strip())
                self.db.add_promocode(code, discount, None, max_uses)
                context.user_data["admin_mode"] = None
                await update.message.reply_text(
                    f"✅ *Промокод добавлен!*\n\n"
                    f"🎁 Код: `{code}`\n"
                    f"📊 Скидка: {discount}%\n"
                    f"📊 Макс. использований: {max_uses}",
                    parse_mode="Markdown"
                )
            except Exception as e:
                await update.message.reply_text(f"❌ *Ошибка:* {str(e)}", parse_mode="Markdown")
            return
        
        if context.user_data.get("awaiting_promocode"):
            code = text.strip().upper()
            result = self.db.apply_promocode(code)
            if result["success"]:
                discount = result["discount"]
                context.user_data["promocode_discount"] = discount
                context.user_data["awaiting_promocode"] = False
                await update.message.reply_text(
                    f"✅ *Промокод применён!*\n\n"
                    f"🎁 Скидка: {discount}%\n\n"
                    f"Перейдите в корзину для оформления заказа.",
                    parse_mode="Markdown"
                )
                await self.show_cart(update, user_id, context)
            else:
                await update.message.reply_text(f"❌ {result['error']}", parse_mode="Markdown")
            return
        
        await update.message.reply_text("❓ Используй кнопки или команды: /start, /catalog, /help")

# ========== ЗАПУСК ==========

if __name__ == "__main__":
    bot = SalesBot(BOT_TOKEN)
    bot.start()
