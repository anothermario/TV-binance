import os
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime

app = Flask(__name__)

# --- Configuration ---
WEBHOOK_PASSPHRASE = os.getenv('WEBHOOK_PASSPHRASE', 'fa44b421a930638dc0cffd0a0f129835')
open_positions = []
closed_trades = []

# --- Base HTML Template ---
BASE_TEMPLATE = """
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
        .nav-link { color: #adb5bd; }
        .nav-link:hover { color: #fff; }
    </style>
</head>
<body>
    <div class="container">
        <nav class="navbar navbar-expand-lg navbar-dark mb-4 p-0">
            <a class="navbar-brand fw-bold" href="/">📈 Paper Trading</a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/">Dashboard</a>
                <a class="nav-link" href="/settings">Settings</a>
            </div>
        </nav>
        {% block content %}{% endblock %}
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

DASHBOARD_HTML = BASE_TEMPLATE.replace("{% block content %}{% endblock %}", """
{% block content %}
<h1>Dashboard</h1>

<!-- Summary Cards -->
<div class="row g-3 mb-4">
    <div class="col-sm-6 col-md-3">
        <div class="card text-center">
            <div class="card-body">
                <h6 class="card-subtitle mb-1 text-muted">Total Trades</h6>
                <h2 class="card-title mb-0">{{ open_count + closed_count }}</h2>
            </div>
        </div>
    </div>
    <div class="col-sm-6 col-md-3">
        <div class="card text-center">
            <div class="card-body">
                <h6 class="card-subtitle mb-1 text-muted">Active Positions</h6>
                <h2 class="card-title mb-0 text-success">{{ open_count }}</h2>
            </div>
        </div>
    </div>
</div>

<!-- Tabs -->
<ul class="nav nav-tabs mb-3" id="tradeTabs" role="tablist">
    <li class="nav-item" role="presentation">
        <button class="nav-link active" id="open-tab" data-bs-toggle="tab" data-bs-target="#open" type="button" role="tab">
            Open Positions <span class="badge bg-success ms-1">{{ open_count }}</span>
        </button>
    </li>
    <li class="nav-item" role="presentation">
        <button class="nav-link" id="closed-tab" data-bs-toggle="tab" data-bs-target="#closed" type="button" role="tab">
            Trade History (Closed) <span class="badge bg-secondary ms-1">{{ closed_count }}</span>
        </button>
    </li>
</ul>

<div class="tab-content" id="tradeTabContent">
    <!-- Open Positions Tab -->
    <div class="tab-pane fade show active" id="open" role="tabpanel">
        {% if open_trades %}
        <table class="table table-striped table-bordered table-hover align-middle">
            <thead class="table-dark">
                <tr>
                    <th>Time</th>
                    <th>Symbol</th>
                    <th>Entry Price</th>
                    <th>Target (+2%)</th>
                    <th>Quantity</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                {% for trade in open_trades %}
                <tr>
                    <td>{{ trade.time }}</td>
                    <td><strong>{{ trade.symbol }}</strong></td>
                    <td>${{ trade.entry }}</td>
                    <td>${{ trade.target }}</td>
                    <td>{{ trade.qty }}</td>
                    <td><span class="badge bg-success">Open</span></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="alert alert-info">No open positions. Send a webhook signal to get started!</div>
        {% endif %}
    </div>

    <!-- Closed Trades Tab -->
    <div class="tab-pane fade" id="closed" role="tabpanel">
        {% if closed_trades %}
        <table class="table table-striped table-bordered table-hover align-middle">
            <thead class="table-dark">
                <tr>
                    <th>Time</th>
                    <th>Symbol</th>
                    <th>Entry Price</th>
                    <th>Target (+2%)</th>
                    <th>Quantity</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                {% for trade in closed_trades|reverse %}
                <tr>
                    <td>{{ trade.time }}</td>
                    <td><strong>{{ trade.symbol }}</strong></td>
                    <td>${{ trade.entry }}</td>
                    <td>${{ trade.target }}</td>
                    <td>{{ trade.qty }}</td>
                    <td><span class="badge bg-secondary">Closed</span></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="alert alert-info">No closed trades yet.</div>
        {% endif %}
    </div>
</div>
{% endblock %}
""")

SETTINGS_HTML = BASE_TEMPLATE.replace("{% block content %}{% endblock %}", """
{% block content %}
<h1>Settings</h1>
<div class="row g-3">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header"><strong>Configuration Status</strong></div>
            <ul class="list-group list-group-flush">
                <li class="list-group-item d-flex justify-content-between align-items-center">
                    Webhook Passphrase
                    <span class="badge bg-success">Set &mdash; <code>{{ passphrase }}</code></span>
                </li>
                <li class="list-group-item d-flex justify-content-between align-items-center">
                    Binance API Key
                    {% if api_set %}
                    <span class="badge bg-success">Configured</span>
                    {% else %}
                    <span class="badge bg-warning text-dark">Not Set</span>
                    {% endif %}
                </li>
                <li class="list-group-item d-flex justify-content-between align-items-center">
                    Binance API Secret
                    {% if secret_set %}
                    <span class="badge bg-success">Configured</span>
                    {% else %}
                    <span class="badge bg-warning text-dark">Not Set</span>
                    {% endif %}
                </li>
            </ul>
        </div>
    </div>
</div>
{% endblock %}
""")


@app.route('/', methods=['GET'])
def index():
    return render_template_string(
        DASHBOARD_HTML,
        open_trades=open_positions,
        closed_trades=closed_trades,
        open_count=len(open_positions),
        closed_count=len(closed_trades),
    )


@app.route('/settings', methods=['GET'])
def settings():
    return render_template_string(
        SETTINGS_HTML,
        passphrase=WEBHOOK_PASSPHRASE,
        api_set=bool(os.getenv('BINANCE_API_KEY')),
        secret_set=bool(os.getenv('BINANCE_API_SECRET')),
    )


@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()

    if not data or data.get('passphrase') != WEBHOOK_PASSPHRASE:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    symbol = data.get('symbol', 'UNKNOWN').upper()
    qty = data.get('quantity', 0)
    entry_price = float(data.get('price', 0))
    target_price = round(entry_price * 1.02, 2)

    new_trade = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": symbol,
        "entry": entry_price,
        "target": target_price,
        "qty": qty,
    }

    # Close any existing open position for the same symbol
    for i, t in enumerate(open_positions):
        if t['symbol'] == symbol:
            closed_trades.append(open_positions.pop(i))
            break

    open_positions.append(new_trade)
    print(f"New position opened: {new_trade}")

    return jsonify({"status": "success", "message": "Trade logged to dashboard"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
