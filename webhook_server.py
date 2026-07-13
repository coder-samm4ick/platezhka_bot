from flask import Flask, request, jsonify
from datetime import datetime
import json
import logging
import sqlite3
import os

app = Flask(__name__)

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db():
    """Подключение к базе данных"""
    conn = sqlite3.connect("sales_bot.db")
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    """Главная страница"""
    return jsonify({
        "status": "Server is running",
        "time": datetime.now().isoformat(),
        "service": "platezhka_bot"
    })

@app.route('/webhook/payment', methods=['GET'])
def payment_webhook_test():
    """Проверка работы вебхука (GET-запрос)"""
    return jsonify({
        "status": "Webhook is active!",
        "time": datetime.now().isoformat(),
        "message": "Send POST requests here for payment notifications"
    })

@app.route('/webhook/payment', methods=['POST'])
def payment_webhook():
    """Обработка уведомлений от FreeKassa (POST-запрос)"""
    try:
        # Получаем данные
        data = request.get_json()
        if not data:
            data = request.form.to_dict()
        
        logger.info(f"📥 Получен вебхук: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
        # Проверяем, есть ли order_id (FreeKassa может передавать MERCHANT_ORDER_ID)
        order_id = data.get('order_id') or data.get('MERCHANT_ORDER_ID')
        
        if order_id:
            # Обновляем статус заказа в БД
            conn = get_db()
            c = conn.cursor()
            c.execute(
                "UPDATE orders SET status = 'paid', updated_at = CURRENT_TIMESTAMP, payment_id = ? WHERE id = ?",
                (data.get('payment_id', ''), order_id)
            )
            conn.commit()
            conn.close()
            logger.info(f"✅ Заказ #{order_id} оплачен")
        else:
            logger.warning("⚠️ В запросе нет order_id")
        
        # Отвечаем FreeKassa, что всё принято
        return jsonify({"success": True, "message": "Webhook received"}), 200
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки вебхука: {e}")
        return jsonify({"error": str(e)}), 400

@app.route('/success', methods=['GET'])
def payment_success():
    """Страница успешной оплаты"""
    order_id = request.args.get('order_id', 'неизвестен')
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>✅ Оплата успешна!</title>
        <meta charset="utf-8">
        <meta http-equiv="refresh" content="5;url=https://t.me/platezhka_robot">
        <style>
            body {{
                font-family: Arial, sans-serif;
                text-align: center;
                padding: 50px;
                background: #0a0a1a;
                color: #00ff88;
            }}
            h1 {{ font-size: 48px; }}
            .order {{ color: #aaa; margin: 20px 0; }}
            .btn {{
                background: #00ff88;
                color: #000;
                padding: 12px 30px;
                border-radius: 8px;
                text-decoration: none;
                display: inline-block;
            }}
            .btn:hover {{ background: #33ffaa; }}
        </style>
    </head>
    <body>
        <h1>✅ Оплата успешна!</h1>
        <p class="order">Заказ #{order_id} оплачен</p>
        <p>Спасибо за покупку! 🎉</p>
        <br>
        <a href="https://t.me/platezhka_robot" class="btn">⬅️ Вернуться в бота</a>
        <p><small>Вы будете перенаправлены через 5 секунд</small></p>
    </body>
    </html>
    """

@app.route('/fail', methods=['GET'])
def payment_fail():
    """Страница неудачной оплаты"""
    order_id = request.args.get('order_id', 'неизвестен')
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>❌ Ошибка оплаты</title>
        <meta charset="utf-8">
        <meta http-equiv="refresh" content="10;url=https://t.me/platezhka_robot">
        <style>
            body {{
                font-family: Arial, sans-serif;
                text-align: center;
                padding: 50px;
                background: #0a0a1a;
                color: #ff4444;
            }}
            h1 {{ font-size: 48px; }}
            .order {{ color: #aaa; margin: 20px 0; }}
            .btn {{
                background: #ff4444;
                color: #fff;
                padding: 12px 30px;
                border-radius: 8px;
                text-decoration: none;
                display: inline-block;
            }}
            .btn:hover {{ background: #ff6666; }}
        </style>
    </head>
    <body>
        <h1>❌ Ошибка оплаты</h1>
        <p class="order">Заказ #{order_id} не оплачен</p>
        <p>Попробуйте снова или выберите другой способ оплаты</p>
        <br>
        <a href="https://t.me/platezhka_robot" class="btn">⬅️ Вернуться в бота</a>
    </body>
    </html>
    """

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
