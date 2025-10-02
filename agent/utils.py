import os
import shutil
import socket
import psutil
import subprocess
import random
import time
import json
from typing import List, Dict, Any

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

def compute_used_cpu():
    # Mesure CPU% global instantané
    # psutil.cpu_percent(interval=0.1) => % usage
    cpu_percent = psutil.cpu_percent(interval=0.1)
    total_cpu = psutil.cpu_count()
    # convertit en "nombre de vCPU utilisés"
    return (cpu_percent / 100.0) * total_cpu

def get_running_managed_containers_count():
    try:
        # Version sans `bash -c`
        output = subprocess.check_output(
            ["docker", "ps", "--filter", "label=managed_by=rdp_agent", "--format", "{{.ID}}"],
            text=True
        ).strip()
        if not output:
            return 0
        return len(output.splitlines())
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

def get_all_managed_containers() -> List[Dict[str, Any]]:
    """
    Récupère les infos sur tous les conteneurs gérés par l'agent.
    """
    try:
        # Version sans `bash -c`
        output = subprocess.check_output(
            [
                "docker", "ps", "-a", 
                "--filter", "label=managed_by=rdp_agent", 
                "--format", '{"id":"{{.ID}}","status":"{{.Status}}","created":"{{.CreatedAt}}","names":"{{.Names}}"}'
            ],
            text=True
        )
        containers = []
        for line in output.strip().split("\n"):
            if line.strip():
                try:
                    containers.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    print(f"Impossible de parser la ligne de conteneur: {line}")
        return containers
    except Exception as e:
        print(f"Erreur lors de la récupération des conteneurs: {e}")
        return []

def cleanup_inactive_containers(idle_minutes: int = 120) -> int:
    """
    Nettoie les conteneurs inactifs (arrêtés ou en marche mais inactifs).
    Retourne le nombre de conteneurs supprimés.
    """
    try:
        # 1. Supprimer les conteneurs arrêtés depuis plus d'1h pour laisser le temps de débugger
        subprocess.run(
            ["docker", "container", "prune", "-f", "--filter", "label=managed_by=rdp_agent", "--filter", "until=1h"],
            check=True, capture_output=True, text=True
        )
        
        # 2. Identifier et supprimer les conteneurs en marche mais inactifs
        containers = get_all_managed_containers()
        cleaned = 0
        
        for container in containers:
            if not container.get("status", "").startswith("Up"):
                continue
                
            container_id = container.get("id")
            if not container_id:
                continue
                
            try:
                # Vérifie la dernière activité RDP via les connexions TCP
                last_activity_minutes = check_container_rdp_activity(container_id)
                
                if last_activity_minutes > idle_minutes:
                    print(f"Conteneur {container_id} inactif (pas de connexion RDP détectée), suppression...")
                    subprocess.run(["docker", "stop", container_id], check=True, capture_output=True, timeout=60)
                    # La suppression se fera au prochain prune si besoin, mais on peut forcer
                    subprocess.run(["docker", "rm", container_id], check=True, capture_output=True, timeout=60)
                    cleaned += 1
            except Exception as e:
                print(f"Erreur lors du nettoyage du conteneur {container_id}: {e}")
                
        return cleaned
    except Exception as e:
        print(f"Erreur lors du nettoyage des conteneurs: {e}")
        return 0

def check_container_rdp_activity(container_id: str) -> float:
    """
    Vérifie l'activité RDP d'un conteneur en cherchant des connexions TCP établies.
    Retourne 0 si une connexion est active, sinon retourne l'âge du conteneur en minutes.
    """
    try:
        # On vérifie les connexions établies sur le port RDP interne (3389)
        # `ss -t -n` liste les sockets TCP. On cherche "ESTAB" et ":3389"
        result = subprocess.run(
            ["docker", "exec", container_id, "ss", "-t", "-n"],
            capture_output=True, text=True, timeout=10
        )
        
        # Si la commande ss n'existe pas, on se rabat sur un comportement sûr (considérer actif)
        if result.returncode != 0:
             print(f"Commande 'ss' non trouvée dans {container_id} ou erreur. Conteneur considéré actif par sécurité.")
             return 0

        if "ESTAB" in result.stdout and ":3389" in result.stdout:
            # Une connexion RDP est probablement active
            return 0
            
        # Pas de connexion active. On considère le conteneur inactif depuis son démarrage.
        # On récupère l'heure de démarrage pour calculer la durée d'inactivité.
        inspect_out = subprocess.check_output(
            ["docker", "inspect", container_id], text=True
        )
        inspect_data = json.loads(inspect_out)
        
        if inspect_data and isinstance(inspect_data, list):
            started_at_str = inspect_data[0].get("State", {}).get("StartedAt", "")
            if started_at_str:
                # Format: 2023-09-25T14:53:58.123456789Z
                start_time = time.mktime(time.strptime(
                    started_at_str.split('.')[0], 
                    "%Y-%m-%dT%H:%M:%S"
                ))
                # On ajoute le décalage du fuseau horaire local
                start_time -= time.timezone
                
                minutes_since_start = (time.time() - start_time) / 60
                return minutes_since_start

    except subprocess.TimeoutExpired:
        print(f"Timeout lors de la vérification d'activité de {container_id}. Conteneur considéré actif.")
        return 0 # Sécurité: on considère actif en cas de timeout
    except Exception as e:
        print(f"Erreur vérification activité conteneur {container_id}: {e}. Conteneur considéré actif par sécurité.")
        return 0 # Sécurité: en cas d'erreur, on suppose qu'il est actif

    # Fallback si on ne peut pas déterminer l'âge
    return float('inf')