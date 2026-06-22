from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
import os
import json
import urllib.request
import urllib.error
from datetime import datetime

app = Flask(__name__)
CORS(app)

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
MATRICE_VERSION = "12"
MATRICE_DATE = "2026-06-21"
POINTS_TOTAL = 594

@app.route('/')
def index():
    return send_file('app_assistec_v4.html')

@app.route('/app_assistec_v4.html')
def app_html():
    return send_file('app_assistec_v4.html')

@app.route('/matrice.js')
def matrice_js():
    response = send_file('matrice.js', mimetype='application/javascript')
    response.headers['Cache-Control'] = 'no-cache, must-revalidate'
    return response

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
        "date": MATRICE_DATE,
        "points_total": POINTS_TOTAL,
        "app": "ASSISTEC Controle Technique",
        "serveur": "OK",
        "cle_serveur": bool(ANTHROPIC_API_KEY),
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/api/analyser', methods=['POST'])
def analyser():
    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "Cle API non configuree sur le serveur"}), 500
    try:
        # Lire les données brutes en UTF-8
        raw_data = request.get_data()
        data = json.loads(raw_data.decode('utf-8'))

        if not data:
            return jsonify({"error": "Donnees manquantes"}), 400

        payload = json.dumps({
            "model": data.get("model", "claude-sonnet-4-6"),
            "max_tokens": data.get("max_tokens", 4000),
            "system": data.get("system", ""),
            "messages": data.get("messages", [])
        }, ensure_ascii=False).encode('utf-8')

        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=payload,
            headers={
                'Content-Type': 'application/json; charset=utf-8',
                'x-api-key': ANTHROPIC_API_KEY,
                'anthropic-version': '2023-06-01'
            },
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
            return jsonify(result)

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        try:
            return jsonify({"error": json.loads(error_body)}), e.code
        except:
            return jsonify({"error": error_body}), e.code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    return jsonify({"status": "ok", "app": "ASSISTEC"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
