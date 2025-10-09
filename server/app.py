import os
import time
import requests
from flask import Flask, request, render_template_string, jsonify, redirect, url_for, session
from dotenv import load_dotenv
from users import verify_user, get_user_role, change_password

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))

AGENTS_FILE = "agents.txt"
IMAGES_FILE = "images.txt"
REQUEST_TIMEOUT_SECONDS = 6
FALLBACK_RETRY_DELAY = 0.8

# Limites par rôle
ROLE_LIMITS = {
    "standard": {"max_cpu": 4, "max_ram_gb": 4},
    "power": {"max_cpu": 10, "max_ram_gb": 32}
}

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

def load_images():
    images = []
    if not os.path.exists(IMAGES_FILE):
        return images
    with open(IMAGES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                images.append(line)
    return images

# ==============================
# Templates (inchangés)
# ==============================
MAIN_PAGE = """<!DOCTYPE html><html lang='fr'>
<head>
<meta charset='utf-8'>
<title><center>Bureaux Virtuels Techlab</center></title>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<style>
/* (styles identiques – coupés ici pour concision si besoin de maintenance future) */
:root { --bg:#0f1115; --card:#1d232c; --accent:#4f7dff; --accent-hover:#3668f6; --danger:#d94141; --ok:#3fbf62; --text:#ecf1f8; --muted:#9aa4b1; --radius:14px; --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; --grad:linear-gradient(135deg,#2641ff,#4f7dff 60%,#7aa8ff); }
*{box-sizing:border-box;} body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:radial-gradient(circle at 20% 20%, #18202a, #0f1115);color:var(--text);line-height:1.45;-webkit-font-smoothing:antialiased;padding:30px 18px 60px;}
h1{margin:0 0 30px;font-size:clamp(1.9rem,2.8vw,2.6rem);background:var(--grad);-webkit-background-clip:text;color:transparent;letter-spacing:.5px;}
a{color:var(--accent);text-decoration:none;} a:hover{text-decoration:underline;}
.grid{display:grid;gap:28px;max-width:1250px;margin:0 auto;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));}
.card{background:var(--card);border:1px solid #263140;border-radius:var(--radius);padding:22px 22px 26px;position:relative;box-shadow:0 4px 18px -4px rgba(0,0,0,.55), 0 0 0 1px rgba(255,255,255,.02) inset;backdrop-filter:blur(6px);}
.card h3{margin:0 0 14px;font-size:18px;font-weight:600;letter-spacing:.5px;}
label{font-size:13px;text-transform:uppercase;letter-spacing:1px;color:var(--muted);display:block;margin-top:14px;margin-bottom:4px;font-weight:600;}
input,select{width:100%;background:#14181f;border:1px solid #2b333f;color:var(--text);padding:10px 12px;border-radius:8px;font-size:14px;font-family:inherit;transition:.18s border, .18s background;}
input:focus,select:focus{outline:none;border-color:var(--accent);background:#101318;}
button{background:var(--grad);border:none;color:#fff;font-weight:600;letter-spacing:.4px;padding:13px 20px;font-size:15px;border-radius:10px;margin-top:22px;cursor:pointer;box-shadow:0 4px 14px -2px rgba(0,0,0,.55);transition:.22s transform, .22s box-shadow, .22s filter;}
button:hover{filter:brightness(1.08);transform:translateY(-2px);box-shadow:0 10px 26px -6px rgba(0,0,0,.65);}
button:active{transform:translateY(0);filter:brightness(.95);}
.smallrow{display:flex;gap:14px;flex-wrap:wrap;}
.smallrow > div{flex:1 1 120px;min-width:120px;}
pre{background:#06090d;border:1px solid #222d3a;padding:16px 18px;border-radius:10px;font-size:13px;font-family:var(--mono);color:#8af08a;min-height:120px;overflow:auto;line-height:1.4;}
table{width:100%;border-collapse:collapse;font-size:13.5px;font-family:var(--mono);}
th,td{border-bottom:1px solid #22303d;padding:6px 6px;text-align:left;vertical-align:middle;}
th{font-weight:600;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:1px;}
.bad{color:var(--danger);} .ok{color:var(--ok);}
.userbar{position:fixed;top:12px;right:14px;font-size:13px;background:#151b22;border:1px solid #263140;padding:10px 14px;border-radius:10px;display:flex;align-items:center;gap:12px;box-shadow:0 4px 16px -6px rgba(0,0,0,.6);}
.tag{background:#213044;padding:2px 8px 3px;border-radius:20px;font-size:11px;letter-spacing:.5px;font-weight:600;text-transform:uppercase;color:#8fb3d5;}
.logout{background:#212c39;border:1px solid #2f3d4d;color:#d5dde6;padding:6px 12px;font-size:12px;font-weight:500;border-radius:8px;text-decoration:none;transition:.2s background;}
.logout:hover{background:#2e3c4d;}
.note{font-size:12px;color:var(--muted);margin-top:6px;}
.form-inline-msg{margin-top:8px;font-size:12px;color:var(--muted);font-style:italic;}
.success{color:var(--ok);} .error{color:var(--danger);}
.password-box pre {min-height:auto;}
footer{margin-top:60px;text-align:center;font-size:12px;color:#566374;}
</style>
</head>
<body>
<div class='userbar'>
  <span><b>{{username}}</b></span>
  <span class="tag">{{ role }}</span>
  <a class='logout' href='/logout'>Déconnexion</a>
</div>

<h1><center>Bureaux Virtuels Techlab</center></h1>

<div class="grid">
  <div class='card'>
    <h3>Lancer un bureau</h3>
    <form id='launchForm'>
      <label>Image Docker</label>
      <select name='image'>
        {% for img in images %}
          <option value='{{img}}'>{{img}}</option>
        {% endfor %}
      </select>
      <div class='smallrow'>
        <div>
          <label>CPU (max {{ limits.max_cpu }})</label>
          <input type='number' name='cpu_limit' value='2' min='1' max='{{ limits.max_cpu }}'>
        </div>
        <div>
          <label>RAM (Go) (max {{ limits.max_ram_gb }})</label>
            <input type='number' name='memory_limit_gb' value='4' min='1' max='{{ limits.max_ram_gb }}'>
        </div>
        <div>
          <label>GPU</label>
          <select name='gpu'>
            <option value='0'>Non</option>
            <option value='1'>Oui</option>
          </select>
        </div>
      </div>
      <div class='form-inline-msg'>Respecte les limites de ton rôle ({{ role }})</div>
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

  <div class='card password-box'>
    <h3>Changer mon mot de passe</h3>
    <form id='pwdForm'>
      <label>Ancien mot de passe</label>
      <input type='password' name='old_password' required>
      <label>Nouveau mot de passe</label>
      <input type='password' name='new_password' required minlength="3">
      <button>Mettre à jour</button>
    </form>
    <pre id='pwdOutput'>...</pre>
  </div>
</div>

<footer>
  Techlab Mines Nancy
</footer>

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
    let html = "<table><tr><th>ID</th><th>CPU (used/total)</th><th>RAM (used/total MB)</th><th>Cont.</th><th>GPU</th><th>OK?</th></tr>";
    data.agents.forEach(a=>{
      html += `<tr>
        <td>${a.agent_id}</td>
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
setInterval(fetchAgents, 6000);
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

document.getElementById('pwdForm').addEventListener('submit', async (e)=>{
  e.preventDefault();
  const po = document.getElementById('pwdOutput');
  po.textContent = "Mise à jour...";
  const fd = new FormData(e.target);
  try{
    const r = await fetch('/change_password', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        old_password: fd.get('old_password'),
        new_password: fd.get('new_password')
      })
    });
    const js = await r.json();
    if(js.status === 'ok'){
      po.textContent = "Mot de passe changé ✅";
      e.target.reset();
    }else{
      po.textContent = "Erreur: "+js.error;
    }
  }catch(err){
    po.textContent = "Erreur réseau: "+err;
  }
});
</script>
</body></html>
"""

LOGIN_PAGE = """<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'><title>Login – Techlab</title>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<style>
/* styles login (inchangés) */
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:radial-gradient(circle at 25% 20%, #18202a, #0f1115);margin:0;color:#ecf1f8;}
.wrap{max-width:380px;margin:90px auto;background:#1d232c;padding:34px 34px 42px;border-radius:18px;border:1px solid #263140;box-shadow:0 6px 30px -8px rgba(0,0,0,.65),0 0 0 1px rgba(255,255,255,.03) inset;}
h2{margin:0 0 10px;font-weight:600;font-size:26px;letter-spacing:.5px;background:linear-gradient(120deg,#668dff,#b4cfff);-webkit-background-clip:text;color:transparent;}
p.sub{margin:0 0 22px;font-size:13px;color:#98a6b8;letter-spacing:.3px;}
label{font-size:12px;text-transform:uppercase;letter-spacing:1px;color:#8da3bb;font-weight:600;margin-top:14px;display:block;}
input{width:100%;margin-top:6px;background:#14181f;border:1px solid #2d3845;color:#fff;padding:12px 14px;font-size:14px;border-radius:10px;transition:.2s border, .2s background;}
input:focus{outline:none;background:#101318;border-color:#4f7dff;}
button{width:100%;margin-top:26px;background:linear-gradient(135deg,#2641ff,#4f7dff 60%,#7aa8ff);color:#fff;font-weight:600;letter-spacing:.5px;padding:14px 16px;border:none;border-radius:12px;font-size:15px;cursor:pointer;box-shadow:0 6px 22px -6px rgba(0,0,0,.6);transition:.22s transform, .22s box-shadow;}
button:hover{transform:translateY(-2px);box-shadow:0 14px 32px -10px rgba(0,0,0,.7);}
.err{margin-top:18px;background:#331c1c;border:1px solid #5d2c2c;padding:10px 14px;border-radius:10px;font-size:13px;color:#ff9e9e;}
footer{text-align:center;margin-top:40px;font-size:11px;color:#5f6e7d;letter-spacing:.5px;}
</style></head><body>
<div class='wrap'>
  <h2>Techlab</h2>
  <p class='sub'>Connexion aux bureaux virtuels</p>
  <form method='post'>
    <label>Utilisateur</label>
    <input name='username' autofocus required>
    <label>Mot de passe</label>
    <input type='password' name='password' required>
    <button>Entrer</button>
    {% if error %}<div class='err'>{{error}}</div>{% endif %}
  </form>
</div>
<footer>Techlab Mines Nancy</footer>
</body></html>
"""

# ==============================
# Auth
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
                session['role'] = get_user_role(u)
                return redirect(url_for('index'))
            else:
                error = "Identifiants invalides."
    return render_template_string(LOGIN_PAGE, error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==============================
# Agents (dynamic reload)
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
    # Reload agents file at every request for dynamic update
    agents = load_agents()
    return [fetch_agent_info(a) for a in agents]

# ==============================
# Pages
# ==============================
@app.route('/')
@login_required
def index():
    role = session.get('role', 'standard')
    limits = ROLE_LIMITS.get(role, ROLE_LIMITS['standard'])
    images = load_images()  # Rechargées à chaque affichage
    return render_template_string(
        MAIN_PAGE,
        username=session.get('username',''),
        role=role,
        limits=limits,
        images=images
    )

@app.route('/api/agents')
@login_required
def api_agents():
    return jsonify({"agents": list_agents_live()})

# ==============================
# Lancement
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
    role = session.get('role','standard')
    limits = ROLE_LIMITS.get(role, ROLE_LIMITS['standard'])

    image = data.get('image','').strip()
    cpu_limit = int(data.get('cpu_limit',1))
    memory_limit_gb = int(data.get('memory_limit_gb',1))
    gpu = bool(data.get('gpu', False))

    if not (username and password and image):
        return "Champs requis manquants", 400
    if cpu_limit < 1 or memory_limit_gb < 1:
        return "Ressources invalides", 400

    if cpu_limit > limits['max_cpu'] or memory_limit_gb > limits['max_ram_gb']:
        return f"Dépasse les limites de ton rôle ({role}) : max {limits['max_cpu']} CPU / {limits['max_ram_gb']} Go", 403

    memory_limit_mb = memory_limit_gb * 1024

    agents_info = list_agents_live()
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

# ==============================
# Changement de mot de passe
# ==============================
@app.route('/change_password', methods=['POST'])
@login_required
def change_pwd():
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({"status":"error","error":"JSON invalide"}), 400
    old_password = data.get("old_password","").strip()
    new_password = data.get("new_password","").strip()
    if not (old_password and new_password):
        return jsonify({"status":"error","error":"Champs manquants"}), 400
    if len(new_password) < 3:
        return jsonify({"status":"error","error":"Mot de passe trop court"}), 400
    user = session.get('username')
    ok = change_password(user, old_password, new_password)
    if not ok:
        return jsonify({"status":"error","error":"Ancien mot de passe incorrect"}), 403
    session['password'] = new_password
    return jsonify({"status":"ok"})

if __name__ == '__main__':
    port = int(os.getenv("SERVER_PORT", "5000"))
    app.run(host='0.0.0.0', port=port, debug=True)