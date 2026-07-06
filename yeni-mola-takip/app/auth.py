"""
Kimlik doğrulama yardımcıları.

Şifre hash'leme ve doğrulama işlemleri burada yapılır.
"""

import hashlib
import secrets


def hash_password(password: str) -> str:
    """Şifreyi tuzlu SHA-256 ile hash'ler."""
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}${digest}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Düz metin şifreyi hash ile karşılaştırır."""
    try:
        salt, digest = hashed_password.split("$", 1)
    except ValueError:
        return False
    check = hashlib.sha256(f"{salt}{plain_password}".encode()).hexdigest()
    return secrets.compare_digest(check, digest)
