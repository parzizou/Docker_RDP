import os
import hashlib
import json
from typing import Dict, Optional, List, Tuple

# Chemin du fichier utilisateurs
USER_FILE = "users.txt"

def hash_password(password: str) -> str:
    """Hash le mot de passe en utilisant SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def load_users() -> Dict:
    """Charge les utilisateurs depuis le fichier texte"""
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
                if len(parts) >= 3:
                    username = parts[0]
                    password_hash = parts[1]
                    first_login = parts[2].lower() == "true"
                    users[username] = {
                        "password_hash": password_hash,
                        "first_login": first_login
                    }
    except Exception as e:
        print(f"Erreur lors du chargement des utilisateurs: {e}")
    
    return users

def save_users(users: Dict) -> None:
    """Sauvegarde les utilisateurs dans le fichier texte"""
    try:
        with open(USER_FILE, "w", encoding="utf-8") as f:
            f.write("# Format: username:password_hash:first_login\n")
            for username, data in users.items():
                first_login = "true" if data.get("first_login", False) else "false"
                f.write(f"{username}:{data['password_hash']}:{first_login}\n")
    except Exception as e:
        print(f"Erreur lors de la sauvegarde des utilisateurs: {e}")

def verify_user(username: str, password: str) -> Tuple[bool, bool]:
    """
    Vérifie les identifiants utilisateur
    Retourne: (authentification_réussie, première_connexion)
    """
    users = load_users()
    user = users.get(username)
    
    if not user:
        return False, False
    
    password_hash = hash_password(password)
    if password_hash == user["password_hash"]:
        return True, user.get("first_login", False)
    
    return False, False

def change_password(username: str, new_password: str) -> bool:
    """Change le mot de passe d'un utilisateur et désactive la première connexion"""
    users = load_users()
    if username not in users:
        return False
    
    users[username]["password_hash"] = hash_password(new_password)
    users[username]["first_login"] = False
    save_users(users)
    return True