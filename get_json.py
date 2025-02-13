import os
import json
from cryptography.fernet import Fernet
import base64
import hashlib

def derive_key(passphrase: str) -> bytes:
    """Derives a key using SHA256 and encodes it for Fernet."""
    key = hashlib.sha256(passphrase.encode()).digest()
    return base64.urlsafe_b64encode(key)

def decrypt_json(input_file: str, passphrase: str) -> dict:
    """Decrypts a JSON file using the provided passphrase."""
    key = derive_key(passphrase)
    cipher = Fernet(key)
    
    try:
        # Read the encrypted file
        with open(input_file, "rb") as f:
            encrypted_data = f.read()
        
        # Decrypt the data
        decrypted_data = cipher.decrypt(encrypted_data).decode()
        print(f"Decryption completed for {input_file}.")
        
        # Convert the decrypted data to a Python dictionary
        return json.loads(decrypted_data)
    
    except Exception as e:
        print(f"Error decrypting {input_file}: {e}")
        return {}

def get_json_data():
    """Loads and decrypts JSON files using the passphrase `key101!`."""
    lst = []
    passphrase = os.getenv("PASSPHRASE")
    
    # List of JSON files to decrypt and load
    json_files = ["encrypted_links.json", "encrypted_token.json"]
    
    for file in json_files:
        decrypted_data = decrypt_json(file, passphrase)
        if decrypted_data:
            lst.append(decrypted_data)
    
    return lst
