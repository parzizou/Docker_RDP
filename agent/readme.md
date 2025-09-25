# Agent RDP Docker – MVP

Cet agent :
- Envoie des heartbeats au serveur orchestrateur
- Écoute `/execute` pour lancer un conteneur
- Lance un conteneur Docker (bureau distant) via `docker_launch.sh`
- Assigne un port RDP libre dans une plage définie
- Retourne au serveur les infos (host, port, container_id)
- Marque les conteneurs avec labels `managed_by=rdp_agent`

## 1. Dépendances

- Linux
- Docker installé et démarré
- Python 3.10+
- (Optionnel GPU) pilotes + nvidia-container-toolkit

## 2. Installation rapide

```bash
git clone <repo_privé_ou_copie> agent-node
cd agent-node/agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Édite `.env` selon ta machine.

## 3. Variables (.env)

```
SERVER_URL=http://10.0.0.5:5000
AGENT_ID=agent-lab-1
AGENT_PORT=5001
PUBLIC_HOST=10.0.0.21
HEARTBEAT_INTERVAL=5
RDP_PORT_RANGE_START=40000
RDP_PORT_RANGE_END=45000
ALLOWED_IMAGES_FILE=allowed_images.txt
GPU_ENABLED=true
PULL_ALWAYS=false
```

- `PUBLIC_HOST` = IP/hostname que les utilisateurs doivent utiliser pour se connecter en RDP.
- Si vide : auto-détection (best-effort).

## 4. Lancement

```bash
chmod +x docker_launch.sh
python agent.py
```

Test ping :
```bash
curl http://localhost:5001/ping
```

## 5. Heartbeat

Envoi périodique à :
```
POST {SERVER_URL}/api/agents/heartbeat
```

Contient CPU/MEM/RUNNING containers etc.

## 6. Exécution d'un ordre

Reçu via `/execute` :
```json
{
  "username":"alice",
  "password":"secret",
  "image":"monorg/rdp-ubuntu:latest",
  "cpu_limit":2,
  "memory_limit_mb":4096,
  "gpu":false
}
```

Réponse succès :
```json
{
  "status":"ok",
  "rdp_host":"10.0.0.21",
  "rdp_port":40123,
  "container_id":"ab12cd34ef"
}
```

## 7. Nom des conteneurs

Format : `rdp_<username>_<timestamp>`  
Labels :
- `managed_by=rdp_agent`
- `agent_id=<AGENT_ID>`

## 8. GPU

Si `GPU_ENABLED=true` et `nvidia-smi` disponible : ajout `--gpus 1`  
(Améliorable plus tard : sélection multi-GPU, MIG, etc.)

## 9. Sécurité basique

- Liste blanche d'images (fichier `allowed_images.txt`)
- Filtrage grossier du nom d'image
- Pas de privilèges docker spéciaux (ajouter si nécessaire)
- Tu peux ajouter plus tard : signature des ordres, token partagé, TLS.

## 10. systemd (optionnel)

Fichier : `systemd/rdp-agent.service`
Activer :
```bash
sudo cp systemd/rdp-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rdp-agent
journalctl -u rdp-agent -f
```

## 11. Nettoyage manuel

```bash
docker ps --filter "label=managed_by=rdp_agent"
docker stop <id> && docker rm <id>
```

## 12. Améliorations possibles

- Persistence sessions (volumes)
- Journalisation structurée JSON
- Stratégie de retry interne
- Gestion des quotas par utilisateur
- Limite sur nb conteneurs simultanés
- File d’attente si ressources saturées
