# TV-binance

A TradingView → Binance webhook bridge with a built-in trade dashboard and
profit stats page.  When a TradingView alert fires the bridge executes a
**market buy** on Binance, places a **limit sell** at a fixed 2% take-profit
above the fill price, and persists the trade in a local SQLite database so it
can be tracked in the UI.

---

## How it works

```
TradingView alert  ──POST /webhook──►  Flask server  ──►  Binance API
                                            │
                                       SQLite DB
                                            │
                               GET /dashboard  GET /stats
```

1. You configure a TradingView alert whose "Message" body is a JSON payload.
2. TradingView sends an HTTP POST to your server's `/webhook` endpoint.
3. The bridge validates the passphrase, executes the market buy, then places
   a GTC limit sell at `fill_price × 1.02`, and saves the trade to the DB.
4. Visit `/dashboard` to see open trades and finished transactions.
5. Visit `/stats` for daily, weekly, and monthly profit breakdowns.

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
| `PORT` | Port the server listens on | `10000` |
| `DB_PATH` | Path for the SQLite trade database | `trades.db` |

### 3 — Run the server

```bash
# Load variables from .env and start the server
export $(grep -v '^#' .env | xargs)
python webhook.py
```

For production use a WSGI server such as **gunicorn**:

```bash
pip install gunicorn
gunicorn --bind 0.0.0.0:10000 webhook:app
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
    "quantity": 0.001
}
```

- `passphrase` — must match `WEBHOOK_PASSPHRASE` in your `.env`
- `symbol` — the Binance trading pair (e.g. `BTCUSDT`); `{{ticker}}` fills it automatically
- `quantity` — exact base-asset quantity to trade

---

## Render deployment

- Use `GET /` as the health check endpoint so Render can confirm the service is up.
- Start the app with:

```bash
gunicorn --bind 0.0.0.0:10000 webhook:app
```

- On Render, set `DB_PATH` to a path inside a **persistent disk** (e.g.
  `/data/trades.db`) so the database survives deploys.

---

## Pages

| URL | Description |
|---|---|
| `GET /` | Health check — returns `Bot is running` |
| `POST /webhook` | TradingView alert receiver |
| `GET /dashboard` | Open trades + finished transactions table |
| `GET /stats` | Daily / weekly / monthly profit breakdown |

---

## Security notes

- **Never** commit your `.env` file — it is listed in `.gitignore`.
- The webhook passphrase is checked with a constant-time comparison to reduce
  timing-attack risk.
- Restrict your Binance API key to **Spot trading only** and whitelist your
  server's IP address in the Binance API settings.

---

## License

MIT
