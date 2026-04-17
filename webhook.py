import os

from flask import Flask, jsonify, request
from binance.client import Client
from binance.exceptions import BinanceAPIException

app = Flask(__name__)

# --- Load Environment Variables ---
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
WEBHOOK_PASSPHRASE = os.getenv("WEBHOOK_PASSPHRASE")

# Initialize client (will handle empty keys gracefully at start)
client = Client(API_KEY, API_SECRET)


@app.route("/", methods=["GET"])
def health_check():
    return "Bot is running", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    missing_env = [
        name
        for name, value in (
            ("BINANCE_API_KEY", API_KEY),
            ("BINANCE_API_SECRET", API_SECRET),
            ("WEBHOOK_PASSPHRASE", WEBHOOK_PASSPHRASE),
        )
        if not value
    ]
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
    if not data or data.get("passphrase") != WEBHOOK_PASSPHRASE:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    try:
        symbol = data["symbol"].upper()
        quantity = float(data["quantity"])

        # 2. Execute Market Buy
        buy_order = client.create_order(
            symbol=symbol,
            side="BUY",
            type="MARKET",
            quantity=quantity,
        )

        # 3. Calculate 2% Take Profit
        fill_price = float(buy_order["fills"][0]["price"])
        tp_price = fill_price * 1.02

        # Binance is strict with decimal places.
        # For BTCUSDT, we usually round to 2 decimals.
        tp_price_rounded = "{:.2f}".format(tp_price)

        # 4. Place Limit Sell
        client.create_order(
            symbol=symbol,
            side="SELL",
            type="LIMIT",
            timeInForce="GTC",
            quantity=quantity,
            price=tp_price_rounded,
        )

        return jsonify({"status": "success", "buy": fill_price, "tp": tp_price_rounded}), 200

    except BinanceAPIException as error:
        print(f"Binance Error: {error}")
        return jsonify({"status": "error", "message": str(error)}), 400
    except Exception as error:
        print(f"Other Error: {error}")
        return jsonify({"status": "error", "message": "Internal error"}), 500


if __name__ == "__main__":
    # For local testing; Render uses Gunicorn
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
