"""
Run this script to generate a hashed password for config.py.

Usage:
    python generate_password_hash.py
"""
from werkzeug.security import generate_password_hash

username = input("Username: ")
password = input("Password: ")
hashed = generate_password_hash(password)
print(f"\nAdd this to USERS in config.py:")
print(f"    '{username}': '{hashed}',")
