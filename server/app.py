import os
import time
import threading
import requests
from flask import Flask, request, render_template_string, jsonify, redirect, url_for, session, flash
from dotenv import load_dotenv
from users import verify_user, change_password

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))  # Pour les sessions Flask

# Durée de la session en secondes (12 heures par défaut)
app.config['PERMANENT_SESSION_LIFETIME'] = int(os.getenv("SESSION_LIFETIME", 12 * 3600))

# ==============================
# Config minimale
# ==============================
AGENT_HEARTBEAT_TIMEOUT = 40          # secondes avant de considérer un agent offline
AGENT_SELECTION_CPU_WEIGHT = 1.0
AGENT_SELECTION_MEM_WEIGHT = 0.7
REQUEST_TIMEOUT_SECONDS = 12          # timeout d'appel HTTP vers l'agent
FALLBACK_RETRY_DELAY = 1.0            # pause entre essais d'agents
IMAGES_FILE = "images.txt"

# ==============================
# Stockage en mémoire
# ==============================
agents = {}  # agent_id -> dict(info)

# ==============================
# Lecture des images autorisées
# ==============================
def load_images():
    images = []
    if os.path.exists(IMAGES_FILE):
        with open(IMAGES_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    images.append(line)
    else:
        # fallback : liste codée en dur
        images = [
            "monorg/rdp-ubuntu:latest",
            "monorg/rdp-debian:latest",
            "monorg/rdp-fedora:latest"
        ]
    return images

AVAILABLE_IMAGES = load_images()

# ==============================
# Templates HTML
# ==============================

# Template de connexion
LOGIN_PAGE = '''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Connexion - Bureaux Virtuels Distribués</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: system-ui,-apple-system,Segoe UI,Roboto,sans-serif; background:#f5f6fa; margin:0; padding:25px; color:#222;}
        .card { background:#fff; padding:20px; border-radius:10px; box-shadow:0 4px 10px rgba(0,0,0,0.06); max-width:450px; margin:50px auto 25px; }
        h1, h2 { margin-top:0; text-align:center; }
        label { display:block; margin-top:12px; font-weight:600; }
        input { width:100%; padding:10px; font-size:15px; border:1px solid #ccc; border-radius:6px; }
        button { margin-top:20px; background:#4361ee; color:#fff; border:none; padding:12px 18px; border-radius:6px; font-size:16px; cursor:pointer; width:100%;}
        button:hover { background:#364dcc; }
        .alert { padding:10px; border-radius:6px; margin-bottom:15px; }
        .alert-danger { background:#ffebee; color:#c62828; }
        .footer { margin-top:40px; font-size:12px; text-align:center; color:#666; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Connexion</h1>
        {% if error %}
        <div class="alert alert-danger">{{ error }}</div>
        {% endif %}
        <form method="post" action="/login">
            <label for="username">Nom d'utilisateur :</label>
            <input type="text" id="username" name="username" required autofocus>
            <label for="password">Mot de passe :</label>
            <input type="password" id="password" name="password" required>
            <button type="submit">Se connecter</button>
        </form>
    </div>
    <div class="footer">
        Bureaux Virtuels Distribués - Connexion sécurisée requise
    </div>
</body>
</html>
'''

# Template de changement de mot de passe
CHANGE_PASSWORD_PAGE = '''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Changement de mot de passe - Bureaux Virtuels Distribués</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: system-ui,-apple-system,Segoe UI,Roboto,sans-serif; background:#f5f6fa; margin:0; padding:25px; color:#222;}
        .card { background:#fff; padding:20px; border-radius:10px; box-shadow:0 4px 10px rgba(0,0,0,0.06); max-width:450px; margin:50px auto 25px; }
        h1, h2 { margin-top:0; text-align:center; }
        label { display:block; margin-top:12px; font-weight:600; }
        input { width:100%; padding:10px; font-size:15px; border:1px solid #ccc; border-radius:6px; }
        button { margin-top:20px; background:#4361ee; color:#fff; border:none; padding:12px 18px; border-radius:6px; font-size:16px; cursor:pointer; width:100%;}
        button:hover { background:#364dcc; }
        .alert { padding:10px; border-radius:6px; margin-bottom:15px; }
        .alert-danger { background:#ffebee; color:#c62828; }
        .alert-info { background:#e3f2fd; color:#0d47a1; }
        .footer { margin-top:40px; font-size:12px; text-align:center; color:#666; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Changement de mot de passe</h1>
        <div class="alert alert-info">Première connexion : veuillez changer votre mot de passe.</div>
        {% if error %}
        <div class="alert alert-danger">{{ error }}</div>
        {% endif %}
        <form method="post" action="/change-password">
            <label for="new_password">Nouveau mot de passe :</label>
            <input type="password" id="new_password" name="new_password" required autofocus>
            <label for="confirm_password">Confirmez le mot de passe :</label>
            <input type="password" id="confirm_password" name="confirm_password" required>
            <button type="submit">Changer le mot de passe</button>
        </form>
    </div>
    <div class="footer">
        Bureaux Virtuels Distribués - Sécurisez votre compte
    </div>
</body>
</html>
'''

# Template principale (mise à jour pour inclure déconnexion)
MAIN_PAGE = '''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Bureaux Virtuels Distribués</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: system-ui,-apple-system,Segoe UI,Roboto,sans-serif; background:#f5f6fa; margin:0; padding:25px; color:#222;}
        h1 { margin-top:0; }
        .card { background:#fff; padding:20px; border-radius:10px; box-shadow:0 4px 10px rgba(0,0,0,0.06); max-width:950px; margin:0 auto 25px; }
        label { display:block; margin-top:12px; font-weight:600; }
        input, select { width:100%; padding:10px; font-size:15px; border:1px solid #ccc; border-radius:6px; }
        button { margin-top:20px; background:#4361ee; color:#fff; border:none; padding:12px 18px; border-radius:6px; font-size:16px; cursor:pointer;}
        button:hover { background:#364dcc; }
        pre { background:#111; color:#0f0; padding:15px; border-radius:8px; overflow:auto; font-size:14px; }
        .agents { font-size:14px; background:#fff; padding:15px; border-radius:8px; margin-top:10px; }
        .agent-offline { opacity:0.5; }
        .badge { display:inline-block; padding:3px 8px; border-radius:4px; font-size:12px; background:#eee; margin-right:6px;}
        .ok { color:#2e7d32; }
        .err { color:#c62828; }
        .warn { color:#ed6c02; }
        .footer { margin-top:40px; font-size:12px; text-align:center; color:#666; }
        .flex { display:flex; gap:16px; flex-wrap:wrap; }
        .half { flex:1 1 320px; }
        .small { width:140px; display:inline-block; }
        .user-info { text-align:right; margin-bottom:20px; }
        .logout-btn { display:inline-block; background:none; border:1px solid #ccc; color:#333; padding:5px 10px; font-size:14px; cursor:pointer; text-decoration:none; }
        .logout-btn:hover { background:#f5f5f5; }
    </style>
</head>
<body>
    <div class="user-info">
        Connecté en tant que: <strong>{{ username }}</strong> | 
        <a href="/logout" class="logout-btn">Déconnexion</a>
    </div>
    <h1>Bureaux Virtuels Distribués</h1>
    <div class="card">
        <form id="launchForm">
            <label>Image Docker :</label>
            <select name="image">
                {% for img in images %}
                <option value="{{ img }}">{{ img }}</option>
                {% endfor %}
            </select>
            <div class="flex">
                <div class="half">
                    <label>CPU (vCPUs) :</label>
                    <input type="number" name="cpu_limit" min="1" value="2">
                </div>
                <div class="half">
                    <label>Mémoire (GB) :</label>
                    <input type="number" name="memory_limit_gb" min="1" value="4">
                </div>
            </div>
            <label>
               <input type="checkbox" name="gpu" value="1"> Utiliser GPU (si dispo)
            </label>
            <button type="submit">Lancer le bureau</button>
        </form>
    </div>
    <div class="card">
        <h2>Résultat</h2>
        <pre id="output">En attente...</pre>
    </div>
    <div class="card">
        <h2>Agents enregistrés</h2>
        <div class="agents" id="agentsBox">
            Chargement...
        </div>
    </div>
    <div class="footer">
        MVP - Pas de persistance / chaque lancement crée un nouveau conteneur - Fallback auto si un agent échoue.
    </div>

<script>
async function refreshAgents(){
    try{
        const r = await fetch('/api/agents');
        const data = await r.json();
        const box = document.getElementById('agentsBox');
        if(!data.agents.length){
            box.innerHTML = "<i>Aucun agent actif.</i>";
            return;
        }
        let html = '<table style="width:100%; border-collapse:collapse;">';
        html += '<tr style="text-align:left;"><th>ID</th><th>URL</th><th>CPU</th><th>Mémoire</th><th>Conteneurs</th><th>Vu</th></tr>';
        data.agents.forEach(a=>{
            const cls = a.online ? '' : 'agent-offline';
            html += `<tr class="${cls}">
                <td>${a.agent_id}</td>
                <td>${a.url}</td>
                <td>${a.used_cpu.toFixed(1)}/${a.total_cpu}</td>
                <td>${a.used_mem_mb}/${a.total_mem_mb} MB</td>
                <td>${a.running_containers}</td>
                <td>${a.seconds_since_last_seen}s</td>
            </tr>`;
        });
        html += '</table>';
        box.innerHTML = html;
    }catch(e){
        console.error(e);
    }
}
setInterval(refreshAgents, 5000);
refreshAgents();

document.getElementById('launchForm').addEventListener('submit', async (e)=>{
    e.preventDefault();
    const out = document.getElementById('output');
    out.textContent = "Sélection de l'agent et envoi de la requête...";
    const formData = new FormData(e.target);
    const payload = {
        username: "{{ username }}",  // Utilisation du nom d'utilisateur connecté
        password: "{{ password }}",  // Le mot de passe est géré par le serveur
        image: formData.get('image'),
        cpu_limit: parseInt(formData.get('cpu_limit'),10),
        memory_limit_gb: parseInt(formData.get('memory_limit_gb'),10),
        gpu: formData.get('gpu') === '1'
    };
    try{
        const r = await fetch('/launch', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify(payload)
        });
        const txt = await r.text();
        out.textContent = txt;
    }catch(err){
        out.textContent = "Erreur réseau: " + err;
    }
});
</script>
</body>
</html>
'''

# ==============================
# Utilitaires
# ==============================
def now():
    return time.time()

def prune_dead_agents():
    """Nettoie les agents très vieux (optionnel)."""
    to_delete = []
    for aid, info in agents.items():
        if now() - info['last_seen'] > 3600:  # 1h
            to_delete.append(aid)
    for aid in to_delete:
        agents.pop(aid, None)

def compute_agent_score(info: dict) -> float:
    """
    Score plus haut = plus intéressant.
    On prend CPU libre + mémoire libre pondérée - pénalité conteneurs.
    """
    free_cpu = max(info['total_cpu'] - info['used_cpu'], 0)
    free_mem = max(info['total_mem_mb'] - info['used_mem_mb'], 0)
    # pondération simple
    score = (free_cpu * AGENT_SELECTION_CPU_WEIGHT) + \
            ((free_mem / 1024.0) * AGENT_SELECTION_MEM_WEIGHT) - \
            (info['running_containers'] * 0.2)
    return score

def list_sorted_candidate_agents(required_cpu: int, required_mem_mb: int, require_gpu: bool):
    """
    Retourne les agents triés par score desc qui ont potentiellement la capacité.
    (On fait simple : on suppose que l'agent sait gérer la contrainte GPU si besoin via un flag 'gpu_capable')
    """
    candidates = []
    now_ts = now()
    for info in agents.values():
        offline = (now_ts - info['last_seen']) > AGENT_HEARTBEAT_TIMEOUT
        if offline:
            continue
        if require_gpu and not info.get('gpu_capable', False):
            continue
        # Check ressources grossière
        if (info['total_cpu'] - info['used_cpu']) < required_cpu:
            continue
        if (info['total_mem_mb'] - info['used_mem_mb']) < required_mem_mb:
            continue
        candidates.append(info)
    # tri par score desc
    candidates.sort(key=lambda x: compute_agent_score(x), reverse=True)
    return candidates

# ==============================
# Middleware d'authentification
# ==============================
def login_required(view_func):
    def wrapped_view(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        # Vérifier si l'utilisateur doit changer son mot de passe
        if session.get('first_login', False):
            return redirect(url_for('change_password_page'))
        return view_func(*args, **kwargs)
    wrapped_view.__name__ = view_func.__name__
    return wrapped_view

# ==============================
# Routes d'authentification
# ==============================
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not (username and password):
            error = "Veuillez remplir tous les champs."
        else:
            auth_success, first_login = verify_user(username, password)
            if auth_success:
                session['username'] = username
                session['password'] = password  # Stocké pour les requêtes RDP
                session['first_login'] = first_login
                
                if first_login:
                    return redirect(url_for('change_password_page'))
                return redirect(url_for('index'))
            else:
                error = "Nom d'utilisateur ou mot de passe incorrect."
    
    return render_template_string(LOGIN_PAGE, error=error)

@app.route('/change-password', methods=['GET', 'POST'])
def change_password_page():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    error = None
    if request.method == 'POST':
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        if not (new_password and confirm_password):
            error = "Veuillez remplir tous les champs."
        elif new_password != confirm_password:
            error = "Les mots de passe ne correspondent pas."
        elif len(new_password) < 6:
            error = "Le mot de passe doit contenir au moins 6 caractères."
        else:
            if change_password(session['username'], new_password):
                session['password'] = new_password
                session['first_login'] = False
                return redirect(url_for('index'))
            else:
                error = "Erreur lors du changement de mot de passe."
    
    return render_template_string(CHANGE_PASSWORD_PAGE, error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==============================
# Routes page principale
# ==============================
@app.route('/')
@login_required
def index():
    return render_template_string(
        MAIN_PAGE, 
        images=AVAILABLE_IMAGES,
        username=session.get('username', ''),
        password=session.get('password', '')
    )

# ==============================
# Heartbeat Agents
# ==============================
@app.route('/api/agents/heartbeat', methods=['POST'])
def agent_heartbeat():
    data = request.get_json(force=True, silent=True) or {}
    required = ['agent_id', 'url', 'total_cpu', 'used_cpu', 'total_mem_mb', 'used_mem_mb', 'running_containers']
    for k in required:
        if k not in data:
            return jsonify({'error': f'champ manquant: {k}'}), 400

    agent_id = str(data['agent_id'])
    agents[agent_id] = {
        'agent_id': agent_id,
        'url': data['url'].rstrip('/'),
        'last_seen': now(),
        'total_cpu': float(data['total_cpu']),
        'used_cpu': float(data['used_cpu']),
        'total_mem_mb': int(data['total_mem_mb']),
        'used_mem_mb': int(data['used_mem_mb']),
        'running_containers': int(data['running_containers']),
        'gpu_capable': bool(data.get('gpu_capable', False))
    }
    return jsonify({'status': 'ok'})

@app.route('/api/agents')
@login_required
def api_list_agents():
    out = []
    now_ts = now()
    for info in agents.values():
        seconds = int(now_ts - info['last_seen'])
        out.append({
            'agent_id': info['agent_id'],
            'url': info['url'],
            'total_cpu': info['total_cpu'],
            'used_cpu': info['used_cpu'],
            'total_mem_mb': info['total_mem_mb'],
            'used_mem_mb': info['used_mem_mb'],
            'running_containers': info['running_containers'],
            'seconds_since_last_seen': seconds,
            'online': seconds <= AGENT_HEARTBEAT_TIMEOUT,
            'score': round(compute_agent_score(info), 2),
            'gpu_capable': info.get('gpu_capable', False)
        })
    # tri optionnel par score
    out.sort(key=lambda x: x['score'], reverse=True)
    return jsonify({'agents': out})

# ==============================
# Lancement d'un bureau
# ==============================
@app.route('/launch', methods=['POST'])
@login_required
def launch():
    """
    1. Parse input
    2. Sélectionne liste d'agents candidats
    3. Essaie en push sur chaque agent (POST /execute)
    4. Retourne le premier succès (RDP info)
    5. Si tous échouent → message d'erreur
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        return "Requête invalide (JSON attendu)", 400

    # On utilise le nom d'utilisateur et mot de passe de la session
    username = session.get('username', '')
    password = session.get('password', '')
    
    image = data.get('image', '').strip()
    cpu_limit = int(data.get('cpu_limit', 1))
    memory_limit_gb = int(data.get('memory_limit_gb', 1))
    gpu = bool(data.get('gpu', False))

    if not (username and password and image):
        return "Champs requis manquants", 400
    if image not in AVAILABLE_IMAGES:
        return f"Image non autorisée: {image}", 400
    if cpu_limit < 1 or memory_limit_gb < 1:
        return "Ressources invalides", 400

    memory_limit_mb = memory_limit_gb * 1024

    # Sélectionner candidats
    candidates = list_sorted_candidate_agents(cpu_limit, memory_limit_mb, gpu)
    if not candidates:
        return ("Aucun agent n'a les ressources nécessaires ou est en ligne. "
                "Contacte l'admin."), 503

    payload = {
        "username": username,
        "password": password,
        "image": image,
        "cpu_limit": cpu_limit,
        "memory_limit_mb": memory_limit_mb,
        "gpu": gpu
    }

    errors = []
    for idx, agent in enumerate(candidates, start=1):
        agent_url = agent['url']
        execute_url = f"{agent_url}/execute"
        try:
            resp = requests.post(
                execute_url,
                json=payload,
                timeout=REQUEST_TIMEOUT_SECONDS
            )
        except requests.RequestException as e:
            errors.append(f"[{agent['agent_id']}] Erreur réseau: {e}")
            time.sleep(FALLBACK_RETRY_DELAY)
            continue

        if resp.status_code != 200:
            errors.append(f"[{agent['agent_id']}] Statut HTTP {resp.status_code}: {resp.text[:120]}")
            time.sleep(FALLBACK_RETRY_DELAY)
            continue

        # On suppose du JSON
        try:
            rj = resp.json()
        except Exception:
            errors.append(f"[{agent['agent_id']}] Réponse non-JSON")
            continue

        if rj.get('status') == 'ok':
            rdp_host = rj.get('rdp_host', 'inconnu')
            rdp_port = rj.get('rdp_port', '???')
            container_id = rj.get('container_id', 'n/a')
            # Format retour
            return (
                f"✅ Bureau lancé avec succès sur l'agent {agent['agent_id']}.\n\n"
                f"Connecte-toi avec RDP sur : {rdp_host}:{rdp_port}\n"
                f"USER : {username}\n"
                f"MOT DE PASSE : {password}\n"
                f"Container ID : {container_id}\n"
                f"Image : {image}\n"
                f"CPU : {cpu_limit} | RAM : {memory_limit_gb}GB | GPU : {'oui' if gpu else 'non'}\n"
                f"\n(Chaque lancement est fresh : pas de persistance utilisateur.)"
            )
        else:
            errors.append(f"[{agent['agent_id']}] Erreur applicative: {rj.get('error','inconnue')}")
            time.sleep(FALLBACK_RETRY_DELAY)

    # Tous les agents ont échoué
    return (
        "❌ Impossible de lancer le bureau après tentative sur tous les agents.\n"
        "Détails:\n" + "\n".join(errors) + "\n\nContacte l'admin."
    ), 502

# ==============================
# Thread de maintenance (optionnel)
# ==============================
def maintenance_loop():
    while True:
        prune_dead_agents()
        time.sleep(300)

threading.Thread(target=maintenance_loop, daemon=True).start()

if __name__ == '__main__':
    port = int(os.getenv("SERVER_PORT", "5000"))
    app.run(host='0.0.0.0', port=port, debug=True)