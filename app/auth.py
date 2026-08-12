import getpass
import sys
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(password: str, password_hash: str) -> bool:
    return bool(password_hash) and pwd_context.verify(password, password_hash)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "hash-password":
    password = getpass.getpass("Password: ")
    print(hash_password(password))
