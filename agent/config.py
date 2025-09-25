import os
from dotenv import load_dotenv

load_dotenv()

# URL du serveur orchestrateur (ex: http://10.0.0.10:5000)
SERVER_URL = os.getenv("SERVER_URL", "http://127.0.0.1:5000").rstrip("/")

# Identifiant unique de l'agent
AGENT_ID = os.getenv("AGENT_ID", "agent-local")

# Port local où l'agent écoute
AGENT_PORT = int(os.getenv("AGENT_PORT", "5001"))

# IP ou hostname public que le serveur affichera aux utilisateurs (sinon auto-détection)
PUBLIC_HOST = os.getenv("PUBLIC_HOST", "")

# Intervalle de heartbeat (secondes)
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "5"))

# Plage de ports pour RDP (host)
RDP_PORT_RANGE_START = int(os.getenv("RDP_PORT_RANGE_START", "40000"))
RDP_PORT_RANGE_END = int(os.getenv("RDP_PORT_RANGE_END", "45000"))

# Fichier liste des images autorisées
ALLOWED_IMAGES_FILE = os.getenv("ALLOWED_IMAGES_FILE", "allowed_images.txt")

# GPU activé ? (détection automatique si nvidia-smi)
GPU_ENABLED = os.getenv("GPU_ENABLED", "true").lower() in ("1", "true", "yes")

# Forcer docker pull systématique ?
PULL_ALWAYS = os.getenv("PULL_ALWAYS", "false").lower() in ("1", "true", "yes")

# Intervalle de vérification et nettoyage des conteneurs (minutes)
CLEANUP_INTERVAL_MINUTES = int(os.getenv("CLEANUP_INTERVAL_MINUTES", "15"))

# Durée d'inactivité avant suppression d'un conteneur (minutes)
CONTAINER_IDLE_TIMEOUT_MINUTES = int(os.getenv("CONTAINER_IDLE_TIMEOUT_MINUTES", "120"))

# Token d'API pour l'authentification entre serveur et agent
API_TOKEN = os.getenv("API_TOKEN", "")