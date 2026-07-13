cat > webhook_server.py << 'EOF'
from flask import Flask, request, jsonify
from datetime import datetime
import json
import logging
import sqlite3
import os

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/')
def index():
    return jsonify({"status": "Server is running", "time": datetime.now().isoformat()})

@app.route('/webhook/payment', methods=['GET'])
def payment_webhook_test():
    return jsonify({"status": "Webhook is active!", "time": datetime.now().isoformat()})

@app.route('/webhook/payment', methods=['POST'])
def payment_webhook():
    try:
        data = request.get_json()
        if not data:
            data = request.form.to_dict()
        logger.info(f"Webhook received: {data}")
        order_id = data.get('order_id') or data.get('MERCHANT_ORDER_ID')
        if order_id:
            conn = sqlite3.connect("sales_bot.db")
            c = conn.cursor()
            c.execute("UPDATE orders SET status = 'paid', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (order_id,))
            conn.commit()
            conn.close()
            logger.info(f"Order #{order_id} paid")
        return jsonify({"success": True}), 200
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 400

@app.route('/success', methods=['GET'])
def payment_success():
    order_id = request.args.get('order_id', 'неизвестен')
    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>✅ Оплата успешна!</title>
    <meta http-equiv="refresh" content="5;url=https://t.me/platezhka_robot">
    <style>
    body {{ font-family: Arial; text-align: center; padding: 50px; background: #0a0a1a; color: #00ff88; }}
    h1 {{ font-size: 48px; }}
    .btn {{ background: #00ff88; color: #000; padding: 12px 30px; border-radius: 8px; text-decoration: none; }}
    </style>
    </head>
    <body>
    <h1>✅ Оплата успешна!</h1>
    <p>Заказ #{order_id} оплачен</p>
    <a href="https://t.me/platezhka_robot" class="btn">Вернуться в бота</a>
    </body>
    </html>
    """

@app.route('/fail', methods=['GET'])
def payment_fail():
    order_id = request.args.get('order_id', 'неизвестен')
    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>❌ Ошибка оплаты</title>
    <meta http-equiv="refresh" content="10;url=https://t.me/platezhka_robot">
    <style>
    body {{ font-family: Arial; text-align: center; padding: 50px; background: #0a0a1a; color: #ff4444; }}
    h1 {{ font-size: 48px; }}
    .btn {{ background: #ff4444; color: #fff; padding: 12px 30px; border-radius: 8px; text-decoration: none; }}
    </style>
    </head>
    <body>
    <h1>❌ Ошибка оплаты</h1>
    <p>Заказ #{order_id} не оплачен</p>
    <a href="https://t.me/platezhka_robot" class="btn">Вернуться в бота</a>
    </body>
    </html>
    """

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
EOF
