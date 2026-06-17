import argparse, base64, hashlib
from pathlib import Path
from cryptography.fernet import Fernet

def main():
    parser = argparse.ArgumentParser(description="Secret sync via .aes")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--encrypt", action="store_true")
    group.add_argument("--decrypt", action="store_true")
    args = parser.parse_args()

    salt_path = Path(__file__).parent / ".aes"

    if not salt_path.exists():
        raise SystemExit(f"Error: Key file {salt_path} not found!")
    
    raw_key = hashlib.sha256(salt_path.read_text().strip().encode()).digest()
    fernet = Fernet(base64.urlsafe_b64encode(raw_key))

    try:
        if args.encrypt:
            Path(".env.enc").write_bytes(fernet.encrypt(Path(".env").read_bytes()))
            print("Packed .env -> .env.enc")
        elif args.decrypt:
            Path(".env").write_bytes(fernet.decrypt(Path(".env.enc").read_bytes()))
            print("Unpacked .env.enc -> .env")
    except Exception:
        raise SystemExit("Error: Operation failed. Check your .aes file!")

if __name__ == "__main__":
    main()

