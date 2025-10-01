from __future__ import annotations

from enum import Enum

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Classi e Enum per gestire richieste HTTP in modo strutturato
API_PREFIX = settings.API_PREFIX


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class HttpUrl(str, Enum):
    USERS_SERVICE = settings.USERS_SERVICE_URL


class HttpParams():
    """Rappresenta i parametri di una richiesta HTTP.
    Attributes:
        params (dict): Dizionario dei parametri della query.
    """
    def __init__(self, initial_params: dict | None = None):
        """Inizializza i parametri della richiesta HTTP.

        Args:
            initial_params (dict | None, optional): Parametri iniziali da includere nella richiesta. Defaults to None.
        """
        if(initial_params is None):
            self.params = {}
        else:
            self.params = initial_params.copy()

    def add_param(self, key: str, value: any):
        """Aggiunge un parametro alla query della richiesta HTTP.
        Args:
            key (str): Nome del parametro.
            value (any): Valore del parametro.
        """
        self.params[key] = value

    def to_dict(self) -> dict:
        """Restituisce i parametri come dizionario.
        Returns:
            dict: Dizionario dei parametri della query.
        """
        return self.params


class HttpHeaders():
    """Rappresenta gli headers di una richiesta HTTP.
    Attributes:
        headers (dict): Dizionario degli headers HTTP.
    """

    def __init__(self, initial_headers: dict | None = None):
        self.headers = initial_headers.copy() if initial_headers else {}
        self.headers.setdefault("Content-Type", "application/json")
        self.headers.setdefault("Accept", "application/json")

    def add_header(self, key: str, value: str):
        """Aggiunge un header alla richiesta HTTP.

        Args:
            key (str): Nome dell'header.
            value (str): Valore dell'header.
        """
        self.headers[key] = value

    def to_dict(self) -> dict:
        """Restituisce gli headers come dizionario.

        Returns:
            dict: Dizionario degli headers HTTP.
        """
        return self.headers


# Errori e risposte


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


class HttpClientResponse():
    """Rappresenta la risposta di un client HTTP.
    Attributes:
        status_code (int): Codice di stato HTTP della risposta.
        data (dict | list | str | None): Dati della risposta, se presenti.
    """

    def __init__(self, status_code: int, data: dict | list | str | None = None):
        self.status_code = status_code
        self.data = data