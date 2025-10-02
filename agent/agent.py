import os
import time
import threading
import subprocess
from flask import Flask, request, jsonify
import psutil

from config import (
    AGENT_ID, AGENT_PORT, PUBLIC_HOST,
    RDP_PORT_RANGE_START, RDP_PORT_RANGE_END,
    GPU_ENABLED,
    CLEANUP_INTERVAL_MINUTES, CONTAINER_IDLE_TIMEOUT_MINUTES
)
from utils import (
    detect_gpu_capability,
    pick_free_rdp_port,
    sanitize_image,
    compute_used_cpu,
    get_running_managed_containers_count,
    get_ip_candidate,
    cleanup_inactive_containers
)

app = Flask(__name__)

GPU_CAPABLE = detect_gpu_capability() if GPU_ENABLED else False

# ------------------------------
# Thread de nettoyage des conteneurs (optionnel)
# ------------------------------
def cleanup_loop():
    while True:
        try:
            cleaned = cleanup_inactive_containers(CONTAINER_IDLE_TIMEOUT_MINUTES)
            if cleaned > 0:
                print(f"[CLEANUP] {cleaned} conteneurs inactifs supprimés")
        except Exception as e:
            print(f"[CLEANUP] Erreur nettoyage: {e}")
        time.sleep(CLEANUP_INTERVAL_MINUTES * 60)

# ------------------------------
# Routes
# ------------------------------
@app.route("/ping")
def ping():
    return {"status": "ok", "agent_id": AGENT_ID}

@app.route("/info")
def info():
    """Retourne l'état temps-réel (remplace l'ancien heartbeat)."""
    try:
        total_cpu = psutil.cpu_count()
        used_cpu = compute_used_cpu()
        vm = psutil.virtual_memory()
        total_mem_mb = int(vm.total / 1024 / 1024)
        used_mem_mb = int((vm.total - vm.available) / 1024 / 1024)
        running_containers = get_running_managed_containers_count()
        return jsonify({
            "agent_id": AGENT_ID,
            "url": f"http://{PUBLIC_HOST or get_ip_candidate()}:{AGENT_PORT}",
            "total_cpu": total_cpu,
            "used_cpu": used_cpu,
            "total_mem_mb": total_mem_mb,
            "used_mem_mb": used_mem_mb,
            "running_containers": running_containers,
            "gpu_capable": GPU_CAPABLE,
            "ts": int(time.time())
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/execute", methods=["POST"])
def execute():
    """
    Lance un container RDP.
    Requête JSON :
    {
      "username": "...",
      "password": "...",
      "image": "repo/image:tag",
      "cpu_limit": 2,
      "memory_limit_mb": 4096,
      "gpu": false
    }
    """
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
    if cpu_limit < 1:
        return jsonify({"status": "error", "error": "cpu_limit doit être >=1"}), 400
    if memory_limit_mb < 256:
        return jsonify({"status": "error", "error": "memory_limit_mb trop bas"}), 400
    if want_gpu and not GPU_CAPABLE:
        return jsonify({"status": "error", "error": "GPU demandé mais agent non GPU-capable"}), 400

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
            })

        container_id = proc.stdout.strip().splitlines()[-1].strip()
        host = PUBLIC_HOST or get_ip_candidate()

        return jsonify({
            "status": "ok",
            "rdp_host": host,
            "rdp_port": rdp_port,
            "container_id": container_id
        })

    except subprocess.TimeoutExpired:
        return jsonify({"status": "error", "error": "Timeout lancement conteneur"})
    except Exception as e:
        return jsonify({"status": "error", "error": f"Exception: {e}"}), 500

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
    # Thread nettoyage (optionnel)
    threading.Thread(target=cleanup_loop, daemon=True).start()
    print(f"[AGENT] Démarrage agent {AGENT_ID} sur port {AGENT_PORT} (GPU_CAPABLE={GPU_CAPABLE})")
    app.run(host="0.0.0.0", port=AGENT_PORT)

if __name__ == "__main__":
    main()