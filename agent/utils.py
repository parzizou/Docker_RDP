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

def get_all_managed_containers() -> List[Dict[str, Any]]:
    """
    Récupère les infos sur tous les conteneurs gérés par l'agent.
    """
    try:
        output = subprocess.check_output(
            ["bash", "-c", """
            docker ps -a --filter "label=managed_by=rdp_agent" --format '{"id":"{{.ID}}","status":"{{.Status}}","created":"{{.CreatedAt}}","names":"{{.Names}}"}'
            """],
            text=True
        )
        # Convertir chaque ligne en objet JSON
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
        # 1. Supprimer les conteneurs arrêtés
        subprocess.run(
            ["docker", "container", "prune", "-f", "--filter", "label=managed_by=rdp_agent"],
            check=True, capture_output=True, text=True
        )
        
        # 2. Identifier et supprimer les conteneurs en marche mais inactifs
        containers = get_all_managed_containers()
        now = time.time()
        cleaned = 0
        
        for container in containers:
            # Si le conteneur n'est pas en cours d'exécution (statut ne commence pas par "Up"), on passe
            if not container.get("status", "").startswith("Up"):
                continue
                
            container_id = container.get("id")
            if not container_id:
                continue
                
            # Vérifier l'activité RDP via les logs
            try:
                # Vérifie la dernière activité RDP dans les logs
                last_activity = check_container_rdp_activity(container_id, idle_minutes)
                
                if last_activity > idle_minutes:
                    print(f"Conteneur {container_id} inactif depuis {last_activity} minutes, suppression...")
                    # Arrêt puis suppression
                    subprocess.run(["docker", "stop", container_id], check=True, capture_output=True)
                    subprocess.run(["docker", "rm", container_id], check=True, capture_output=True)
                    cleaned += 1
            except Exception as e:
                print(f"Erreur lors du nettoyage du conteneur {container_id}: {e}")
                
        return cleaned
    except Exception as e:
        print(f"Erreur lors du nettoyage des conteneurs: {e}")
        return 0

def check_container_rdp_activity(container_id: str, idle_minutes: int) -> float:
    """
    Vérifie la dernière activité RDP d'un conteneur.
    Retourne le nombre de minutes depuis la dernière activité.
    """
    # Obtenir le timestamp de dernière activité dans les logs
    since = f"{idle_minutes*2}m"  # Cherche sur 2x le temps max d'inactivité
    
    try:
        # Rechercher des indices d'activité RDP dans les logs récents
        logs = subprocess.check_output(
            ["docker", "logs", "--since", since, container_id],
            stderr=subprocess.STDOUT, text=True
        )
        
        if not logs.strip():
            # Aucun log récent = probablement inactif
            # On calcule l'âge du conteneur
            inspect = json.loads(subprocess.check_output(
                ["docker", "inspect", container_id],
                text=True
            ))
            
            if inspect and isinstance(inspect, list):
                started_at = inspect[0].get("State", {}).get("StartedAt", "")
                if started_at:
                    # Format ISO 8601: 2023-09-25T14:53:58.123456789Z
                    start_time = time.mktime(time.strptime(
                        started_at.split('.')[0], 
                        "%Y-%m-%dT%H:%M:%S"
                    ))
                    minutes_since_start = (time.time() - start_time) / 60
                    return minutes_since_start
        
        # Si on a des logs, on suppose une activité récente
        return 0
    except Exception as e:
        # En cas d'erreur, on suppose que le conteneur est actif
        print(f"Erreur vérification activité conteneur {container_id}: {e}")
        return 0