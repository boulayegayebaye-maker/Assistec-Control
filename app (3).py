from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
import os
import json
import urllib.request
import urllib.error
import base64
from datetime import datetime

app = Flask(__name__)
CORS(app)

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
MATRICE_VERSION = "12"
POINTS_TOTAL = 594

@app.route('/')
def index():
    return send_file('app_assistec_v4.html')

@app.route('/app_assistec_v4.html')
def app_html():
    return send_file('app_assistec_v4.html')

@app.route('/matrice.js')
def matrice_js():
    return send_file('matrice.js', mimetype='application/javascript')

@app.route('/manifest.json')
def manifest():
    return send_file('manifest.json', mimetype='application/json')

@app.route('/sw.js')
def sw():
    return send_file('sw.js', mimetype='application/javascript')

@app.route('/api/version')
def version():
    return jsonify({
        "version": MATRICE_VERSION,
        "points_total": POINTS_TOTAL,
        "app": "ASSISTEC",
        "serveur": "OK",
        "cle_serveur": bool(ANTHROPIC_API_KEY),
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/api/analyser', methods=['POST'])
def analyser():
    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "Cle API non configuree"}), 500
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"error": "Donnees manquantes"}), 400

        # Décoder le system prompt s'il est encodé en base64
        system = data.get("system", "")
        if data.get("encoded"):
            try:
                system = base64.b64decode(system).decode('utf-8')
            except:
                pass

        messages = data.get("messages", [])

        # Construire le payload pour Anthropic
        anthropic_payload = {
            "model": data.get("model", "claude-sonnet-4-6"),
            "max_tokens": data.get("max_tokens", 4000),
            "system": system,
            "messages": messages
        }

        payload_bytes = json.dumps(
            anthropic_payload,
            ensure_ascii=True
        ).encode('ascii')

        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=payload_bytes,
            headers={
                'Content-Type': 'application/json',
                'x-api-key': ANTHROPIC_API_KEY,
                'anthropic-version': '2023-06-01'
            },
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return jsonify(result)

    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode('utf-8'))
            return jsonify({"error": err}), e.code
        except:
            return jsonify({"error": f"HTTP {e.code}"}), e.code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
