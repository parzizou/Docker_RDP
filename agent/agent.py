import os
import time
import threading
import socket
import json
import subprocess
from flask import Flask, request, jsonify
import psutil

from config import (
    SERVER_URL, AGENT_ID, AGENT_PORT, PUBLIC_HOST,
    HEARTBEAT_INTERVAL, RDP_PORT_RANGE_START, RDP_PORT_RANGE_END,
    ALLOWED_IMAGES_FILE, GPU_ENABLED, PULL_ALWAYS,
    CLEANUP_INTERVAL_MINUTES, CONTAINER_IDLE_TIMEOUT_MINUTES,
    API_TOKEN
)
from utils import (
    load_allowed_images,
    detect_gpu_capability,
    pick_free_rdp_port,
    sanitize_image,
    compute_used_cpu,
    get_running_managed_containers_count,
    get_ip_candidate,
    cleanup_inactive_containers
)

app = Flask(__name__)

ALLOWED_IMAGES = load_allowed_images(ALLOWED_IMAGES_FILE)
GPU_CAPABLE = detect_gpu_capability() if GPU_ENABLED else False

# ------------------------------
# Heartbeat background thread
# ------------------------------
def heartbeat_loop():
    import requests
    while True:
        try:
            total_cpu = psutil.cpu_count()
            used_cpu = compute_used_cpu()
            vm = psutil.virtual_memory()
            total_mem_mb = int(vm.total / 1024 / 1024)
            used_mem_mb = int((vm.total - vm.available) / 1024 / 1024)
            running_containers = get_running_managed_containers_count()

            payload = {
                "agent_id": AGENT_ID,
                "url": f"http://{PUBLIC_HOST}:{AGENT_PORT}",
                "total_cpu": total_cpu,
                "used_cpu": used_cpu,
                "total_mem_mb": total_mem_mb,
                "used_mem_mb": used_mem_mb,
                "running_containers": running_containers,
                "gpu_capable": GPU_CAPABLE
            }
            
            headers = {}
            if API_TOKEN:
                headers['Authorization'] = f'Bearer {API_TOKEN}'
                
            requests.post(
                f"{SERVER_URL}/api/agents/heartbeat",
                json=payload, headers=headers, timeout=5
            )
        except Exception as e:
            print(f"[HB] Erreur heartbeat: {e}")
        time.sleep(HEARTBEAT_INTERVAL)

# ------------------------------
# Thread de nettoyage des conteneurs
# ------------------------------
def cleanup_loop():
    while True:
        try:
            print(f"[CLEANUP] Vérification des conteneurs inactifs...")
            cleaned = cleanup_inactive_containers(CONTAINER_IDLE_TIMEOUT_MINUTES)
            if cleaned > 0:
                print(f"[CLEANUP] {cleaned} conteneurs inactifs supprimés")
        except Exception as e:
            print(f"[CLEANUP] Erreur nettoyage: {e}")
        
        # Attendre avant la prochaine vérification
        time.sleep(CLEANUP_INTERVAL_MINUTES * 60)

# ------------------------------
# Middleware d'authentification
# ------------------------------
def validate_token():
    if not API_TOKEN:
        return True  # Pas de token configuré = pas d'auth requise
        
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ', 1)[1]
        return token == API_TOKEN
    return False

# ------------------------------
# Routes API
# ------------------------------
@app.route("/ping")
def ping():
    return {"status": "ok", "agent_id": AGENT_ID, "gpu": GPU_CAPABLE}

@app.route("/execute", methods=["POST"])
def execute():
    """
    Reçoit un ordre de lancement. JSON attendu :
    {
      "username": "...",
      "password": "...",
      "image": "repo/image:tag",
      "cpu_limit": 2,
      "memory_limit_mb": 4096,
      "gpu": false
    }
    Retour :
    { "status": "ok", "rdp_host": "...", "rdp_port": 40123, "container_id": "xxx" }
    ou { "status": "error", "error": "message" }
    """
    # Vérification d'authentification
    if API_TOKEN and not validate_token():
        return jsonify({"status": "error", "error": "Non autorisé"}), 401
        
    start_time = time.time()
    data = request.get_json(force=True, silent=True) or {}

    required = ["username", "password", "image", "cpu_limit", "memory_limit_mb", "gpu"]
    missing = [r for r in required if r not in data]
    if missing:
        return jsonify({"status": "error", "error": f"Champs manquants: {missing}"}), 400

    username = data["username"].strip()
    password = data["password"].strip()
    image = sanitize_image(data["image"].strip())
    cpu_limit = int(data["cpu_limit"])
    memory_limit_mb = int(data["memory_limit_mb"])
    want_gpu = bool(data["gpu"])

    if not username or not password:
        return jsonify({"status": "error", "error": "Username ou password vide"}), 400

    if ALLOWED_IMAGES and image not in ALLOWED_IMAGES:
        return jsonify({"status": "error", "error": f"Image non autorisée: {image}"}), 400

    if want_gpu and (not GPU_CAPABLE):
        return jsonify({"status": "error", "error": "GPU demandé mais agent non GPU-capable"}), 400

    if cpu_limit < 1:
        return jsonify({"status": "error", "error": "cpu_limit doit être >=1"}), 400
    if memory_limit_mb < 256:
        return jsonify({"status": "error", "error": "memory_limit_mb trop bas"}), 400

    try:
        rdp_port = pick_free_rdp_port(RDP_PORT_RANGE_START, RDP_PORT_RANGE_END)
        if not rdp_port:
            return jsonify({"status": "error", "error": "Aucun port RDP disponible"}), 503

        container_name = f"rdp_{username}_{int(time.time())}"
        script_path = os.path.join(os.path.dirname(__file__), "docker_launch.sh")

        env = os.environ.copy()
        env["AGENT_ID"] = AGENT_ID

        args = [
            script_path,
            image,
            container_name,
            str(rdp_port),
            str(cpu_limit),
            str(memory_limit_mb),
            "true" if (want_gpu and GPU_CAPABLE) else "false",
            username,
            password
        ]

        print(f"[EXEC] Lancement container: {args}")

        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            env=env,
            timeout=120
        )

        if proc.returncode != 0:
            print(f"[EXEC] Erreur script: {proc.stderr}")
            return jsonify({
                "status": "error",
                "error": f"Echec lancement: {proc.stderr.strip() or proc.stdout.strip()}"
            }), 200

        # Le script imprime l'ID du conteneur en dernière ligne
        container_id = proc.stdout.strip().splitlines()[-1].strip()

        host = PUBLIC_HOST or get_ip_candidate()

        elapsed = round(time.time() - start_time, 2)
        return jsonify({
            "status": "ok",
            "rdp_host": host,
            "rdp_port": rdp_port,
            "container_id": container_id,
            "startup_seconds": elapsed
        })

    except subprocess.TimeoutExpired:
        return jsonify({"status": "error", "error": "Timeout lancement conteneur"}), 200
    except Exception as e:
        return jsonify({"status": "error", "error": f"Exception: {e}"}), 500

# (Optionnel) Debug route pour voir conteneurs gérés
@app.route("/containers")
def list_containers():
    try:
        output = subprocess.check_output(
            ["bash", "-c", "docker ps --format '{{.ID}} {{.Image}} {{.Names}}' --filter 'label=managed_by=rdp_agent'"],
            text=True
        )
        lines = [l for l in output.splitlines() if l.strip()]
        return jsonify({"containers": lines})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def main():
    # Thread heartbeat
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    
    # Thread nettoyage
    threading.Thread(target=cleanup_loop, daemon=True).start()
    
    print(f"[AGENT] Démarrage agent {AGENT_ID} sur port {AGENT_PORT} (GPU_CAPABLE={GPU_CAPABLE})")
    app.run(host="0.0.0.0", port=AGENT_PORT)

if __name__ == "__main__":
    main()