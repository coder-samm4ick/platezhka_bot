#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import sqlite3
import logging
import hashlib
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
BOT_USERNAME = "platezhka_robot"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ========== БАЗА ДАННЫХ ==========

class Database:
    def __init__(self, db_path="sales_bot.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
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
        c.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                emoji TEXT,
                sort_order INTEGER DEFAULT 0
            )
        """)
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
        conn.commit()
        conn.close()
        logger.info("База данных инициализирована")
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    # ===== КАТЕГОРИИ =====
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
    
    # ===== ТОВАРЫ =====
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
            c.execute("""SELECT id, name, description, price, category, image_url, stock, is_digital 
                        FROM products WHERE category = ? AND stock > 0 ORDER BY id DESC LIMIT ?""", (category, limit))
        else:
            c.execute("""SELECT id, name, description, price, category, image_url, stock, is_digital 
                        FROM products WHERE stock > 0 ORDER BY id DESC LIMIT ?""", (limit,))
        products = [{"id": row[0], "name": row[1], "description": row[2], "price": row[3], 
                     "category": row[4], "image_url": row[5], "stock": row[6], "is_digital": row[7]} 
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
    
    # ===== ПОЛЬЗОВАТЕЛИ =====
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
                    "created_at": row[6], "last_activity": row[7]}
        return None
    
    # ===== КОРЗИНА =====
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
            SELECT c.product_id, p.name, p.price, c.quantity, p.is_digital, p.stock
            FROM cart c JOIN products p ON c.product_id = p.id WHERE c.user_id = ?
        """, (user_id,))
        cart = [{"product_id": row[0], "name": row[1], "price": row[2], 
                 "quantity": row[3], "is_digital": row[4], "stock": row[5]} 
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
    
    # ===== ЗАКАЗЫ =====
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
    
    # ===== СТАТИСТИКА =====
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

# Добавляем категории
db.add_category("Электроника", "💻")
db.add_category("Одежда", "👕")
db.add_category("Цифровые товары", "🎮")
db.add_category("Услуги", "⚡")

# Добавляем тестовые товары
if not db.get_products():
    db.add_product("iPhone 15 Pro Max", "Самый мощный смартфон Apple", 1299.99, "Электроника", None, 10)
    db.add_product("Футболка с принтом", "Качественная футболка", 29.99, "Одежда", None, 50)
    db.add_product("Курс по Python", "Полный курс Python", 99.99, "Цифровые товары", None, 999, True, "https://example.com/course.zip")

# ========== БОТ ==========

class SalesBot:
    def __init__(self, token):
        self.token = token
        self.db = db
        self.application = None
    
    def start(self):
        self.application = Application.builder().token(self.token).build()
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("catalog", self.catalog_command))
        self.application.add_handler(CommandHandler("cart", self.cart_command))
        self.application.add_handler(CommandHandler("orders", self.orders_command))
        self.application.add_handler(CommandHandler("profile", self.profile_command))
        self.application.add_handler(CommandHandler("admin", self.admin_command))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        logger.info("🚀 Бот запущен!")
        self.application.run_polling()
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        self.db.register_user(user.id, user.username, user.first_name, user.last_name)
        text = f"🛍️ *Добро пожаловать в магазин!*\n\nМы рады видеть тебя, {user.first_name}! 👋\n\nЧто тебя интересует?"
        keyboard = [
            [InlineKeyboardButton("📦 Каталог", callback_data="catalog")],
            [InlineKeyboardButton("🛒 Корзина", callback_data="view_cart")],
            [InlineKeyboardButton("📋 Мои заказы", callback_data="my_orders")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = """
❓ *Помощь и инструкция*

📌 *Команды:* /start, /catalog, /cart, /orders, /profile, /admin (для админов)

🛒 *Как сделать заказ:*
1. Выбери товар
2. Добавь в корзину
3. Оформи заказ → оплата

💬 *Вопросы?* @support
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
        await self.show_cart(update, user_id)
    
    async def orders_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        orders = self.db.get_orders(user_id)
        if not orders:
            text = "📋 *У вас пока нет заказов*"
        else:
            text = "📋 *Ваши заказы:*\n\n"
            for order in orders[:5]:
                text += f"📦 #{order['order_number']}\n💰 {order['total']:.2f} $\n📊 Статус: {order['status']}\n📅 {order['created_at'][:10]}\n\n"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    async def profile_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user = self.db.get_user(user_id)
        if not user:
            await update.message.reply_text("❌ Пользователь не найден")
            return
        text = f"👤 *Профиль*\n\n• ID: `{user['user_id']}`\n• Имя: {user['first_name'] or 'Не указано'}\n• Username: @{user['username'] or 'Не указан'}\n• Баланс: {user['balance']:.2f} $\n• Дата: {user['created_at'][:10]}"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("⛔ *Нет доступа*", parse_mode="Markdown")
            return
        text = "👑 *Админ-панель*\n\n📌 Управление:"
        keyboard = [
            [InlineKeyboardButton("📦 Товары", callback_data="admin_products")],
            [InlineKeyboardButton("➕ Добавить товар", callback_data="admin_add_product")],
            [InlineKeyboardButton("📋 Заказы", callback_data="admin_orders")],
            [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]
        ]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
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
            text += f"🔹 *{p['name']}* — {p['price']:.2f} $\n"
            keyboard.append([InlineKeyboardButton(f"👉 {p['name']}", callback_data=f"product_{p['id']}")])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="catalog")])
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    async def show_product_detail(self, update: Update, product_id):
        product = self.db.get_product(product_id)
        if not product:
            await update.callback_query.edit_message_text("❌ Товар не найден")
            return
        text = f"🛍️ *{product['name']}*\n\n📝 {product['description']}\n💰 *Цена:* {product['price']:.2f} $\n📦 *В наличии:* {product['stock']} шт."
        keyboard = [
            [InlineKeyboardButton("🛒 Добавить в корзину", callback_data=f"add_to_cart_{product_id}")],
            [InlineKeyboardButton("🗑 Удалить товар", callback_data=f"admin_delete_product_{product_id}")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"category_{product['category'] or 'all'}")]
        ]
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    async def show_cart(self, update: Update, user_id):
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
            text += f"• {item['name']} × {item['quantity']} = {subtotal:.2f} $\n"
            keyboard.append([InlineKeyboardButton(f"❌ Убрать {item['name']}", callback_data=f"remove_from_cart_{item['product_id']}")])
        text += f"\n💰 *Итого:* {total:.2f} $"
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
            await self.show_cart(update, user_id)
        elif data == "my_orders":
            await self.orders_command(update, context)
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
            cart = self.db.get_cart(user_id)
            if not cart:
                await query.edit_message_text("❌ *Корзина пуста*", parse_mode="Markdown")
                return
            total = self.db.get_cart_total(user_id)
            text = f"💳 *Оформление заказа*\n\n💰 *Итого:* {total:.2f} $\n\nВыбери способ оплаты:"
            keyboard = [
                [InlineKeyboardButton("💳 FreeKassa", callback_data="pay_freekassa")],
                [InlineKeyboardButton("🔙 Назад", callback_data="view_cart")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
        elif data == "pay_freekassa":
            cart = self.db.get_cart(user_id)
            if not cart:
                await query.edit_message_text("❌ *Корзина пуста*", parse_mode="Markdown")
                return
            total = self.db.get_cart_total(user_id)
            order_id, order_number = self.db.create_order(user_id, cart, total, "freekassa")
            
            sign = hashlib.md5(f"{FREAKASSA_MERCHANT_ID}:{total:.2f}:{FREAKASSA_SECRET_KEY}:{order_id}".encode()).hexdigest()
            payment_url = f"https://pay.freekassa.ru/?m={FREAKASSA_MERCHANT_ID}&oa={total:.2f}&o={order_id}&s={sign}"
            
            await query.edit_message_text(
                f"💳 *Оплата через FreeKassa*\n\n📦 Заказ: #{order_number}\n💰 Сумма: {total:.2f} $\n\n🔗 Нажми на кнопку для оплаты:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Перейти к оплате", url=payment_url)],
                    [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_order_{order_id}")],
                    [InlineKeyboardButton("🔙 Назад", callback_data="view_cart")]
                ]),
                parse_mode="Markdown"
            )
        
        elif data.startswith("check_order_"):
            order_id = int(data.replace("check_order_", ""))
            conn = sqlite3.connect("sales_bot.db")
            c = conn.cursor()
            c.execute("SELECT status FROM orders WHERE id = ?", (order_id,))
            row = c.fetchone()
            conn.close()
            if row and row[0] == "paid":
                await query.edit_message_text("✅ *Заказ оплачен!*\n\nСпасибо за покупку! 🎉", parse_mode="Markdown")
            else:
                await query.edit_message_text("⏳ *Заказ ещё не оплачен*\n\nПожалуйста, завершите оплату или проверьте позже.", parse_mode="Markdown")
        
        # ===== АДМИНКА =====
        elif data == "admin":
            await self.admin_command(update, context)
        
        elif data == "admin_products":
            products = self.db.get_products(limit=100)
            if not products:
                text = "📦 *Товаров пока нет*"
            else:
                text = "📦 *Товары:*\n\n"
                for p in products[:20]:
                    text += f"• {p['name']} — {p['price']:.2f} $ (в наличии: {p['stock']})\n"
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
        elif data == "admin_add_product":
            context.user_data["admin_mode"] = "add_product"
            await query.edit_message_text(
                "📝 *Добавление товара*\n\n"
                "Отправь данные в формате:\n"
                "`Название | Описание | Цена | Категория | Количество`\n\n"
                "Пример:\n"
                "`Наушники | Беспроводные наушники | 199.99 | Электроника | 30`\n\n"
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
                    text += f"📦 #{order['order_number']} — {order['total']:.2f} $ — {order['status']}\n"
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
        elif data == "admin_stats":
            stats = self.db.get_stats()
            text = f"📊 *Статистика*\n\n"
            text += f"👥 Пользователей: {stats['total_users']}\n"
            text += f"📦 Заказов: {stats['total_orders']}\n"
            text += f"💰 Выручка: {stats['total_revenue']:.2f} $\n"
            text += f"📅 Заказов сегодня: {stats['today_orders']}\n"
            text += f"📦 Товаров в наличии: {stats['in_stock']}"
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text
        
        # Режим добавления товара (админ)
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
                    "Нужно: `Название | Описание | Цена | Категория | Количество`\n\n"
                    "Пример:\n"
                    "`Наушники | Беспроводные наушники | 199.99 | Электроника | 30`",
                    parse_mode="Markdown"
                )
                return
            
            try:
                name = parts[0].strip()
                description = parts[1].strip()
                price = float(parts[2].strip())
                category = parts[3].strip()
                stock = int(parts[4].strip())
                
                product_id = self.db.add_product(name, description, price, category, stock=stock)
                context.user_data["admin_mode"] = None
                
                await update.message.reply_text(
                    f"✅ *Товар добавлен!*\n\n"
                    f"📦 {name}\n"
                    f"💰 {price:.2f} $\n"
                    f"📂 {category}\n"
                    f"📊 В наличии: {stock}\n"
                    f"🆔 ID: {product_id}",
                    parse_mode="Markdown"
                )
            except Exception as e:
                await update.message.reply_text(f"❌ *Ошибка:* {str(e)}", parse_mode="Markdown")
            return
        
        # Обычные сообщения
        await update.message.reply_text("❓ Используй кнопки или команды: /start, /catalog, /help")

# ========== ЗАПУСК ==========

if __name__ == "__main__":
    bot = SalesBot(BOT_TOKEN)
    bot.start()
