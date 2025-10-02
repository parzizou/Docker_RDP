# Serveur – Orchestrateur RDP Docker

Ce composant fournit :
- Une page web unique pour que l'utilisateur se connecte et lance un bureau RDP
- La sélection automatique d’un agent disposant des ressources demandées
- Le fallback sur d’autres agents si le lancement échoue
- L’affichage des informations de connexion RDP (host:port, user, pass, container)
- La lecture DYNAMIQUE des fichiers `agents.txt` et `images.txt` (pas besoin de redémarrer)

## 1. Architecture actuelle

Contrairement à une version précédente documentée, il n’y a PLUS de mécanisme de heartbeat poussé par les agents.

Le serveur fait du polling :
1. Le front appelle périodiquement `GET /api/agents`
2. Le backend relit `agents.txt` à chaque requête
3. Pour chaque agent listé il interroge `GET {agent}/info`
4. Il renvoie un snapshot JSON de l’état (CPU utilisé, mémoire, conteneurs, GPU…)

Avantage : pas d’état long terme, pas de synchronisation complexe.
Inconvénient : légère latence et surcharge si beaucoup d’agents.

## 2. Fichiers de configuration

- `agents.txt`  
  Format (une par ligne) :
  ```
  agent-id http://ip_ou_host:port
  ```
  Commentaires possibles avec `#`.
  Le fichier est relu à CHAQUE appel (ajout/suppression d’un agent = effet immédiat sur /api/agents et sur la sélection lors d’un lancement).

- `images.txt`  
  Liste des images Docker proposées dans le menu déroulant :
  ```
  monorg/rdp-ubuntu:latest
  monorg/rdp-debian:latest
  ```
  Rechargée à chaque affichage de la page principale `/`.  
  (Si tu veux recharger sans recharger la page, ajouter plus tard un endpoint `/api/images`.)

## 3. Endpoints côté serveur

| Méthode | Route              | Description |
|---------|--------------------|-------------|
| GET     | `/login`           | Page de connexion |
| POST    | `/login`           | Authentification simple (users.txt) |
| GET     | `/logout`          | Déconnexion |
| GET     | `/`                | Page principale (lancement + état + changement mdp) |
| GET     | `/api/agents`      | Snapshot dynamique des agents (poll) |
| POST    | `/launch`          | Tente de lancer une session RDP sur un agent |
| POST    | `/change_password` | Changement du mot de passe utilisateur |

## 4. Sélection d’un agent (algorithme)

1. Récupère la liste des agents courants (`agents.txt`)
2. Interroge chacun (`/info`)
3. Filtre ceux :
   - en ligne
   - avec CPU libre suffisant
   - avec RAM libre suffisante
   - compatibles GPU si demandé
4. Trie par CPU libre décroissant (heuristique simple)
5. Envoie un POST `/execute` au premier
6. Si échec → essaie le suivant (avec petit délai)
7. Retourne soit les infos RDP, soit un listing des erreurs si tous ont échoué

## 5. Ordre envoyé à l’agent

POST `{agent.url}/execute` :
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

Réponse succès attendue :
```json
{
  "status": "ok",
  "rdp_host": "10.0.0.21",
  "rdp_port": 40123,
  "container_id": "abcedf123"
}
```

Sinon :
```json
{
  "status": "error",
  "error": "Raison..."
}
```

## 6. Gestion des rôles

`users.txt` stocke : `username:hash:first_login:role`  
Rôles supportés :
- `standard` → limites par défaut (ex: 4 CPU / 4 Go)
- `power` → plus large (ex: 10 CPU / 32 Go)

Les limites sont appliquées au moment du POST `/launch`.

## 7. Authentification (MVP)

- Mots de passe hashés (SHA-256 simple, pas de sel → suffisant seulement en environnement fermé)
- Session Flask (cookie signé)
- Le mot de passe clair est conservé en session pour être transmis à l’agent 
- Pas de TLS intégré (prévoir un reverse proxy si besoin)

## 8. Sécurité (limitations actuelles)

- Pas de contrôle d’accès entre serveur et agents (tout client réseau pourrait tenter un POST direct si non filtré)
- Pas de quotas, pas de durée max de session côté serveur
- Pas de logs structurés
- Pas de mécanisme d’annulation/stop depuis l’UI

Ces points sont à considérer si passage hors MVP.

## 9. Lancement local

```bash
pip install -r requirements.txt
export SECRET_KEY="une_valeur_random"
python app.py
```

Accéder ensuite à http://localhost:5000

Assure-toi que :
- `agents.txt` référence des agents atteignables
- Chaque agent tourne et expose `/info` + `/execute`

## 10. Format `users.txt`

```
# Format: username:password_hash:first_login:role
test:...:false:standard
poweruser:...:false:power
```

Pour créer un hash rapidement en Python :
```python
import hashlib
print(hashlib.sha256("monmotdepasse".encode()).hexdigest())
```

## 11. Prochaines améliorations possibles

- Endpoint `/api/images` + rafraîchissement auto dans l’UI
- Arrêt / liste des sessions lancées
- Meilleur scheduler (prendre en compte la mémoire en priorité pondérée)
- Authentification serveur ↔ agents (token partagé)
- Génération d’un fichier `.rdp` téléchargeable
- Logs persistants + métriques Prometheus

---

MVP prêt : le README reflète désormais le comportement réel (polling), et les listes agents/images peuvent être modifiées sans redémarrage (agents dynamiques déjà effectifs ; images relues à chaque rendu page).