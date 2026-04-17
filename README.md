# TV-binance

A lightweight webhook bridge that forwards TradingView alerts to Binance.
When a TradingView alert fires, the bridge executes a **market buy** on Binance
and immediately places a **limit sell** at a configurable take-profit percentage
above the fill price.

---

## How it works

```
TradingView alert  ──POST /webhook──►  Flask server  ──►  Binance API
```

1. You configure a TradingView alert whose "Message" body is a JSON payload.
2. TradingView sends an HTTP POST to your server's `/webhook` endpoint.
3. The bridge validates the passphrase, executes the market buy, then places
   a GTC limit sell at `fill_price × (1 + TAKE_PROFIT_PCT / 100)`.

---

## Requirements

- Python 3.9+
- A publicly reachable URL (e.g. [Render](https://render.com),
  [Railway](https://railway.app), [PythonAnywhere](https://www.pythonanywhere.com))
- Binance account with API key & secret (Spot trading enabled)

---

## Quick start

### 1 — Clone and install dependencies

```bash
git clone https://github.com/anothermario/TV-binance.git
cd TV-binance
pip install -r requirements.txt
```

### 2 — Configure environment variables

```bash
cp .env.example .env
# Edit .env and fill in your real values
```

| Variable | Description | Default |
|---|---|---|
| `BINANCE_API_KEY` | Binance API key | *(required)* |
| `BINANCE_API_SECRET` | Binance API secret | *(required)* |
| `WEBHOOK_PASSPHRASE` | Secret phrase shared with TradingView | *(required)* |
| `TAKE_PROFIT_PCT` | Take-profit % above fill price | `2.0` |
| `PORT` | Port the server listens on | `5000` |

### 3 — Run the server

```bash
# Load variables from .env and start the server
export $(grep -v '^#' .env | xargs)
python webhook.py
```

For production use a WSGI server such as **gunicorn**:

```bash
pip install gunicorn
gunicorn webhook:app --bind 0.0.0.0:5000
```

---

## TradingView alert setup

In the TradingView **Alert** dialog, set **Webhook URL** to your public endpoint:

```
https://your-server.example.com/webhook
```

Set the **Message** body to:

```json
{
    "passphrase": "MY_SECRET_PHRASE",
    "symbol": "{{ticker}}",
    "side": "buy",
    "quantity": 0.001
}
```

- `passphrase` — must match `WEBHOOK_PASSPHRASE` in your `.env`
- `symbol` — the Binance trading pair (e.g. `BTCUSDT`); `{{ticker}}` fills it automatically
- `side` — `"buy"` executes a market buy + limit sell; `"sell"` executes a market sell
- `quantity` — exact base-asset quantity to trade

---

## Security notes

- **Never** commit your `.env` file — it is listed in `.gitignore`.
- The passphrase is checked with a constant-time comparison (`hmac.compare_digest`)
  to prevent timing attacks.
- Restrict your Binance API key to **Spot trading only** and whitelist your
  server's IP address in the Binance API settings.

---

## License

MIT
