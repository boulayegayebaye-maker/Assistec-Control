from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
import os, json, urllib.request, urllib.error, base64
from datetime import datetime

app = Flask(__name__)
CORS(app)

API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
VERSION = "12"
POINTS = 594

# ── Charger la matrice au démarrage ──────────────────────────
MATRICE = {}
try:
    with open('matrice_data.json', 'r', encoding='utf-8') as f:
        MATRICE = json.load(f)
    print(f"Matrice chargée: {sum(len(v) for v in MATRICE.values())} points")
except Exception as e:
    print(f"Matrice non trouvée: {e}")

LOT_MAPPING = {
    'electricite':       'Électricité',
    'plomberie':         'Plomberie sanitaire',
    'cvc':               'CVC',
    'securite_incendie': 'Sécurité incendie',
    'courant_faible':    'Courant faible - Vidéo',
    'ascenseur':         'Ascenseur',
    'fd_c17205':         'FD C17-205 Sections & Protect.',
    'reception':         'Vérification & Réception'
}

CONTEXTE = {
    'electricite': "Retours terrain ASSISTEC: IB non calculé par circuit, Ku/Ks/Ke absents, DDR 30mA absents, schémas incomplets, prise de terre > 10 Ohm, BAES mal positionnés.",
    'plomberie': "Retours terrain ASSISTEC: canalisations sous-dimensionnées, ECS < 50C, bras morts > 1m, bouclage absent, test pression non réalisé.",
    'cvc': "Retours terrain ASSISTEC: données météo incorrectes (Paris au lieu de Dakar: T=34-36C, HR=70%), extracteurs non certifiés 400C/2h, fluides F-Gaz non conformes.",
    'securite_incendie': "Retours terrain ASSISTEC: détecteurs optiques en parking (doivent être thermiques), matrice SSI absente, câblage CR1 non prévu, colonnes sèches absentes.",
    'courant_faible': "Retours terrain ASSISTEC: budget PoE non calculé, déverrouillage accès sur alarme incendie absent, badges 125kHz copiables.",
    'ascenseur': "Retours terrain ASSISTEC: UCMP absent (NF EN 81-20:2020), rappel niveau évacuation non asservi SSI, manoeuvre pompiers non conforme.",
    'fd_c17205': "Retours terrain ASSISTEC: S=MAX(Sa,Sb,Sc,Sd) non appliqué, IB non conforme Tableaux 2-3, résistivité incorrecte.",
    'reception': "Retours terrain ASSISTEC: PV de terre absents, essais DDR non réalisés, schémas recollement jamais fournis."
}

# ── Fichiers statiques ────────────────────────────────────────
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
        "version": VERSION,
        "points_total": POINTS,
        "matrice_chargee": bool(MATRICE),
        "app": "ASSISTEC",
        "serveur": "OK",
        "cle_serveur": bool(API_KEY),
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

# ── Analyse principale — tout se passe ici ───────────────────
@app.route('/api/analyser', methods=['POST'])
def analyser():
    if not API_KEY:
        return jsonify({"error": "Cle API non configuree sur le serveur"}), 500

    try:
        data = request.get_json(force=True, silent=True) or {}

        lot        = data.get('lot', 'electricite')
        type_bat   = data.get('type_batiment', '')
        type_doc   = data.get('type_document', '')
        projet     = data.get('projet', 'Projet')
        controleur = data.get('controleur', 'ASSISTEC')
        fichier_b64 = data.get('fichier_b64', '')
        fichier_type = data.get('fichier_type', 'application/pdf')

        # Récupérer les points de la matrice pour ce lot
        cle_excel = LOT_MAPPING.get(lot, 'Électricité')
        points = MATRICE.get(cle_excel, [])
        contexte = CONTEXTE.get(lot, '')

        # Construire la liste des points (ASCII uniquement)
        points_txt = ''
        for i, p in enumerate(points[:80], 1):  # max 80 points par analyse
            sev = p.get('s', '')
            pt  = p.get('p', '').encode('ascii', 'replace').decode('ascii')
            nrm = p.get('n', '').encode('ascii', 'replace').decode('ascii')
            obs = p.get('o', '')[:150].encode('ascii', 'replace').decode('ascii')
            points_txt += f"{i}. [{sev}] {pt} | {nrm} | {obs}\n"

        nb_points = len(points)
        lot_nom = cle_excel.encode('ascii', 'replace').decode('ascii')

        system_prompt = (
            f"Tu es un expert en controle technique de batiments pour le bureau ASSISTEC au Senegal.\n"
            f"Lot: {lot_nom} | Batiment: {type_bat} | Document: {type_doc}\n"
            f"Projet: {projet} | Controleur: {controleur}\n\n"
            f"MATRICE ({nb_points} points):\n{points_txt}\n"
            f"CONTEXTE TERRAIN: {contexte}\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Lis le document fourni\n"
            f"2. Verifie chaque point de la matrice\n"
            f"3. Genere une reserve UNIQUEMENT si non-conforme ou manquant\n"
            f"4. Observations courtes et directes (2 phrases max)\n"
            f"5. Reponds UNIQUEMENT en JSON valide\n\n"
            f"FORMAT JSON:\n"
            f"{{\"reserves\":[{{\"point\":\"...\",\"severite\":\"CRITIQUE|MAJEURE|MINEURE\","
            f"\"norme\":\"...\",\"observation\":\"...\",\"element_concerne\":\"...\"}}],"
            f"\"points_conformes\":[\"...\"],\"resume\":\"...\"}}"
        )

        # Construire le message avec le fichier
        if fichier_b64 and fichier_type == 'application/pdf':
            contenu = [
                {"type": "document", "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": fichier_b64
                }},
                {"type": "text", "text": f"Analyse ce document et genere les reserves en JSON."}
            ]
        elif fichier_b64 and fichier_type.startswith('image/'):
            contenu = [
                {"type": "image", "source": {
                    "type": "base64",
                    "media_type": fichier_type,
                    "data": fichier_b64
                }},
                {"type": "text", "text": "Analyse ce plan et genere les reserves en JSON."}
            ]
        else:
            contenu = [{"type": "text",
                       "text": f"Analyse le document {type_doc} pour {projet} et genere les reserves en JSON."}]

        payload = json.dumps({
            "model": "claude-sonnet-4-6",
            "max_tokens": 4000,
            "system": system_prompt,
            "messages": [{"role": "user", "content": contenu}]
        }, ensure_ascii=True).encode('ascii')

        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'x-api-key': API_KEY,
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
