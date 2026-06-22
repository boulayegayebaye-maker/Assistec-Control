from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
import os, json, urllib.request, urllib.error, base64
from datetime import datetime

app = Flask(__name__)
CORS(app)

API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
VERSION = "12"
POINTS = 594

MATRICE = {}
try:
    with open('matrice_data.json', 'r', encoding='utf-8') as f:
        MATRICE = json.load(f)
    print(f"Matrice: {sum(len(v) for v in MATRICE.values())} points")
except Exception as e:
    print(f"Matrice non trouvee: {e}")

LOT_MAPPING = {
    'electricite':       'Electricite',
    'plomberie':         'Plomberie sanitaire',
    'cvc':               'CVC',
    'securite_incendie': 'Securite incendie',
    'courant_faible':    'Courant faible - Video',
    'ascenseur':         'Ascenseur',
    'fd_c17205':         'FD C17-205',
    'reception':         'Verification et Reception'
}

LOT_MAPPING_EXCEL = {
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
    'electricite': "Retours terrain: IB non calcule par circuit, Ku/Ks/Ke absents, DDR 30mA absents, schemas incomplets, prise de terre > 10 Ohm.",
    'plomberie': "Retours terrain: ECS < 50C, bras morts > 1m, bouclage absent, test pression non realise.",
    'cvc': "Retours terrain: donnees meteo incorrectes (utiliser T=34-36C HR=70% pour Dakar), extracteurs non certifies 400C/2h.",
    'securite_incendie': "Retours terrain: detecteurs optiques en parking (doivent etre thermiques), matrice SSI absente, cablage CR1 non prevu.",
    'courant_faible': "Retours terrain: budget PoE non calcule, deverrouillage acces sur alarme incendie absent.",
    'ascenseur': "Retours terrain: UCMP absent (NF EN 81-20:2020), rappel niveau evacuation non asservi SSI.",
    'fd_c17205': "Retours terrain: S=MAX(Sa,Sb,Sc,Sd) non applique, IB non conforme Tableaux 2-3.",
    'reception': "Retours terrain: PV de terre absents, essais DDR non realises."
}

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
        "app": "ASSISTEC",
        "serveur": "OK",
        "cle_serveur": bool(API_KEY),
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

@app.route('/api/analyser', methods=['POST'])
def analyser():
    if not API_KEY:
        return jsonify({"error": "Cle API non configuree"}), 500
    try:
        # Lire depuis FormData
        lot        = request.form.get('lot', 'electricite')
        type_bat   = request.form.get('type_batiment', '')
        type_doc   = request.form.get('type_document', '')
        projet     = request.form.get('projet', 'Projet')
        controleur = request.form.get('controleur', 'ASSISTEC')
        fichier_b64  = request.form.get('fichier_b64', '')
        fichier_type = request.form.get('fichier_type', 'application/pdf')

        # Récupérer les points de la matrice
        cle_excel = LOT_MAPPING_EXCEL.get(lot, 'Electricite')
        points = MATRICE.get(cle_excel, [])
        contexte = CONTEXTE.get(lot, '')
        lot_nom = LOT_MAPPING.get(lot, lot)

        # Construire la liste des points en ASCII
        points_txt = ''
        for i, p in enumerate(points[:80], 1):
            sev = str(p.get('s', ''))
            pt  = str(p.get('p', ''))[:100]
            nrm = str(p.get('n', ''))[:50]
            obs = str(p.get('o', ''))[:120]
            # Encoder en ASCII
            pt  = pt.encode('ascii', 'replace').decode('ascii')
            nrm = nrm.encode('ascii', 'replace').decode('ascii')
            obs = obs.encode('ascii', 'replace').decode('ascii')
            points_txt += f"{i}.[{sev}] {pt} | {nrm} | {obs}\n"

        # System prompt en ASCII pur
        sys_prompt = (
            f"Tu es un expert controle technique batiments bureau ASSISTEC Senegal.\n"
            f"Lot:{lot_nom} | Batiment:{type_bat} | Document:{type_doc}\n"
            f"Projet:{projet} | Controleur:{controleur}\n\n"
            f"MATRICE DE CONTROLE ({len(points)} points):\n{points_txt}\n"
            f"CONTEXTE: {contexte}\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Lis le document fourni attentivement\n"
            f"2. Pour chaque point de la matrice verifie la conformite\n"
            f"3. Genere une reserve UNIQUEMENT si non-conforme ou manquant\n"
            f"4. Observations courtes et directes (2 phrases max)\n"
            f"5. Reponds UNIQUEMENT en JSON valide sans markdown\n\n"
            f'FORMAT: {{"reserves":[{{"point":"...","severite":"CRITIQUE|MAJEURE|MINEURE","norme":"...","observation":"...","element_concerne":"..."}}],"points_conformes":["..."],"resume":"..."}}'
        )

        # Encoder en ASCII
        sys_prompt = sys_prompt.encode('ascii', 'replace').decode('ascii')

        # Construire le message
        if fichier_b64 and fichier_type == 'application/pdf':
            contenu = [
                {"type": "document", "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": fichier_b64
                }},
                {"type": "text", "text": "Analyse ce document et genere les reserves en JSON."}
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
            "system": sys_prompt,
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
