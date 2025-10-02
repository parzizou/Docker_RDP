import os
from dotenv import load_dotenv

load_dotenv()

# Identifiant unique de l'agent
AGENT_ID = os.getenv("AGENT_ID", "agent-local")

# Port local où l'agent écoute
AGENT_PORT = int(os.getenv("AGENT_PORT", "5001"))

# IP/hostname publique (sinon auto-détection)
PUBLIC_HOST = os.getenv("PUBLIC_HOST", "")

# Plage de ports RDP à exposer
RDP_PORT_RANGE_START = int(os.getenv("RDP_PORT_RANGE_START", "40000"))
RDP_PORT_RANGE_END = int(os.getenv("RDP_PORT_RANGE_END", "45000"))

# GPU activé ?
GPU_ENABLED = os.getenv("GPU_ENABLED", "true").lower() in ("1", "true", "yes")

# Intervalle de nettoyage (minutes)
CLEANUP_INTERVAL_MINUTES = int(os.getenv("CLEANUP_INTERVAL_MINUTES", "15"))

# Durée d'inactivité avant suppression (minutes)
CONTAINER_IDLE_TIMEOUT_MINUTES = int(os.getenv("CONTAINER_IDLE_TIMEOUT_MINUTES", "120"))