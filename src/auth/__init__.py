"""
PicFrame 4.0 - Authentication Module.

Handles:
- JWT token creation and validation
- Pairing code generation and verification
- Device authentication models
"""

from src.auth.jwt_handler import create_token, verify_token
from src.auth.pairing import generate_pairing_code, verify_pairing_code

__all__ = [
    "create_token",
    "verify_token",
    "generate_pairing_code",
    "verify_pairing_code",
]
