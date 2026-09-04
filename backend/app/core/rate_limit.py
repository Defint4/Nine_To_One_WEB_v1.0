from slowapi import Limiter
from slowapi.util import get_remote_address

# En prod, uvicorn tourne derrière nginx avec --proxy-headers --forwarded-allow-ips 127.0.0.1 :
# sans ça, toutes les requêtes partagent l'IP du reverse proxy et le quota est commun à tous.
limiter = Limiter(key_func=get_remote_address)
