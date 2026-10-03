"""Cifra em repouso com `APP_SECRET_KEY` (estável por instalação). Use para guardar no banco o que
não pode ficar em texto puro (chaves de API de terceiros, tokens…). Se a chave mudar, o que foi
cifrado antes deixa de abrir — por isso o app Android a gera uma vez só."""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

PREFIX = "enc:"


class SecretBox:
    def __init__(self, secret_key: str):
        self._fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest()))

    def encrypt(self, value: str) -> str:
        if not value or value.startswith(PREFIX):
            return value
        return PREFIX + self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        """Devolve "" se o valor foi cifrado com outra chave; texto sem o prefixo passa como está."""
        if not value or not value.startswith(PREFIX):
            return value
        try:
            return self._fernet.decrypt(value[len(PREFIX):].encode()).decode()
        except InvalidToken:
            return ""
