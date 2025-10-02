import os
import time
import requests
from flask import Flask, request, render_template_string, jsonify, redirect, url_for, session
from dotenv import load_dotenv
from users import verify_user

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))

AGENTS_FILE = "agents.txt"
REQUEST_TIMEOUT_SECONDS = 6
FALLBACK_RETRY_DELAY = 0.8

# ==============================
# Chargement des agents (statiques)
# ==============================
def load_agents():
    agents = []
    if not os.path.exists(AGENTS_FILE):
        return agents
    with open(AGENTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                agents.append({"agent_id": parts[0], "url": parts[1].rstrip("/")})
    return agents

STATIC_AGENTS = load_agents()

# ==============================
# Templates simplifiés
# ==============================
LOGIN_PAGE = """
<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'><title>Login</title>
<style>
body{font-family:system-ui;background:#f5f6fa;padding:40px;}
.card{background:#fff;max-width:400px;margin:40px auto;padding:25px;border-radius:10px;box-shadow:0 4px 10px rgba(0,0,0,.06);}
input{width:100%;padding:10px;margin-top:10px;border:1px solid #ccc;border-radius:6px;}
button{margin-top:15px;width:100%;padding:12px;background:#4361ee;color:#fff;border:none;border-radius:6px;font-size:16px;cursor:pointer;}
.err{color:#c62828;margin-top:10px;}
</style></head><body>
<div class='card'>
<h2>Connexion</h2>
<form method='post'>
<input name='username' placeholder='Utilisateur' autofocus required>
<input type='password' name='password' placeholder='Mot de passe' required>
<button>Entrer</button>
{% if error %}<div class='err'>{{error}}</div>{% endif %}
</form>
</div>
</body></html>
"""

MAIN_PAGE = """
<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'><title>Bureaux</title>
<style>
body{font-family:system-ui;background:#f5f6fa;margin:0;padding:25px;color:#222;}
h1{margin-top:0;}
.card{background:#fff;padding:20px;border-radius:10px;box-shadow:0 4px 10px rgba(0,0,0,.06);max-width:980px;margin:0 auto 25px;}
input,select{width:100%;padding:10px;border:1px solid #ccc;border-radius:6px;margin-top:6px;}
button{background:#4361ee;color:#fff;border:none;padding:12px 18px;border-radius:6px;font-size:15px;cursor:pointer;margin-top:15px;}
button:hover{background:#364dcc;}
pre{background:#111;color:#0f0;padding:15px;border-radius:8px;overflow:auto;font-size:14px;}
.smallrow{display:flex;gap:16px;flex-wrap:wrap;}
.smallrow > div{flex:1 1 180px;}
table{width:100%;border-collapse:collapse;font-size:14px;}
th,td{padding:6px 4px;text-align:left;border-bottom:1px solid #eee;}
.bad{color:#c62828;}
.ok{color:#2e7d32;}
.userbar{text-align:right;margin-bottom:15px;}
.logout{color:#333;text-decoration:none;font-size:14px;border:1px solid #ccc;padding:4px 10px;border-radius:6px;}
.logout:hover{background:#eee;}
</style>
</head><body>
<div class='userbar'>
Connecté: <b>{{username}}</b> | <a class='logout' href='/logout'>Déconnexion</a>
</div>
<h1>Bureaux Virtuels (MVP)</h1>

<div class='card'>
  <h3>Lancer un bureau</h3>
  <form id='launchForm'>
    <label>Image Docker (ex: ubuntu:22.04)</label>
    <input name='image' value='ubuntu:22.04'>
    <div class='smallrow'>
      <div>
        <label>CPU</label>
        <input type='number' name='cpu_limit' value='2' min='1'>
      </div>
      <div>
        <label>RAM (GB)</label>
        <input type='number' name='memory_limit_gb' value='4' min='1'>
      </div>
      <div>
        <label>GPU ?</label>
        <select name='gpu'>
          <option value='0'>Non</option>
          <option value='1'>Oui</option>
        </select>
      </div>
    </div>
    <button>Lancer</button>
  </form>
</div>

<div class='card'>
  <h3>Résultat</h3>
  <pre id='output'>En attente...</pre>
</div>

<div class='card'>
  <h3>Agents</h3>
  <div id='agentsBox'>Chargement...</div>
</div>

<script>
async function fetchAgents(){
  try{
    const r = await fetch('/api/agents');
    const data = await r.json();
    const box = document.getElementById('agentsBox');
    if(!data.agents.length){
      box.innerHTML = "<i>Aucun agent</i>";
      return;
    }
    let html = "<table><tr><th>ID</th><th>URL</th><th>CPU (used/total)</th><th>RAM (used/total MB)</th><th>Conteneurs</th><th>GPU</th><th>OK?</th></tr>";
    data.agents.forEach(a=>{
      html += `<tr>
        <td>${a.agent_id}</td>
        <td>${a.url}</td>
        <td>${a.used_cpu.toFixed(1)}/${a.total_cpu}</td>
        <td>${a.used_mem_mb}/${a.total_mem_mb}</td>
        <td>${a.running_containers}</td>
        <td>${a.gpu_capable ? 'oui':'non'}</td>
        <td>${a.online ? '✅':'❌'}</td>
      </tr>`;
    });
    html += "</table>";
    box.innerHTML = html;
  }catch(e){
    console.error(e);
  }
}
setInterval(fetchAgents, 5000);
fetchAgents();

document.getElementById('launchForm').addEventListener('submit', async (e)=>{
  e.preventDefault();
  const out = document.getElementById('output');
  out.textContent = "Sélection d'un agent...";
  const fd = new FormData(e.target);
  const payload = {
    image: fd.get('image'),
    cpu_limit: parseInt(fd.get('cpu_limit'),10),
    memory_limit_gb: parseInt(fd.get('memory_limit_gb'),10),
    gpu: fd.get('gpu') === '1'
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
    out.textContent = "Erreur réseau: "+err;
  }
});
</script>
</body></html>
"""

# ==============================
# Auth simple
# ==============================
def login_required(view_func):
    def wrapped(*a, **kw):
        if 'username' not in session:
            return redirect(url_for('login'))
        return view_func(*a, **kw)
    wrapped.__name__ = view_func.__name__
    return wrapped

@app.route('/login', methods=['GET','POST'])
def login():
    error = None
    if request.method == 'POST':
        u = request.form.get('username','').strip()
        p = request.form.get('password','').strip()
        if not (u and p):
            error = "Champs requis."
        else:
            ok, _ = verify_user(u, p)
            if ok:
                session['username'] = u
                session['password'] = p
                return redirect(url_for('index'))
            else:
                error = "Identifiants invalides."
    return render_template_string(LOGIN_PAGE, error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==============================
# Récupération dynamique des infos agents
# ==============================
def fetch_agent_info(agent):
    url = f"{agent['url']}/info"
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        if r.status_code != 200:
            return {**agent, "online": False}
        data = r.json()
        return {
            "agent_id": agent["agent_id"],
            "url": agent["url"],
            "total_cpu": data.get("total_cpu", 0),
            "used_cpu": data.get("used_cpu", 0),
            "total_mem_mb": data.get("total_mem_mb", 0),
            "used_mem_mb": data.get("used_mem_mb", 0),
            "running_containers": data.get("running_containers", 0),
            "gpu_capable": data.get("gpu_capable", False),
            "online": True
        }
    except Exception:
        return {
            "agent_id": agent["agent_id"],
            "url": agent["url"],
            "total_cpu": 0,
            "used_cpu": 0,
            "total_mem_mb": 0,
            "used_mem_mb": 0,
            "running_containers": 0,
            "gpu_capable": False,
            "online": False
        }

def list_agents_live():
    out = []
    for a in STATIC_AGENTS:
        out.append(fetch_agent_info(a))
    return out

# ==============================
# Page principale
# ==============================
@app.route('/')
@login_required
def index():
    return render_template_string(MAIN_PAGE, username=session.get('username',''))

@app.route('/api/agents')
@login_required
def api_agents():
    return jsonify({"agents": list_agents_live()})

# ==============================
# Lancement d'une session
# ==============================
@app.route('/launch', methods=['POST'])
@login_required
def launch():
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        return "JSON invalide", 400

    username = session.get('username','')
    password = session.get('password','')
    image = data.get('image','').strip()
    cpu_limit = int(data.get('cpu_limit',1))
    memory_limit_gb = int(data.get('memory_limit_gb',1))
    gpu = bool(data.get('gpu', False))

    if not (username and password and image):
        return "Champs requis manquants", 400
    if cpu_limit < 1 or memory_limit_gb < 1:
        return "Ressources invalides", 400

    memory_limit_mb = memory_limit_gb * 1024

    # Récupérer état live des agents
    agents_info = list_agents_live()
    # Filtrer agents en ligne avec ressources approximatives
    candidates = []
    for a in agents_info:
        if not a['online']:
            continue
        free_cpu = a['total_cpu'] - a['used_cpu']
        free_mem = a['total_mem_mb'] - a['used_mem_mb']
        if free_cpu >= cpu_limit and free_mem >= memory_limit_mb:
            if gpu and not a['gpu_capable']:
                continue
            candidates.append(a)

    if not candidates:
        return "Aucun agent n'a les ressources ou est en ligne.", 503

    # Stratégie simple: prendre celui avec le plus de CPU libre
    candidates.sort(key=lambda x: (x['total_cpu'] - x['used_cpu']), reverse=True)

    payload = {
        "username": username,
        "password": password,
        "image": image,
        "cpu_limit": cpu_limit,
        "memory_limit_mb": memory_limit_mb,
        "gpu": gpu
    }

    errors = []
    for agent in candidates:
        execute_url = f"{agent['url']}/execute"
        try:
            resp = requests.post(execute_url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as e:
            errors.append(f"[{agent['agent_id']}] réseau: {e}")
            time.sleep(FALLBACK_RETRY_DELAY)
            continue

        if resp.status_code != 200:
            errors.append(f"[{agent['agent_id']}] HTTP {resp.status_code}")
            time.sleep(FALLBACK_RETRY_DELAY)
            continue

        try:
            rj = resp.json()
        except Exception:
            errors.append(f"[{agent['agent_id']}] réponse non JSON")
            continue

        if rj.get("status") == "ok":
            return (
                f"✅ Session lancée sur agent {agent['agent_id']}\n\n"
                f"Connexion RDP : {rj.get('rdp_host')}:{rj.get('rdp_port')}\n"
                f"USER : {username}\n"
                f"PASS : {password}\n"
                f"Container : {rj.get('container_id')}\n"
                f"Image : {image}\n"
                f"CPU : {cpu_limit} | RAM : {memory_limit_gb}GB | GPU : {'oui' if gpu else 'non'}"
            )
        else:
            errors.append(f"[{agent['agent_id']}] erreur: {rj.get('error','?')}")
            time.sleep(FALLBACK_RETRY_DELAY)

    return "Échec sur tous les agents:\n" + "\n".join(errors), 502

if __name__ == '__main__':
    port = int(os.getenv("SERVER_PORT", "5000"))
    app.run(host='0.0.0.0', port=port, debug=True)