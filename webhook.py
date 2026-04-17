import hmac
import logging
import os
from decimal import Decimal, ROUND_DOWN

from flask import Flask, jsonify, request
from binance.client import Client
from binance.exceptions import BinanceAPIException

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Load Environment Variables ---
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
WEBHOOK_PASSPHRASE = os.getenv("WEBHOOK_PASSPHRASE")

client = None


def get_client():
    global client
    if client is None:
        client = Client(API_KEY, API_SECRET)
    return client


def get_missing_env_vars():
    return [
        name
        for name, value in (
            ("BINANCE_API_KEY", API_KEY),
            ("BINANCE_API_SECRET", API_SECRET),
            ("WEBHOOK_PASSPHRASE", WEBHOOK_PASSPHRASE),
        )
        if not value
    ]


def round_take_profit_price(symbol, price):
    symbol_info = get_client().get_symbol_info(symbol)
    if symbol_info:
        for rule in symbol_info.get("filters", []):
            if rule.get("filterType") == "PRICE_FILTER":
                tick_size = Decimal(rule["tickSize"])
                if tick_size > 0:
                    rounded = Decimal(str(price)).quantize(tick_size, rounding=ROUND_DOWN)
                    return format(rounded, "f")
    return "{:.2f}".format(price)


@app.route("/", methods=["GET"])
def health_check():
    return "Bot is running", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True)

    missing_env = get_missing_env_vars()
    if missing_env:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Missing environment variables: {', '.join(missing_env)}",
                }
            ),
            500,
        )

    # 1. Verification
    if not data or not hmac.compare_digest(data.get("passphrase", ""), WEBHOOK_PASSPHRASE or ""):
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    try:
        symbol = data.get("symbol")
        quantity = data.get("quantity")

        if not symbol:
            return jsonify({"status": "error", "message": "Missing symbol"}), 400
        if quantity is None:
            return jsonify({"status": "error", "message": "Missing quantity"}), 400

        symbol = symbol.upper()
        quantity = float(quantity)
        if quantity <= 0:
            return jsonify({"status": "error", "message": "Invalid quantity"}), 400

        # 2. Execute Market Buy
        binance_client = get_client()
        buy_order = binance_client.create_order(
            symbol=symbol,
            side="BUY",
            type="MARKET",
            quantity=quantity,
        )

        # 3. Calculate 2% Take Profit
        fills = buy_order.get("fills") or []
        if not fills or "price" not in fills[0]:
            logger.error("Buy order missing fill price: %s", buy_order)
            return jsonify({"status": "error", "message": "Buy order fill price unavailable"}), 502

        fill_price = float(fills[0]["price"])
        tp_price = fill_price * 1.02

        # Binance is strict with decimal places.
        tp_price_rounded = round_take_profit_price(symbol, tp_price)

        # 4. Place Limit Sell
        binance_client.create_order(
            symbol=symbol,
            side="SELL",
            type="LIMIT",
            timeInForce="GTC",
            quantity=quantity,
            price=tp_price_rounded,
        )

        return jsonify({"status": "success", "buy": fill_price, "tp": tp_price_rounded}), 200

    except BinanceAPIException as error:
        logger.exception("Binance API error while processing webhook")
        return jsonify({"status": "error", "message": "Binance API error", "code": error.code}), 400
    except Exception as error:
        logger.exception("Unexpected webhook error: %s", error)
        return jsonify({"status": "error", "message": "Internal error"}), 500


if __name__ == "__main__":
    # For local testing; Render uses Gunicorn
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
