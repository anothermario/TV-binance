import os
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime

app = Flask(__name__)

# --- Configuration ---
WEBHOOK_PASSPHRASE = os.getenv('WEBHOOK_PASSPHRASE', 'fa44b421a930638dc0cffd0a0f129835')
trade_history = []

# --- HTML Template for Dashboard ---
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paper Trading Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { padding: 2rem; }
        h1 { margin-bottom: 1.5rem; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📈 Paper Trading Dashboard</h1>
        {% if trades %}
        <table class="table table-striped table-bordered table-hover align-middle">
            <thead class="table-dark">
                <tr>
                    <th>Timestamp</th>
                    <th>Symbol</th>
                    <th>Entry Price</th>
                    <th>Target Price (+2%)</th>
                    <th>Quantity</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                {% for trade in trades|reverse %}
                <tr>
                    <td>{{ trade.time }}</td>
                    <td><strong>{{ trade.symbol }}</strong></td>
                    <td>${{ trade.entry }}</td>
                    <td>${{ trade.target }}</td>
                    <td>{{ trade.qty }}</td>
                    <td><span class="badge bg-success">Simulated Success</span></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="alert alert-info" role="alert">
            No trades logged yet. Send a webhook signal to get started!
        </div>
        {% endif %}
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

@app.route('/', methods=['GET'])
def dashboard():
    return render_template_string(DASHBOARD_HTML, trades=trade_history)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()

    if not data or data.get('passphrase') != WEBHOOK_PASSPHRASE:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    # Simulated Logic
    symbol = data.get('symbol', 'UNKNOWN')
    qty = data.get('quantity', 0)

    # In a real scenario, we'd get the price from Binance.
    # For simulation, we'll assume a dummy price of 60000 if not provided.
    entry_price = data.get('price', 60000)
    target_price = round(entry_price * 1.02, 2)

    new_trade = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": symbol.upper(),
        "entry": entry_price,
        "target": target_price,
        "qty": qty
    }

    trade_history.append(new_trade)
    print(f"Stored Simulated Trade: {new_trade}")

    return jsonify({"status": "success", "message": "Trade logged to dashboard"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
