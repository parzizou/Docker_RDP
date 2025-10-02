import os
import hashlib
from typing import Dict, Tuple, Optional

# Chemin du fichier utilisateurs
USER_FILE = "users.txt"

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def load_users() -> Dict[str, Dict]:
    """
    Charge les utilisateurs.
    Formats acceptés :
      username:hash
      username:hash:first_login
      username:hash:first_login:role
    first_login -> true/false (false par défaut)
    role -> standard/power (standard par défaut)
    """
    if not os.path.exists(USER_FILE):
        return {}

    users = {}
    try:
        with open(USER_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(":")
                if len(parts) < 2:
                    continue
                username = parts[0]
                password_hash = parts[1]
                first_login = False
                role = "standard"

                if len(parts) >= 3 and parts[2]:
                    first_login = parts[2].lower() == "true"
                if len(parts) >= 4 and parts[3]:
                    role_candidate = parts[3].strip().lower()
                    if role_candidate in ("power", "standard"):
                        role = role_candidate

                users[username] = {
                    "password_hash": password_hash,
                    "first_login": first_login,
                    "role": role
                }
    except Exception as e:
        print(f"Erreur lors du chargement des utilisateurs: {e}")

    return users

def save_users(users: Dict[str, Dict]) -> None:
    """
    Sauvegarde au format complet (3 ou 4 champs selon présence du rôle).
    Toujours écrit le rôle pour homogénéiser.
    """
    try:
        with open(USER_FILE, "w", encoding="utf-8") as f:
            f.write("# Format: username:password_hash:first_login:role\n")
            f.write("# role = standard|power\n")
            for username, data in users.items():
                first_login = "true" if data.get("first_login", False) else "false"
                role = data.get("role", "standard")
                f.write(f"{username}:{data['password_hash']}:{first_login}:{role}\n")
    except Exception as e:
        print(f"Erreur lors de la sauvegarde des utilisateurs: {e}")

def verify_user(username: str, password: str) -> Tuple[bool, bool]:
    users = load_users()
    user = users.get(username)
    if not user:
        return False, False
    if hash_password(password) == user["password_hash"]:
        return True, user.get("first_login", False)
    return False, False

def get_user_role(username: str) -> str:
    users = load_users()
    user = users.get(username)
    if not user:
        return "standard"
    return user.get("role", "standard")

def change_password(username: str, old_password: str, new_password: str) -> bool:
    """
    Change le mot de passe si l'ancien est correct.
    """
    users = load_users()
    user = users.get(username)
    if not user:
        return False
    if hash_password(old_password) != user["password_hash"]:
        return False
    user["password_hash"] = hash_password(new_password)
    user["first_login"] = False
    users[username] = user
    save_users(users)
    return True