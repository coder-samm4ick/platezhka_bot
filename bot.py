#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
💀 KVEZOVTEAM SALES BOT v3.0
Telegram-бот для продажи товаров/услуг
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = "8896855591:AAF837-w09REedQe2RCSzSJhlhT7BKUrEQ0"  # Заменить на реальный токен
ADMIN_IDS = [8563327706, 8563327706]  # ID админов (заменить)
CHANNEL_ID = -1003934163183  # ID канала для уведомлений (опционально)

# Настройки оплаты
PAYMENT_PROVIDER_TOKEN = "UQB1aDv_cBgRjodfmMfTpRZsmaV0t2mPeCJa_H5gmhAhrhiE"  # Для Telegram Payments
CRYPTO_WALLET = "UQB1aDv_cBgRjodfmMfTpRZsmaV0t2mPeCJa_H5gmhAhrhiE"  # Крипто-кошелёк (опционально)

# Настройки логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("sales_bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ========== БАЗА ДАННЫХ ==========

class Database:
    def __init__(self, db_path="sales_bot.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Инициализация всех таблиц"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Товары
        c.execute("""
            CREATE TABLE IF NOT EXISTS products (
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
            )
        """)
        
        # Категории
        c.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                emoji TEXT,
                sort_order INTEGER DEFAULT 0
            )
        """)
        
        # Пользователи
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                phone TEXT,
                balance REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP
            )
        """)
        
        # Корзина
        c.execute("""
            CREATE TABLE IF NOT EXISTS cart (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                product_id INTEGER,
                quantity INTEGER DEFAULT 1,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)
        
        # Заказы
        c.execute("""
            CREATE TABLE IF NOT EXISTS orders (
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
            )
        """)
        
        # Промокоды
        c.execute("""
            CREATE TABLE IF NOT EXISTS promocodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                discount_percent INTEGER,
                active BOOLEAN DEFAULT 1,
                expires_at TIMESTAMP,
                max_uses INTEGER DEFAULT 1,
                used_count INTEGER DEFAULT 0
            )
        """)
        
        # Отзывы
        c.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                product_id INTEGER,
                rating INTEGER CHECK(rating >= 1 AND rating <= 5),
                text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("База данных инициализирована")
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    # ========== ТОВАРЫ ==========
    
    def add_product(self, name, description, price, category=None, image_url=None, 
                   stock=999, is_digital=False, digital_content=None):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("""
            INSERT INTO products 
            (name, description, price, category, image_url, stock, is_digital, digital_content)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, description, price, category, image_url, stock, is_digital, digital_content))
        product_id = c.lastrowid
        conn.commit()
        conn.close()
        return product_id
    
    def get_products(self, category=None, limit=50):
        conn = self.get_connection()
        c = conn.cursor()
        if category:
            c.execute("""
                SELECT id, name, description, price, category, image_url, stock, is_digital
                FROM products 
                WHERE category = ? AND stock > 0
                ORDER BY id DESC LIMIT ?
            """, (category, limit))
        else:
            c.execute("""
                SELECT id, name, description, price, category, image_url, stock, is_digital
                FROM products 
                WHERE stock > 0
                ORDER BY id DESC LIMIT ?
            """, (limit,))
        products = [{
            "id": row[0], "name": row[1], "description": row[2],
            "price": row[3], "category": row[4], "image_url": row[5],
            "stock": row[6], "is_digital": row[7]
        } for row in c.fetchall()]
        conn.close()
        return products
    
    def get_product(self, product_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT id, name, description, price, category, image_url, stock, is_digital, digital_content
            FROM products WHERE id = ?
        """, (product_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return {
                "id": row[0], "name": row[1], "description": row[2],
                "price": row[3], "category": row[4], "image_url": row[5],
                "stock": row[6], "is_digital": row[7], "digital_content": row[8]
            }
        return None
    
    def update_product(self, product_id, **kwargs):
        conn = self.get_connection()
        c = conn.cursor()
        fields = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [product_id]
        c.execute(f"UPDATE products SET {fields} WHERE id = ?", values)
        conn.commit()
        conn.close()
    
    def delete_product(self, product_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()
        conn.close()
    
    # ========== КАТЕГОРИИ ==========
    
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
    
    # ========== ПОЛЬЗОВАТЕЛИ ==========
    
    def register_user(self, user_id, username=None, first_name=None, last_name=None):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("""
            INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        """, (user_id, username, first_name, last_name))
        conn.commit()
        conn.close()
    
    def get_user(self, user_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return {
                "user_id": row[0], "username": row[1], "first_name": row[2],
                "last_name": row[3], "phone": row[4], "balance": row[5],
                "created_at": row[6], "last_activity": row[7]
            }
        return None
    
    # ========== КОРЗИНА ==========
    
    def add_to_cart(self, user_id, product_id, quantity=1):
        conn = self.get_connection()
        c = conn.cursor()
        
        # Проверяем, есть ли уже в корзине
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
            SELECT c.product_id, p.name, p.price, c.quantity, p.is_digital, p.stock
            FROM cart c
            JOIN products p ON c.product_id = p.id
            WHERE c.user_id = ?
        """, (user_id,))
        cart = [{
            "product_id": row[0], "name": row[1], "price": row[2],
            "quantity": row[3], "is_digital": row[4], "stock": row[5]
        } for row in c.fetchall()]
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
    
    # ========== ЗАКАЗЫ ==========
    
    def create_order(self, user_id, items, total, payment_method, payment_id=None):
        conn = self.get_connection()
        c = conn.cursor()
        
        # Генерируем номер заказа
        order_number = f"ORD-{datetime.now().strftime('%Y%m%d')}-{user_id}-{int(datetime.now().timestamp()) % 1000}"
        
        c.execute("""
            INSERT INTO orders (order_number, user_id, items, total, payment_method, payment_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (order_number, user_id, json.dumps(items), total, payment_method, payment_id))
        
        order_id = c.lastrowid
        
        # Очищаем корзину
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
    
    def get_orders(self, user_id=None, status=None, limit=50):
        conn = self.get_connection()
        c = conn.cursor()
        
        query = "SELECT id, order_number, items, total, status, created_at FROM orders"
        params = []
        
        if user_id:
            query += " WHERE user_id = ?"
            params.append(user_id)
            if status:
                query += " AND status = ?"
                params.append(status)
        elif status:
            query += " WHERE status = ?"
            params.append(status)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        c.execute(query, params)
        orders = [{
            "id": row[0], "order_number": row[1], "items": json.loads(row[2]),
            "total": row[3], "status": row[4], "created_at": row[5]
        } for row in c.fetchall()]
        conn.close()
        return orders
    
    # ========== ПРОМОКОДЫ ==========
    
    def apply_promocode(self, code, user_id):
        conn = self.get_connection()
        c = conn.cursor()
        
        c.execute("""
            SELECT id, discount_percent, max_uses, used_count, expires_at
            FROM promocodes 
            WHERE code = ? AND active = 1
        """, (code,))
        row = c.fetchone()
        
        if not row:
            conn.close()
            return {"success": False, "error": "Промокод не найден"}
        
        promo_id, discount, max_uses, used_count, expires_at = row
        
        # Проверяем срок действия
        if expires_at and datetime.now() > datetime.fromisoformat(expires_at):
            conn.close()
            return {"success": False, "error": "Промокод истёк"}
        
        # Проверяем лимит использований
        if used_count >= max_uses:
            conn.close()
            return {"success": False, "error": "Промокод уже использован максимальное количество раз"}
        
        # Обновляем счётчик
        c.execute("UPDATE promocodes SET used_count = used_count + 1 WHERE id = ?", (promo_id,))
        conn.commit()
        conn.close()
        
        return {"success": True, "discount": discount}
    
    # ========== СТАТИСТИКА ==========
    
    def get_stats(self):
        conn = self.get_connection()
        c = conn.cursor()
        
        # Всего пользователей
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        
        # Всего заказов
        c.execute("SELECT COUNT(*) FROM orders")
        total_orders = c.fetchone()[0]
        
        # Выручка
        c.execute("SELECT SUM(total) FROM orders WHERE status != 'cancelled'")
        total_revenue = c.fetchone()[0] or 0
        
        # Заказов сегодня
        today = datetime.now().date().isoformat()
        c.execute("SELECT COUNT(*) FROM orders WHERE DATE(created_at) = ?", (today,))
        today_orders = c.fetchone()[0]
        
        # Товаров в наличии
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

# ========== ИНИЦИАЛИЗАЦИЯ БАЗЫ ==========
db = Database()

# Добавляем тестовые категории
db.add_category("Электроника", "💻")
db.add_category("Одежда", "👕")
db.add_category("Цифровые товары", "🎮")
db.add_category("Услуги", "⚡")

# Добавляем тестовые товары
if not db.get_products():
    db.add_product(
        "iPhone 15 Pro Max",
        "Самый мощный смартфон Apple с титановым корпусом",
        1299.99,
        "Электроника",
        "https://example.com/iphone.jpg",
        10
    )
    db.add_product(
        "Футболка с принтом",
        "Качественная футболка из хлопка с уникальным дизайном",
        29.99,
        "Одежда",
        "https://example.com/tshirt.jpg",
        50
    )
    db.add_product(
        "Курс по Python",
        "Полный курс по Python от новичка до профи",
        99.99,
        "Цифровые товары",
        None,
        999,
        True,
        "https://example.com/course.zip"
    )
    db.add_product(
        "Разработка сайта под ключ",
        "Профессиональная разработка сайта любой сложности",
        499.99,
        "Услуги",
        None,
        20
    )

# ========== БОТ ==========

class SalesBot:
    def __init__(self, token):
        self.token = token
        self.db = db
        self.application = None
    
    def start(self):
        """Запуск бота"""
        self.application = Application.builder().token(self.token).build()
        
        # Команды
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("catalog", self.catalog_command))
        self.application.add_handler(CommandHandler("cart", self.cart_command))
        self.application.add_handler(CommandHandler("orders", self.orders_command))
        self.application.add_handler(CommandHandler("profile", self.profile_command))
        self.application.add_handler(CommandHandler("admin", self.admin_command))
        
        # Callback'и
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Сообщения (для приёма текста)
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Запуск
        logger.info("Бот запущен!")
        self.application.run_polling()
    
    # ========== КОМАНДЫ ==========
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        self.db.register_user(
            user.id,
            user.username,
            user.first_name,
            user.last_name
        )
        
        text = f"""
🛍️ *Добро пожаловать в наш магазин!*

Мы рады видеть тебя, {user.first_name}! 👋

Здесь ты найдёшь:
• 🔥 *Только качественные товары*
• 💰 *Лучшие цены*
• 🚀 *Быструю доставку*
• ⭐ *Гарантию качества*

Что тебя интересует?
        """
        
        keyboard = [
            [InlineKeyboardButton("📦 Каталог", callback_data="catalog")],
            [InlineKeyboardButton("🛒 Корзина", callback_data="view_cart")],
            [InlineKeyboardButton("📋 Мои заказы", callback_data="my_orders")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = """
❓ *Помощь и инструкция*

📌 *Основные команды:*
• /start - Главное меню
• /catalog - Показать каталог
• /cart - Корзина
• /orders - Мои заказы
• /profile - Профиль

🛒 *Как сделать заказ:*
1. Выбери товар в каталоге
2. Добавь в корзину
3. Оформи заказ
4. Оплати

💬 *Вопросы?*
Напиши нам: @support_username
        """
        
        await update.message.reply_text(text, parse_mode="Markdown")
    
    async def catalog_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        categories = self.db.get_categories()
        
        if not categories:
            await update.message.reply_text("📦 *Каталог временно пуст*")
            return
        
        keyboard = []
        for cat in categories:
            keyboard.append([InlineKeyboardButton(
                f"{cat['emoji']} {cat['name']}",
                callback_data=f"category_{cat['name']}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔄 Все товары", callback_data="category_all")])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
        
        await update.message.reply_text(
            "📦 *Каталог товаров*\n\nВыбери категорию:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    async def cart_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        await self.show_cart(update, user_id)
    
    async def orders_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        orders = self.db.get_orders(user_id=user_id, limit=20)
        
        if not orders:
            await update.message.reply_text("📋 *У вас пока нет заказов*", parse_mode="Markdown")
            return
        
        text = "📋 *Ваши заказы:*\n\n"
        for order in orders[:5]:
            text += f"📦 #{order['order_number']}\n"
            text += f"💰 {order['total']:.2f} $\n"
            text += f"📊 Статус: {self.get_status_emoji(order['status'])} {order['status']}\n"
            text += f"📅 {order['created_at'][:10]}\n\n"
        
        await update.message.reply_text(text, parse_mode="Markdown")
    
    async def profile_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user = self.db.get_user(user_id)
        
        if not user:
            await update.message.reply_text("❌ Пользователь не найден")
            return
        
        text = f"""
👤 *Профиль*

• ID: `{user['user_id']}`
• Имя: {user['first_name'] or 'Не указано'}
• Username: @{user['username'] or 'Не указан'}
• Баланс: {user['balance']:.2f} $
• Дата регистрации: {user['created_at'][:10]}
        """
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]]
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("⛔ *У вас нет доступа к админ-панели*", parse_mode="Markdown")
            return
        
        stats = self.db.get_stats()
        
        text = f"""
👑 *Админ-панель*

📊 *Статистика:*
• 👥 Пользователей: {stats['total_users']}
• 📦 Заказов: {stats['total_orders']}
• 💰 Выручка: {stats['total_revenue']:.2f} $
• 📅 Заказов сегодня: {stats['today_orders']}
• 📦 Товаров в наличии: {stats['in_stock']}

📌 *Что хочешь сделать?*
        """
        
        keyboard = [
            [InlineKeyboardButton("📦 Управление товарами", callback_data="admin_products")],
            [InlineKeyboardButton("📋 Заказы", callback_data="admin_orders")],
            [InlineKeyboardButton("➕ Добавить товар", callback_data="admin_add_product")],
            [InlineKeyboardButton("📊 Полная статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]
        ]
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    # ========== ОБРАБОТКА CALLBACK ==========
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = query.from_user.id
        
        if data == "back_to_menu":
            await self.start_command(update, context)
        
        elif data == "catalog":
            await self.catalog_command(update, context)
        
        elif data == "view_cart":
            await self.show_cart(update, user_id)
        
        elif data == "my_orders":
            await self.orders_command(update, context)
        
        elif data == "help":
            await self.help_command(update, context)
        
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
            await self.show_cart(update, user_id)
        
        elif data == "clear_cart":
            self.db.clear_cart(user_id)
            await self.show_cart(update, user_id)
        
        elif data == "checkout":
            await self.checkout(update, user_id)
        
        elif data.startswith("order_status_"):
            order_id = int(data.replace("order_status_", ""))
            new_status = data.split("_")[2]
            self.db.update_order_status(order_id, new_status)
            await query.edit_message_text(f"✅ Статус заказа обновлён на: {new_status}")
        
        # Админские
        elif data == "admin_products":
            await self.admin_products(update)
        
        elif data == "admin_orders":
            await self.admin_orders(update)
        
        elif data == "admin_add_product":
            context.user_data["admin_mode"] = "add_product"
            await query.edit_message_text(
                "📝 *Добавление товара*\n\n"
                "Введи название товара:",
                parse_mode="Markdown"
            )
        
        elif data == "admin_stats":
            stats = self.db.get_stats()
            text = f"""
📊 *Полная статистика*

👥 *Пользователи:* {stats['total_users']}
📦 *Заказов:* {stats['total_orders']}
💰 *Выручка:* {stats['total_revenue']:.2f} $
📅 *Заказов сегодня:* {stats['today_orders']}
📦 *Товаров в наличии:* {stats['in_stock']}
            """
            await query.edit_message_text(text, parse_mode="Markdown")
    
    # ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
    
    async def show_products(self, update: Update, category=None):
        products = self.db.get_products(category, limit=20)
        
        if not products:
            text = "📦 *В этой категории пока нет товаров*"
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="catalog")]]
            await update.callback_query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return
        
        text = f"📦 *Каталог товаров*\n\n"
        
        keyboard = []
        for product in products:
            text += f"🔹 *{product['name']}*\n"
            text += f"💰 {product['price']:.2f} $\n"
            if product['stock'] < 10:
                text += f"⚠️ Осталось: {product['stock']} шт.\n"
            text += "\n"
            
            keyboard.append([InlineKeyboardButton(
                f"👉 {product['name']}",
                callback_data=f"product_{product['id']}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="catalog")])
        
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    async def show_product_detail(self, update: Update, product_id):
        product = self.db.get_product(product_id)
        
        if not product:
            await update.callback_query.edit_message_text("❌ Товар не найден")
            return
        
        text = f"""
🛍️ *{product['name']}*

📝 {product['description']}

💰 *Цена:* {product['price']:.2f} $
📦 *В наличии:* {product['stock']} шт.
📂 *Категория:* {product['category'] or 'Без категории'}

{'🖥️ *Цифровой товар* — выдача моментальная' if product['is_digital'] else ''}
        """
        
        keyboard = [
            [InlineKeyboardButton("🛒 Добавить в корзину", callback_data=f"add_to_cart_{product_id}")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"category_{product['category'] or 'all'}")]
        ]
        
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    async def show_cart(self, update: Update, user_id):
        cart = self.db.get_cart(user_id)
        
        if not cart:
            text = "🛒 *Ваша корзина пуста*"
            keyboard = [[InlineKeyboardButton("📦 В каталог", callback_data="catalog")]]
            await update.callback_query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            ) if update.callback_query else await update.message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return
        
        text = "🛒 *Ваша корзина:*\n\n"
        total = 0
        
        keyboard = []
        for item in cart:
            subtotal = item["price"] * item["quantity"]
            total += subtotal
            text += f"• {item['name']} × {item['quantity']} = {subtotal:.2f} $\n"
            keyboard.append([InlineKeyboardButton(
                f"❌ Убрать {item['name']}",
                callback_data=f"remove_from_cart_{item['product_id']}"
            )])
        
        text += f"\n💰 *Итого:* {total:.2f} $"
        
        keyboard.append([InlineKeyboardButton("🔄 Очистить корзину", callback_data="clear_cart")])
        keyboard.append([InlineKeyboardButton("✅ Оформить заказ", callback_data="checkout")])
        keyboard.append([InlineKeyboardButton("🔙 В каталог", callback_data="catalog")])
        
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        ) if update.callback_query else await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    async def checkout(self, update: Update, user_id):
        cart = self.db.get_cart(user_id)
        
        if not cart:
            await update.callback_query.edit_message_text("❌ *Корзина пуста*", parse_mode="Markdown")
            return
        
        total = self.db.get_cart_total(user_id)
        
        text = f"""
💳 *Оформление заказа*

📦 *Товары:*
"""
        for item in cart:
            text += f"• {item['name']} × {item['quantity']} = {item['price'] * item['quantity']:.2f} $\n"
        
        text += f"\n💰 *Итого:* {total:.2f} $"
        text += "\n\n📌 *Выбери способ оплаты:*"
        
        keyboard = [
            [InlineKeyboardButton("💳 Telegram Payments", callback_data="pay_telegram")],
            [InlineKeyboardButton("🪙 Криптовалюта", callback_data="pay_crypto")],
            [InlineKeyboardButton("📱 СБП", callback_data="pay_sbp")]
        ]
        
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    async def admin_products(self, update: Update):
        products = self.db.get_products(limit=100)
        
        text = "📦 *Управление товарами*\n\n"
        
        keyboard = []
        for p in products[:20]:
            text += f"• {p['name']} — {p['price']:.2f} $ (в наличии: {p['stock']})\n"
            keyboard.append([InlineKeyboardButton(
                f"✏️ {p['name']}",
                callback_data=f"admin_edit_product_{p['id']}"
            )])
        
        keyboard.append([InlineKeyboardButton("➕ Добавить товар", callback_data="admin_add_product")])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin")])
        
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    async def admin_orders(self, update: Update):
        orders = self.db.get_orders(limit=20)
        
        if not orders:
            text = "📋 *Нет заказов*"
        else:
            text = "📋 *Последние заказы:*\n\n"
            for order in orders:
                text += f"📦 #{order['order_number']}\n"
                text += f"💰 {order['total']:.2f} $\n"
                text += f"📊 {self.get_status_emoji(order['status'])} {order['status']}\n"
                text += f"📅 {order['created_at'][:10]}\n\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data="admin_orders")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin")]
        ]
        
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text
        
        # Режим админа (добавление товара)
        if context.user_data.get("admin_mode") == "add_product":
            # Простая обработка, можно расширить
            await update.message.reply_text("✅ Товар добавлен! (заглушка)")
            context.user_data["admin_mode"] = None
            return
    
    def get_status_emoji(self, status):
        emojis = {
            "pending": "⏳",
            "paid": "✅",
            "shipped": "🚚",
            "delivered": "📦",
            "cancelled": "❌"
        }
        return emojis.get(status, "❓")

# ========== ЗАПУСК ==========

if __name__ == "__main__":
    bot = SalesBot(BOT_TOKEN)
    bot.start()