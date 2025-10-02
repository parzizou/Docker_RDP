# Agent RDP Docker – Version Simplifiée

Fonctionnalités :
- Endpoint `/info` pour que le serveur récupère à la demande l'état (CPU, RAM, conteneurs)
- Endpoint `/execute` pour lancer un conteneur RDP (port interne 3389 mappé vers un port host dynamique)
- Pas de heartbeat : le serveur interroge directement les agents quand nécessaire
- Aucune restriction d'images (toutes autorisées)
- Nettoyage basique optionnel (container prune)

## Installation

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # adapter si besoin
python agent.py
```

Variables utiles dans `.env` :

```
AGENT_ID=agent-1
AGENT_PORT=5001
PUBLIC_HOST=10.0.0.21
RDP_PORT_RANGE_START=40000
RDP_PORT_RANGE_END=45000
GPU_ENABLED=true
CLEANUP_INTERVAL_MINUTES=15
CONTAINER_IDLE_TIMEOUT_MINUTES=120
```

## Endpoints

- `GET /ping` → ping simple
- `GET /info` → retourne l'état temps réel
- `POST /execute` → lance un conteneur
- `GET /containers` → debug

## Exemple /execute

```json
{
  "username": "bob",
  "password": "secret",
  "image": "ubuntu:22.04",
  "cpu_limit": 2,
  "memory_limit_mb": 4096,
  "gpu": false
}
```

Réponse succès :

```json
{
  "status": "ok",
  "rdp_host": "10.0.0.21",
  "rdp_port": 40123,
  "container_id": "ab12cd34ef"
}
```

## Image attendue

L'image doit :
- Exposer un service RDP sur le port 3389
- Accepter `RDP_USER` et `RDP_PASSWORD` (sinon adapter le script)

Tu peux construire tes propres images (xrdp, etc.).

## Notes

- Pas d'authentification entre serveur et agent (MVP)
- Protection minimale uniquement via environnement réseau (LAN)
- Pour plus tard : tokens, TLS, quotas, logs structurés…