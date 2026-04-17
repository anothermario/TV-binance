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

## Deploying on Render.com (step-by-step)

[Render](https://render.com) is one of the easiest ways to host this bridge for free.

### Step 1 — Fork / push the repo to GitHub

Make sure your code is in a GitHub (or GitLab) repository that Render can access.

### Step 2 — Create a new Web Service

1. Log in to [render.com](https://render.com) and click **New → Web Service**.
2. Connect your GitHub account and select the **TV-binance** repository.

### Step 3 — Configure the service

| Setting | Value |
|---|---|
| **Environment** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn webhook:app --bind 0.0.0.0:$PORT` |

> **What is the Start Command?**  
> Render runs this command every time it deploys or restarts your app.  
> `gunicorn webhook:app` tells Gunicorn to load the `app` object from `webhook.py`.  
> `--bind 0.0.0.0:$PORT` makes the server listen on the port Render assigns automatically via the `$PORT` environment variable.

### Step 4 — Add environment variables

In the **Environment** tab of your Render service, add the following key-value pairs:

| Key | Value |
|---|---|
| `BINANCE_API_KEY` | Your Binance API key |
| `BINANCE_API_SECRET` | Your Binance API secret |
| `WEBHOOK_PASSPHRASE` | A secret phrase you choose (must match the TradingView alert) |
| `TAKE_PROFIT_PCT` | *(optional)* Take-profit %, e.g. `2.0` |

Do **not** set `PORT` — Render injects it automatically.

### Step 5 — Deploy

Click **Create Web Service**. Render will install dependencies and start the server.  
Once the deploy is green, your webhook URL is:

```
https://<your-service-name>.onrender.com/webhook
```

Paste this URL into the **Webhook URL** field of your TradingView alert.

---

## FAQ

### Q: What should I put as the Start Command on Render?

```
gunicorn webhook:app --bind 0.0.0.0:$PORT
```

Render injects the `$PORT` variable automatically, so do not hard-code a port number.

---

### Q: Why use Gunicorn instead of running `python webhook.py` directly?

`python webhook.py` uses Flask's built-in development server, which is single-threaded and not suitable for production.  
Gunicorn is a production-grade WSGI server that handles concurrent requests properly. Render (and most PaaS platforms) expect a proper WSGI server as the entry point.

---

### Q: The server starts but TradingView alerts are not reaching it. What should I check?

1. **Webhook URL** — make sure it ends with `/webhook` (e.g. `https://my-app.onrender.com/webhook`).
2. **Passphrase** — the `"passphrase"` field in the TradingView alert message must exactly match `WEBHOOK_PASSPHRASE` in your environment variables.
3. **Render free tier sleep** — free Render services spin down after 15 minutes of inactivity. The first request after sleep may time out. Upgrade to a paid plan or use a cron-job pinger service to keep the instance awake.
4. **Logs** — open the **Logs** tab in Render to see real-time output and any error messages.

---

### Q: How do I get my Binance API key?

1. Log in to [binance.com](https://www.binance.com) and go to **Account → API Management**.
2. Create a new API key. Label it (e.g. `TV-binance`).
3. Enable **Spot & Margin Trading**. Leave withdrawals disabled for safety.
4. *(Recommended)* Restrict access to your Render server's outbound IP address.
5. Copy the **API Key** and **Secret Key** — the secret is shown only once.

---

### Q: Can I change the take-profit percentage?

Yes. Set the `TAKE_PROFIT_PCT` environment variable to any positive number.  
For example, `1.5` means the limit sell is placed 1.5 % above the market-buy fill price.  
The default is `2.0` if the variable is not set.

---

### Q: What does the TradingView alert message look like?

```json
{
    "passphrase": "MY_SECRET_PHRASE",
    "symbol": "{{ticker}}",
    "side": "buy",
    "quantity": 0.001
}
```

- Replace `MY_SECRET_PHRASE` with the value of your `WEBHOOK_PASSPHRASE`.
- `{{ticker}}` is a TradingView dynamic variable that inserts the chart symbol automatically.
- `quantity` is the exact base-asset amount to trade (e.g. `0.001` BTC for `BTCUSDT`).

---

## License

MIT
