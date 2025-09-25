import os
import shutil
import socket
import psutil
import subprocess
import random

def load_allowed_images(path: str):
    if not os.path.exists(path):
        return []
    images = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                images.append(line)
    return images

def detect_gpu_capability():
    # Simple: présence de nvidia-smi => GPU utilisable
    return shutil.which("nvidia-smi") is not None

def pick_free_rdp_port(start: int, end: int, attempts: int = 50):
    """
    Cherche un port libre dans la plage.
    On prend une approche random pour répartir.
    """
    tried = set()
    for _ in range(attempts):
        port = random.randint(start, end)
        if port in tried:
            continue
        tried.add(port)
        if is_port_free(port):
            return port
    # fallback scan linéaire
    for port in range(start, end + 1):
        if is_port_free(port):
            return port
    return None

def is_port_free(port: int):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) != 0

def sanitize_image(image: str):
    # Supprime espaces & caractères douteux basiques
    return image.replace(";", "").replace("&", "").strip()

def compute_used_cpu():
    # Mesure CPU% global instantané
    # psutil.cpu_percent(interval=0.1) => % usage
    cpu_percent = psutil.cpu_percent(interval=0.1)
    total_cpu = psutil.cpu_count()
    # convertit en "nombre de vCPU utilisés"
    return (cpu_percent / 100.0) * total_cpu

def get_running_managed_containers_count():
    try:
        out = subprocess.check_output(
            ["bash", "-c", "docker ps --filter 'label=managed_by=rdp_agent' --format '{{.ID}}' | wc -l"],
            text=True
        ).strip()
        return int(out) if out.isdigit() else 0
    except Exception:
        return 0

def get_ip_candidate():
    """
    Détection d'une IP locale "raisonnable".
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"
