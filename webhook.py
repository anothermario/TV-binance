import hmac
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN

from flask import Flask, jsonify, render_template, request
from binance.client import Client
from binance.exceptions import BinanceAPIException

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Load Environment Variables ---
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
WEBHOOK_PASSPHRASE = os.getenv("WEBHOOK_PASSPHRASE")

DB_PATH = os.getenv("DB_PATH", "trades.db")

client = None
symbol_info_cache = {}
trade_history = []

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def init_db():
    with _db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol        TEXT    NOT NULL,
                quantity      REAL    NOT NULL,
                buy_price     REAL    NOT NULL,
                buy_order_id  TEXT    NOT NULL,
                tp_price      REAL    NOT NULL,
                sell_order_id TEXT,
                status        TEXT    NOT NULL DEFAULT 'open',
                buy_time      TEXT    NOT NULL,
                close_time    TEXT,
                profit        REAL
            )
            """
        )


@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_trade(symbol, quantity, buy_price, buy_order_id, tp_price, sell_order_id):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO trades (symbol, quantity, buy_price, buy_order_id,
                                tp_price, sell_order_id, status, buy_time)
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?)
            """,
            (symbol, quantity, buy_price, buy_order_id, tp_price, sell_order_id, now),
        )


def sync_open_trades():
    """Check Binance for each open trade and mark it closed if the sell order filled."""
    if not API_KEY or not API_SECRET:
        return
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, symbol, quantity, buy_price, tp_price, sell_order_id "
            "FROM trades WHERE status = 'open' AND sell_order_id IS NOT NULL"
        ).fetchall()

    for row in rows:
        try:
            binance_client = get_client()
            order = binance_client.get_order(symbol=row["symbol"], orderId=row["sell_order_id"])
            if order.get("status") == "FILLED":
                # Prefer average fill price (cummulativeQuoteQty / executedQty)
                # over the limit price, which may differ from the actual execution.
                executed_qty = float(order.get("executedQty") or 0)
                cumulative_quote = float(order.get("cummulativeQuoteQty") or 0)
                if executed_qty > 0 and cumulative_quote > 0:
                    sell_price = cumulative_quote / executed_qty
                else:
                    sell_price = float(order.get("price") or row["tp_price"])
                profit = (sell_price - row["buy_price"]) * row["quantity"]
                close_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                with _db() as conn:
                    conn.execute(
                        "UPDATE trades SET status='closed', close_time=?, profit=? WHERE id=?",
                        (close_time, profit, row["id"]),
                    )
                logger.info("Trade %s closed — profit %.4f", row["id"], profit)
        except Exception:
            logger.exception("Error syncing trade id=%s", row["id"])


# ---------------------------------------------------------------------------
# Binance helpers
# ---------------------------------------------------------------------------

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
    symbol_info = symbol_info_cache.get(symbol)
    if symbol_info is None:
        symbol_info = get_client().get_symbol_info(symbol)
        symbol_info_cache[symbol] = symbol_info
    if symbol_info:
        for rule in symbol_info.get("filters", []):
            if rule.get("filterType") == "PRICE_FILTER":
                tick_size = Decimal(rule["tickSize"])
                if tick_size > 0:
                    rounded = Decimal(str(price)).quantize(tick_size, rounding=ROUND_DOWN)
                    return format(rounded, "f")
    raise LookupError(f"Unable to determine price precision for {symbol}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def health_check():
    sync_open_trades()
    with _db() as conn:
        open_trades = [dict(r) for r in conn.execute(
            "SELECT * FROM trades WHERE status = 'open' ORDER BY buy_time DESC"
        ).fetchall()]
        closed_trades = [dict(r) for r in conn.execute(
            "SELECT * FROM trades WHERE status = 'closed' ORDER BY close_time DESC"
        ).fetchall()]

    total_profit = sum(t["profit"] or 0 for t in closed_trades)
    wins = sum(1 for t in closed_trades if (t["profit"] or 0) > 0)
    win_rate = round(wins / len(closed_trades) * 100) if closed_trades else 0

    return render_template(
        "dashboard.html",
        active="dashboard",
        trades=trade_history,
        open_trades=open_trades,
        closed_trades=closed_trades,
        total_profit=total_profit,
        win_rate=win_rate,
    )


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True)

    missing_env = get_missing_env_vars()
    missing_binance_env = [name for name in missing_env if name != "WEBHOOK_PASSPHRASE"]
    if "WEBHOOK_PASSPHRASE" in missing_env:
        logger.error("Missing required webhook configuration")
        return jsonify({"status": "error", "message": "Server configuration error"}), 500

    # 1. Verification
    if not data or not hmac.compare_digest(data.get("passphrase", ""), WEBHOOK_PASSPHRASE):
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    if missing_binance_env:
        logger.error("Missing required Binance configuration")
        return jsonify({"status": "error", "message": "Server configuration error"}), 500

    try:
        symbol = data.get("symbol")
        quantity = data.get("quantity")

        if not symbol:
            return jsonify({"status": "error", "message": "Missing symbol"}), 400
        if quantity is None:
            return jsonify({"status": "error", "message": "Missing quantity"}), 400

        symbol = symbol.upper()
        try:
            quantity = float(quantity)
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "Invalid quantity"}), 400
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
        fill = fills[0] if fills else {}
        fill_price_value = fill.get("price")
        if fill_price_value is None:
            logger.error("Buy order fill missing price field: %s", buy_order)
            return jsonify({"status": "error", "message": "Invalid order response from exchange"}), 500

        fill_price = float(fill_price_value)
        # TradingView alerts in this project always target a fixed 2% take-profit.
        tp_price = fill_price * 1.02

        # Binance is strict with decimal places.
        tp_price_rounded = round_take_profit_price(symbol, tp_price)

        # 4. Place Limit Sell
        sell_order = binance_client.create_order(
            symbol=symbol,
            side="SELL",
            type="LIMIT",
            timeInForce="GTC",
            quantity=quantity,
            price=tp_price_rounded,
        )

        # 5. Persist trade record
        save_trade(
            symbol=symbol,
            quantity=quantity,
            buy_price=fill_price,
            buy_order_id=str(buy_order.get("orderId", "")),
            tp_price=float(tp_price_rounded),
            sell_order_id=str(sell_order.get("orderId", "")),
        )

        # 6. Record in in-memory trade history for the dashboard
        trade_history.append({
            "symbol": symbol,
            "price": fill_price,
            "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "type": "BUY",
        })

        return jsonify({"status": "success", "buy": fill_price, "tp": tp_price_rounded}), 200

    except LookupError:
        logger.exception("Price precision lookup failed")
        return jsonify({"status": "error", "message": "Unable to determine valid price precision"}), 500
    except BinanceAPIException:
        logger.exception("Binance API error while processing webhook")
        return jsonify({"status": "error", "message": "Binance API error"}), 400
    except Exception:
        logger.exception("Unexpected webhook error")
        return jsonify({"status": "error", "message": "Internal error"}), 500


@app.route("/dashboard", methods=["GET"])
def dashboard():
    sync_open_trades()
    with _db() as conn:
        open_trades = [dict(r) for r in conn.execute(
            "SELECT * FROM trades WHERE status = 'open' ORDER BY buy_time DESC"
        ).fetchall()]
        closed_trades = [dict(r) for r in conn.execute(
            "SELECT * FROM trades WHERE status = 'closed' ORDER BY close_time DESC"
        ).fetchall()]

    total_profit = sum(t["profit"] or 0 for t in closed_trades)
    wins = sum(1 for t in closed_trades if (t["profit"] or 0) > 0)
    win_rate = round(wins / len(closed_trades) * 100) if closed_trades else 0

    return render_template(
        "dashboard.html",
        active="dashboard",
        open_trades=open_trades,
        closed_trades=closed_trades,
        total_profit=total_profit,
        win_rate=win_rate,
    )


@app.route("/stats", methods=["GET"])
def stats():
    sync_open_trades()
    with _db() as conn:
        # Daily breakdown — last 7 days
        daily_rows = [
            {"period": r["period"], "count": r["cnt"], "profit": r["profit"]}
            for r in conn.execute(
                """
                SELECT date(close_time) AS period,
                       COUNT(*)         AS cnt,
                       SUM(profit)      AS profit
                FROM   trades
                WHERE  status = 'closed'
                  AND  close_time >= date('now', '-6 days')
                GROUP  BY period
                ORDER  BY period DESC
                """
            ).fetchall()
        ]

        # Weekly breakdown — last 8 weeks (week starts Monday)
        weekly_rows = [
            {"period": r["period"], "count": r["cnt"], "profit": r["profit"]}
            for r in conn.execute(
                """
                SELECT strftime('%Y-%W', close_time) AS period,
                       COUNT(*)                       AS cnt,
                       SUM(profit)                    AS profit
                FROM   trades
                WHERE  status = 'closed'
                  AND  close_time >= date('now', '-56 days')
                GROUP  BY period
                ORDER  BY period DESC
                """
            ).fetchall()
        ]

        # Monthly breakdown — last 12 months
        monthly_rows = [
            {"period": r["period"], "count": r["cnt"], "profit": r["profit"]}
            for r in conn.execute(
                """
                SELECT strftime('%Y-%m', close_time) AS period,
                       COUNT(*)                       AS cnt,
                       SUM(profit)                    AS profit
                FROM   trades
                WHERE  status = 'closed'
                  AND  close_time >= date('now', '-365 days')
                GROUP  BY period
                ORDER  BY period DESC
                """
            ).fetchall()
        ]

        # Summary totals for the header cards
        def _sum(rows):
            return sum(r["profit"] or 0 for r in rows), sum(r["count"] for r in rows)

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        week_str = datetime.now(timezone.utc).strftime("%Y-%W")
        month_str = datetime.now(timezone.utc).strftime("%Y-%m")

        daily_today = [r for r in daily_rows if r["period"] == today_str]
        weekly_this = [r for r in weekly_rows if r["period"] == week_str]
        monthly_this = [r for r in monthly_rows if r["period"] == month_str]

        daily_total, daily_count = _sum(daily_today)
        weekly_total, weekly_count = _sum(weekly_this)
        monthly_total, monthly_count = _sum(monthly_this)

    return render_template(
        "stats.html",
        active="stats",
        daily_rows=daily_rows,
        weekly_rows=weekly_rows,
        monthly_rows=monthly_rows,
        daily_total=daily_total,
        daily_count=daily_count,
        weekly_total=weekly_total,
        weekly_count=weekly_count,
        monthly_total=monthly_total,
        monthly_count=monthly_count,
    )


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

init_db()

if __name__ == "__main__":
    # For local testing; Render uses Gunicorn
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
