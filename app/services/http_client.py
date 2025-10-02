from __future__ import annotations

from enum import Enum

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Classi e Enum per gestire richieste HTTP in modo strutturato
API_PREFIX = settings.API_PREFIX

class HttpClientException(Exception):
    """Eccezione personalizzata per errori nelle richieste HTTP.
    Attributes:
        status_code (int | None): Codice di stato HTTP della risposta, se disponibile.
        server_message (str): Messaggio di errore restituito dal server.
        url (str): URL della richiesta che ha causato l'errore.
    """

    def __init__(self, message: str, server_message: str, status_code: int, url: str = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.server_message = server_message
        self.url = url