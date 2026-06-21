from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
import os
import json
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Version actuelle de la matrice
MATRICE_VERSION = "12"
MATRICE_DATE = "2026-06-21"
POINTS_TOTAL = 594

# ── Fichiers statiques ──────────────────────────────────────
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
    response.headers['X-Matrice-Version'] = MATRICE_VERSION
    return response

@app.route('/manifest.json')
def manifest():
    return send_file('manifest.json', mimetype='application/json')

@app.route('/sw.js')
def sw():
    return send_file('sw.js', mimetype='application/javascript')

# ── API version ─────────────────────────────────────────────
@app.route('/api/version')
def version():
    """
    L'application appelle cette route au démarrage
    pour savoir si une nouvelle version de la matrice est disponible.
    """
    return jsonify({
        "version": MATRICE_VERSION,
        "date": MATRICE_DATE,
        "points_total": POINTS_TOTAL,
        "lots": {
            "Électricité": 210,
            "Plomberie sanitaire": 64,
            "CVC": 50,
            "Sécurité incendie": 128,
            "Courant faible - Vidéo": 47,
            "Ascenseur": 38,
            "FD C17-205 Sections & Protect.": 37,
            "Vérification & Réception": 20
        },
        "app": "ASSISTEC Contrôle Technique",
        "serveur": "OK",
        "timestamp": datetime.utcnow().isoformat()
    })

# ── Santé du serveur ─────────────────────────────────────────
@app.route('/health')
def health():
    return jsonify({"status": "ok", "app": "ASSISTEC"})

# ── Démarrage ────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
