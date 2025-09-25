# Serveur - MVP Orchestrateur RDP Docker

## Fonctionnement

Ce serveur :
- Expose une page unique `/`
- Reçoit les heartbeats des agents sur `/api/agents/heartbeat`
- Conserve un état en mémoire uniquement
- Sélectionne l’agent "le plus libre" selon CPU/Mémoire
- Push un ordre POST `/execute` vers l’agent
- Fallback si échec (essaie les suivants)
- Retourne les infos RDP à l’utilisateur

## Heartbeat Agent attendu

POST /api/agents/heartbeat
```json
{
  "agent_id": "machine-1",
  "url": "http://10.0.0.5:5001",
  "total_cpu": 8,
  "used_cpu": 2.4,
  "total_mem_mb": 16384,
  "used_mem_mb": 2048,
  "running_containers": 3,
  "gpu_capable": true
}
```

## Ordre envoyé à l'agent

POST {agent.url}/execute
```json
{
  "username": "alice",
  "password": "secret",
  "image": "monorg/rdp-ubuntu:latest",
  "cpu_limit": 2,
  "memory_limit_mb": 4096,
  "gpu": false
}
```

## Réponse attendue agent

```json
{
  "status": "ok",
  "rdp_host": "10.0.0.5",
  "rdp_port": 40123,
  "container_id": "abcedf123"
}
```

Ou

```json
{
  "status": "error",
  "error": "Pull failed"
}
```

## Lancement

```bash
pip install -r requirements.txt
python app.py
```

