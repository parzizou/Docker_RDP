import os
import time
import threading
import requests
from flask import Flask, request, render_template_string, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ==============================
# Config minimale
# ==============================
AGENT_HEARTBEAT_TIMEOUT = 40          # secondes avant de considérer un agent offline
AGENT_SELECTION_CPU_WEIGHT = 1.0
AGENT_SELECTION_MEM_WEIGHT = 0.7
REQUEST_TIMEOUT_SECONDS = 12          # timeout d'appel HTTP vers l'agent
FALLBACK_RETRY_DELAY = 1.0            # pause entre essais d’agents
IMAGES_FILE = "images.txt"

# ==============================
# Stockage en mémoire
# ==============================
agents = {}  # agent_id -> dict(info)
# Exemple d’entrée :
# {
#   'agent_id': 'machine-1',
#   'url': 'http://10.0.0.5:5001',
#   'last_seen': 1234567890.0,
#   'total_cpu': 8,
#   'used_cpu': 2.5,
#   'total_mem_mb': 16384,
#   'used_mem_mb': 2048,
#   'running_containers': 3,
# }

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
# Template HTML (simplifiée)
# ==============================
HTML_PAGE = '''
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
    </style>
</head>
<body>
    <h1>Bureaux Virtuels Distribués</h1>
    <div class="card">
        <form id="launchForm">
            <label>Nom d'utilisateur :</label>
            <input type="text" name="username" required placeholder="ton login">
            <label>Mot de passe :</label>
            <input type="password" name="password" required placeholder="ton mot de passe (sera transmis à l'agent)">
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
        username: formData.get('username'),
        password: formData.get('password'),
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
    (On fait simple : on suppose que l’agent sait gérer la contrainte GPU si besoin via un flag 'gpu_capable')
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
# Routes page
# ==============================
@app.route('/')
def index():
    return render_template_string(HTML_PAGE, images=AVAILABLE_IMAGES)

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
def launch():
    """
    1. Parse input
    2. Sélectionne liste d’agents candidats
    3. Essaie en push sur chaque agent (POST /execute)
    4. Retourne le premier succès (RDP info)
    5. Si tous échouent → message d’erreur
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        return "Requête invalide (JSON attendu)", 400

    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
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
