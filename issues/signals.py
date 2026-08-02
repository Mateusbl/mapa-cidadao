import hashlib
import hmac
import json
import os

import requests
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Vote

VERIFIER_URL = "http://verifier:9000/ingest"
SHARED_SECRET = os.getenv("VERIFIER_SHARED_SECRET")


def sign_payload(payload: dict, secret: str) -> str:
    message = json.dumps(payload, sort_keys=True).encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _send_to_verifier(vote, action):
    payload = {
        'vote_id': vote.id,
        'record_hash': vote.record_hash,
        'previous_hash': vote.previous_hash,
        'action': action,
        'observed_at': timezone.now().isoformat(),
    }
    signature = sign_payload(payload, SHARED_SECRET)
    try:
        requests.post(
            VERIFIER_URL,
            json={'payload': payload, 'signature': signature},
            timeout=3,
        )
    except requests.RequestException as e:
        # se o verificador estiver fora do ar, isso precisa ser visível, nunca engolido
        print(f"ERRO: falha ao notificar o verificador: {e}")


@receiver(post_save, sender=Vote)
def vote_saved(sender, instance, created, **kwargs):
    if created:  # só notifica na criação, não em updates (votos são append-only mesmo)
        _send_to_verifier(instance, 'created')