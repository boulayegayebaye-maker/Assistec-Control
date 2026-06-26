from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
import os, json, base64, urllib.request, urllib.error
from datetime import datetime

app = Flask(__name__)
CORS(app)

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# Charger la matrice une seule fois au demarrage
MATRICE = {}
CONTEXTE_TERRAIN = {
    'Electricite': (
        "RETOURS TERRAIN ASSISTEC (380 observations) :\n"
        "- Prise de terre : valeur souvent > 10 Ohm GE, piquets mal enfonces, regards absents\n"
        "- Coffrets : schemas absents, calibres incoherents, selectivite non assuree\n"
        "- DDR 30mA absents en amont circuits terminaux, max 8 circuits par DDR depasse\n"
        "- BAES : hauteurs non respectees, sens evacuation incorrect\n"
        "- Groupe electrogene : non raccorde a la terre, bac a sable absent\n"
        "- IB non calcule circuit par circuit, Ku/Ks/Ke absents"
    ),
    'Plomberie sanitaire': (
        "RETOURS TERRAIN ASSISTEC (232 observations) :\n"
        "- Canalisations sous-dimensionnees, surpresseur non conforme aux plans\n"
        "- Tests de pression jamais realises avant carrelage\n"
        "- Chutes EU/EV non ventilees, separation EU/EV non assuree\n"
        "- Bras morts ECS > 1 m frequents, temperatures ECS < 50 degC en distribution\n"
        "- Mitigeurs thermostatiques absents, bouclage ECS non prevu"
    ),
    'CVC': (
        "RETOURS TERRAIN ASSISTEC (54 observations) :\n"
        "- Bilan thermique absent ou global sans detail par local\n"
        "- Donnees meteo de Paris utilisees pour Dakar (T base ete 36 degC, HR 75%)\n"
        "- Fluides frigorigenes non conformes F-Gaz (R410A en phase out)\n"
        "- Extracteurs de desenfumage non certifies 400degC/2h\n"
        "- Isolation incomplete, fuites condensats (siphon absent)"
    ),
    'Securite incendie': (
        "RETOURS TERRAIN ASSISTEC (68 observations) :\n"
        "- Detecteurs optiques en parking et cuisine (doivent etre thermiques)\n"
        "- Desenfumage parking absent, amenee d air de compensation absente\n"
        "- Cablage CR1 non prevu sur boucles detection et commandes DAS\n"
        "- Matrice de concordance ZD/ZS absente du dossier SSI\n"
        "- Colonnes seches absentes des SS2 en habitation"
    ),
    'Courant faible - Video': (
        "RETOURS TERRAIN ASSISTEC (21 observations) :\n"
        "- Fiches techniques cameras absentes, resolution non justifiee\n"
        "- Budget PoE total du switch non calcule\n"
        "- Duree de retention NVR non calculee\n"
        "- Deverrouillage controle d acces sur alarme incendie non prevu\n"
        "- Badges RFID 125 kHz retenus (copiables facilement)"
    ),
    'Ascenseur': (
        "RETOURS TERRAIN ASSISTEC (9 observations) :\n"
        "- Manoeuvre pompiers Phase 2 absente ou non conforme NF EN 81-72:2020\n"
        "- UCMP absent (exigence NF EN 81-20:2020 souvent meconnue)\n"
        "- Rappel au niveau d evacuation non asservi au SSI\n"
        "- Hauteur de fosse insuffisante, survol insuffisant"
    ),
    'FD C17-205': (
        "RETOURS TERRAIN ASSISTEC - FD C17-205 :\n"
        "- Calcul IB absent ou non conforme aux Tableaux 2-3\n"
        "- Section S retenue non justifiee (S = MAX(Sa,Sb,Sc,Sd) non applique)\n"
        "- Longueurs L et l confondues dans les formules de chute de tension"
    ),
    'Reception': (
        "RETOURS TERRAIN ASSISTEC - RECEPTION :\n"
        "- PV de mesure de resistance de terre absents\n"
        "- Essais DDR non realises avant reception\n"
        "- Schemas de recollement jamais fournis\n"
        "- Contrat de maintenance non souscrit a la livraison"
    )
}

LOT_MAPPING = {
    'electricite':       'Electricite',
    'plomberie':         'Plomberie sanitaire',
    'cvc':               'CVC',
    'securite_incendie': 'Securite incendie',
    'courant_faible':    'Courant faible - Video',
    'ascenseur':         'Ascenseur',
    'fd_c17205':         'FD C17-205',
    'reception':         'Reception'
}

LOT_NOMS = {
    'electricite':       'Electricite',
    'plomberie':         'Plomberie sanitaire',
    'cvc':               'CVC - Climatisation - VMC',
    'securite_incendie': 'Securite incendie',
    'courant_faible':    'Courant faible - Videosurveillance',
    'ascenseur':         'Ascenseur',
    'fd_c17205':         'FD C17-205 (Sections conducteurs)',
    'reception':         'Verification et Reception'
}

def charger_matrice():
    global MATRICE
    chemin = os.path.join(os.path.dirname(__file__), 'matrice_data.json')
    if os.path.exists(chemin):
        with open(chemin, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        # Re-indexer par cle simplifiee
        for lot_key, lot_nom in LOT_MAPPING.items():
            # Chercher dans raw par correspondance partielle
            for raw_key, points in raw.items():
                raw_clean = raw_key.lower().replace(' ', '').replace('&', '').replace('-', '')
                lot_clean = lot_nom.lower().replace(' ', '').replace('&', '').replace('-', '')
                if lot_clean[:8] in raw_clean or raw_clean[:8] in lot_clean:
                    MATRICE[lot_key] = points
                    break
        print(f"Matrice chargee: {sum(len(v) for v in MATRICE.values())} points")
    else:
        print("ATTENTION: matrice_data.json introuvable")

charger_matrice()

def nettoyer_ascii(texte):
    """Convertir en ASCII pur pour le prompt."""
    if not texte:
        return ''
    result = ''
    for c in str(texte):
        if ord(c) < 128:
            result += c
        else:
            # Translitteration basique
            table = {
                'e': 'eeeeeEEEEE', 'a': 'aaaaAAA', 'i': 'iiII', 'o': 'ooOO', 'u': 'uuUU',
                'c': 'c', 'n': 'n'
            }
            encoded = c.encode('ascii', 'ignore').decode('ascii')
            if encoded:
                result += encoded
            else:
                try:
                    import unicodedata
                    norm = unicodedata.normalize('NFD', c)
                    ascii_c = norm.encode('ascii', 'ignore').decode('ascii')
                    result += ascii_c if ascii_c else '?'
                except:
                    result += '?'
    return result

def selectionner_points(points, type_doc, max_points=60):
    """Selectionner les points les plus pertinents."""
    if len(points) <= max_points:
        return points

    mots_cles = {
        'bilan_puissance':        ['bilan', 'puissance', 'Ke', 'Ks', 'Ku', 'IB', 'GE', 'groupe', 'simultaneite'],
        'note_calcul_elec':       ['calcul', 'section', 'cable', 'chute', 'tension', 'IB', 'courant'],
        'schema_unifilaire':      ['schema', 'unifilaire', 'TGBT', 'disjoncteur', 'DDR', 'selectivite'],
        'schema_coffret':         ['coffret', 'disjoncteur', 'DDR', 'calibre'],
        'plan_implantation_elec': ['plan', 'implantation', 'BAES', 'prise', 'eclairage'],
        'plan_mise_terre':        ['terre', 'piquet', 'regard', 'equipotentielle'],
        'bilan_thermique':        ['thermique', 'bilan', 'charge', 'meteo', 'frigorigene'],
        'note_calcul_vmc':        ['VMC', 'debit', 'aeraulique', 'extraction'],
        'plan_cvc':               ['plan', 'CVC', 'gaine', 'climatisation'],
        'notice_securite':        ['notice', 'securite', 'classification', 'ERP', 'IGH'],
        'plan_detection':         ['detection', 'detecteur', 'centrale', 'boucle', 'SSI'],
        'plan_desenfumage':       ['desenfumage', 'extracteur', 'commande'],
        'dossier_ssi':            ['SSI', 'CMSI', 'DAS', 'matrice', 'concordance'],
        'plan_videosurveillance': ['camera', 'CCTV', 'NVR', 'PoE', 'resolution'],
        'plan_controle_acces':    ['controle', 'acces', 'badge', 'lecteur'],
        'dossier_ascenseur':      ['ascenseur', 'UCMP', 'pompiers', 'fosse'],
        'note_calcul_plomb':      ['debit', 'pression', 'ECS', 'EU', 'EV'],
        'plan_alimentation_eau':  ['eau', 'EF', 'ECS', 'bouclage', 'colonne'],
        'plan_evacuation':        ['evacuation', 'EU', 'EV', 'EP', 'collecteur']
    }

    mots = mots_cles.get(type_doc, [])
    scores = []
    for p in points:
        texte = (str(p.get('p', '')) + ' ' + str(p.get('o', '')) + ' ' + str(p.get('sec', ''))).lower()
        score = 3 if p.get('s') == 'CRITIQUE' else (1 if p.get('s') == 'MAJEURE' else 0)
        for mc in mots:
            if mc.lower() in texte:
                score += 2
        scores.append(score)

    indices = sorted(range(len(scores)), key=lambda i: -scores[i])[:max_points]
    indices.sort()
    return [points[i] for i in indices]

def construire_prompt(lot, type_bat, type_doc, projet, controleur):
    """Construire le system prompt entierement cote serveur."""
    points_raw = MATRICE.get(lot, [])
    contexte_key = LOT_MAPPING.get(lot, lot)
    contexte = CONTEXTE_TERRAIN.get(contexte_key, '')
    nom_lot = LOT_NOMS.get(lot, lot)

    points = selectionner_points(points_raw, type_doc, 60)

    lignes = []
    for i, p in enumerate(points):
        sev   = nettoyer_ascii(p.get('s', 'MAJEURE'))
        pt    = nettoyer_ascii(p.get('p', ''))[:100]
        norme = nettoyer_ascii(p.get('n', 'N/A'))
        obs   = nettoyer_ascii(p.get('o', ''))[:120]
        lignes.append(f"{i+1}.[{sev}] {pt} | {norme} | {obs}")

    points_str = '\n'.join(lignes)
    nom_lot_ascii = nettoyer_ascii(nom_lot)
    contexte_ascii = nettoyer_ascii(contexte)

    prompt = (
        f"Tu es un expert controle technique batiment (bureau ASSISTEC, Senegal).\n"
        f"LOT: {nom_lot_ascii} | BATIMENT: {type_bat} | DOCUMENT: {type_doc}\n"
        f"PROJET: {nettoyer_ascii(projet)} | CONTROLEUR: {nettoyer_ascii(controleur)}\n\n"
        f"MATRICE ({len(points)} points sur {len(points_raw)}):\n"
        f"{points_str}\n\n"
        f"{contexte_ascii}\n\n"
        "REGLES:\n"
        "- Verifie chaque point de la matrice sur le document fourni\n"
        "- Reserve UNIQUEMENT si non-conformite reelle ou donnee manquante\n"
        "- Observations courtes (1-2 phrases), directes, professionnelles\n"
        "- Reponds UNIQUEMENT en JSON valide, aucun texte avant ou apres\n\n"
        'FORMAT: {"reserves":[{"point":"...","severite":"CRITIQUE|MAJEURE|MINEURE",'
        '"norme":"...","observation":"...","element_concerne":"..."}],'
        '"points_conformes":["..."],"resume":"Synthese 2 phrases"}'
    )
    return prompt

# ── Fichiers statiques ──────────────────────────────────────
@app.route('/')
def index():
    return send_file('app_assistec_v4.html')

@app.route('/app_assistec_v4.html')
def app_html():
    return send_file('app_assistec_v4.html')

@app.route('/matrice.js')
def matrice_js():
    return send_file('matrice.js', mimetype='application/javascript; charset=utf-8')

@app.route('/manifest.json')
def manifest():
    return send_file('manifest.json', mimetype='application/json')

@app.route('/sw.js')
def sw():
    return send_file('sw.js', mimetype='application/javascript')

# ── API version ─────────────────────────────────────────────
@app.route('/api/version')
def version():
    return jsonify({
        "app": "ASSISTEC Controle Technique",
        "matrice_points": sum(len(v) for v in MATRICE.values()),
        "lots": list(MATRICE.keys()),
        "cle_serveur": bool(ANTHROPIC_API_KEY),
        "timestamp": datetime.utcnow().isoformat()
    })

# ── Analyse — le serveur fait TOUT ──────────────────────────
@app.route('/api/analyser', methods=['POST'])
def analyser():
    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "Cle API non configuree sur le serveur"}), 500

    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"error": "Donnees manquantes"}), 400

        lot          = data.get('lot', 'electricite')
        type_bat     = data.get('type_batiment', '')
        type_doc     = data.get('type_document', '')
        projet       = data.get('projet', 'Projet sans nom')
        controleur   = data.get('controleur', 'ASSISTEC')
        fichier_b64  = data.get('fichier_base64', '')
        fichier_type = data.get('fichier_type', 'application/pdf')
        fichier_nom  = data.get('fichier_nom', '')

        # Construire le prompt cote serveur
        system_prompt = construire_prompt(lot, type_bat, type_doc, projet, controleur)

        # Construire le message utilisateur
        if fichier_b64:
            if fichier_type == 'application/pdf':
                contenu = [
                    {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": fichier_b64}},
                    {"type": "text", "text": f"Analyse ce document. Reponds uniquement en JSON."}
                ]
            elif fichier_type.startswith('image/'):
                contenu = [
                    {"type": "image", "source": {"type": "base64", "media_type": fichier_type, "data": fichier_b64}},
                    {"type": "text", "text": "Analyse ce plan. Reponds uniquement en JSON."}
                ]
            else:
                contenu = [{"type": "text", "text": f"Fichier: {fichier_nom}. Genere les reserves en JSON."}]
        else:
            contenu = [{"type": "text", "text": "Genere les reserves probables en JSON."}]

        payload = json.dumps({
            "model": "claude-sonnet-4-6",
            "max_tokens": 6000,
            "system": system_prompt,
            "messages": [{"role": "user", "content": contenu}]
        }).encode('utf-8')

        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'x-api-key': ANTHROPIC_API_KEY,
                'anthropic-version': '2023-06-01'
            },
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return jsonify(result)

    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        try:
            return jsonify({"error": json.loads(body)}), e.code
        except:
            return jsonify({"error": body}), e.code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    return jsonify({"status": "ok", "app": "ASSISTEC", "matrice": sum(len(v) for v in MATRICE.values())})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
