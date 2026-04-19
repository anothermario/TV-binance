import os
from flask import Flask, request, jsonify

app = Flask(__name__)

# Load secret for verification
WEBHOOK_PASSPHRASE = os.getenv('WEBHOOK_PASSPHRASE', 'fa44b421a930638dc0cffd0a0f129835')

@app.route('/', methods=['GET'])
def health():
    return "Test Bot is Online", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    # Try to get the JSON data
    data = request.get_json()
    
    # 1. Log exactly what we received to the Render console
    print(f"--- NEW SIGNAL RECEIVED ---")
    print(f"Payload: {data}")

    # 2. Check Passphrase
    if not data or data.get('passphrase') != WEBHOOK_PASSPHRASE:
        print("Error: Unauthorized (Passphrase Mismatch)")
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    # 3. Simulate the Trade Logic
    symbol = data.get('symbol')
    qty = data.get('quantity')
    
    print(f"Action: Simulating Market BUY for {qty} of {symbol}")
    print(f"Action: Simulating 2% Limit SELL placement")
    print(f"--- TEST SUCCESSFUL ---")

    return jsonify({"status": "test_mode_success", "received": data}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
