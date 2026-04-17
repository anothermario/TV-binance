import hmac
import json
import logging
import os
import sys

from binance.client import Client
from binance.exceptions import BinanceAPIException
from flask import Flask, request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

API_KEY = os.environ.get("BINANCE_API_KEY", "")
API_SECRET = os.environ.get("BINANCE_API_SECRET", "")
PASSPHRASE = os.environ.get("WEBHOOK_PASSPHRASE", "")
TAKE_PROFIT_PCT = float(os.environ.get("TAKE_PROFIT_PCT", "2.0"))

# Validate required configuration at startup so the server fails fast
_missing = [name for name, val in [
    ("BINANCE_API_KEY", API_KEY),
    ("BINANCE_API_SECRET", API_SECRET),
    ("WEBHOOK_PASSPHRASE", PASSPHRASE),
] if not val]
if _missing:
    sys.exit(f"ERROR: Missing required environment variables: {', '.join(_missing)}")

_client = None


def get_client():
    global _client
    if _client is None:
        _client = Client(API_KEY, API_SECRET)
    return _client


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = json.loads(request.data)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Invalid JSON payload: %s", exc)
        return "Bad Request", 400

    # Constant-time passphrase check to prevent timing attacks
    received = data.get("passphrase", "")
    if not hmac.compare_digest(received, PASSPHRASE):
        logger.warning("Unauthorized webhook attempt")
        return "Unauthorized", 401

    symbol = data.get("symbol")
    side = data.get("side", "buy").upper()
    quantity = data.get("quantity")

    if not symbol:
        return "Missing symbol", 400
    if quantity is None:
        return "Missing quantity", 400
    try:
        quantity = float(quantity)
        if quantity <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return "quantity must be a positive number", 400

    binance_client = get_client()

    try:
        if side == "BUY":
            buy_order = binance_client.create_order(
                symbol=symbol,
                side=Client.SIDE_BUY,
                type=Client.ORDER_TYPE_MARKET,
                quantity=quantity,
            )
            logger.info("Buy order executed: %s", buy_order)

            fills = buy_order.get("fills", [])
            if not fills:
                logger.error("No fills in buy order response: %s", buy_order)
                return "Order placed but fill data unavailable", 500
            fill_price = float(fills[0]["price"])
            # Use 8 decimal places to accommodate Binance precision rules
            tp_price = round(fill_price * (1 + TAKE_PROFIT_PCT / 100), 8)

            sell_order = binance_client.create_order(
                symbol=symbol,
                side=Client.SIDE_SELL,
                type=Client.ORDER_TYPE_LIMIT,
                timeInForce=Client.TIME_IN_FORCE_GTC,
                quantity=quantity,
                price=str(tp_price),
            )
            logger.info("Limit sell placed at %s: %s", tp_price, sell_order)

        elif side == "SELL":
            sell_order = binance_client.create_order(
                symbol=symbol,
                side=Client.SIDE_SELL,
                type=Client.ORDER_TYPE_MARKET,
                quantity=quantity,
            )
            logger.info("Sell order executed: %s", sell_order)

        else:
            return "Invalid side", 400

    except BinanceAPIException as exc:
        logger.error("Binance API error: %s", exc)
        return "Order failed: Binance API error", 400
    except Exception as exc:
        logger.error("Unexpected error: %s", exc)
        return "Internal server error", 500

    return "Success", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
