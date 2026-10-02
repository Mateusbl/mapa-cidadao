"""Envio dos votos ao Verifier (signal) e o próprio serviço Verifier."""
from datetime import datetime, timedelta, timezone

import pytest
import requests
from django.db import connection

from issues import signals
from issues.models import Vote

VERIFIER_URL = "http://verifier:9000"


class TestSignal:
    @pytest.fixture
    def sent(self, monkeypatch):
        calls = []
        monkeypatch.setattr(signals, 'SHARED_SECRET', 'segredo-de-teste')
        monkeypatch.setattr(signals.requests, 'post', lambda url, json, timeout: calls.append((url, json)))
        return calls

    def test_new_vote_is_sent_signed(self, sent, issue, user):
        vote = Vote.objects.create(issue=issue, user=user)
        assert len(sent) == 1
        url, body = sent[0]
        assert url == signals.VERIFIER_URL
        assert body['payload']['vote_id'] == vote.id
        assert body['payload']['record_hash'] == vote.record_hash
        assert body['signature'] == signals.sign_payload(body['payload'], 'segredo-de-teste')

    def test_revocation_is_not_sent(self, sent, issue, user):
        vote = Vote.objects.create(issue=issue, user=user)
        vote.is_active = False
        vote.save()
        assert len(sent) == 1

    def test_missing_secret_does_not_break_voting(self, monkeypatch, issue, user):
        monkeypatch.setattr(signals, 'SHARED_SECRET', None)
        vote = Vote.objects.create(issue=issue, user=user)
        assert Vote.objects.filter(pk=vote.pk).exists()

    def test_verifier_down_does_not_break_voting(self, monkeypatch, issue, user):
        monkeypatch.setattr(signals, 'SHARED_SECRET', 'x')

        def down(*args, **kwargs):
            raise requests.ConnectionError('fora do ar')

        monkeypatch.setattr(signals.requests, 'post', down)
        vote = Vote.objects.create(issue=issue, user=user)
        assert Vote.objects.filter(pk=vote.pk).exists()


# ---------- integração (requer o serviço Verifier no ar) ----------

def _payload(**overrides):
    payload = {
        'vote_id': 999999, 'record_hash': 'a' * 64, 'previous_hash': '', 'action': 'created',
        'observed_at': datetime.now(timezone.utc).isoformat(),
    }
    payload.update(overrides)
    return payload


@pytest.mark.integration
class TestVerifierIntegration:
    def test_vote_creation_reaches_verifier(self, issue, user):
        vote = Vote.objects.create(issue=issue, user=user)

        resp = requests.get(f"{VERIFIER_URL}/verify/{vote.id}", params={"current_hash": vote.record_hash})
        assert resp.json()["status"] == "OK"

    def test_verifier_detects_tampering(self, transactional_db, issue, user):
        vote = Vote.objects.create(issue=issue, user=user)

        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE issues_vote DISABLE TRIGGER block_vote_update;")
            cursor.execute("UPDATE issues_vote SET record_hash = %s WHERE id = %s", ["hash_falso", vote.id])
            cursor.execute("ALTER TABLE issues_vote ENABLE TRIGGER block_vote_update;")

        resp = requests.get(f"{VERIFIER_URL}/verify/{vote.id}", params={"current_hash": "hash_falso"})
        data = resp.json()
        assert data["status"] == "MISMATCH"
        assert data["expected"] == vote.compute_hash()

    def test_rejects_wrong_signature(self):
        payload = _payload()
        resp = requests.post(f"{VERIFIER_URL}/ingest", json={
            'payload': payload, 'signature': signals.sign_payload(payload, 'segredo-errado'),
        })
        assert resp.status_code == 403

    def test_rejects_replayed_payload(self):
        old = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        payload = _payload(observed_at=old)
        resp = requests.post(f"{VERIFIER_URL}/ingest", json={
            'payload': payload, 'signature': signals.sign_payload(payload, signals.SHARED_SECRET),
        })
        assert resp.status_code == 403
        assert 'replay' in resp.json()['detail']

    def test_rejects_missing_signature(self):
        resp = requests.post(f"{VERIFIER_URL}/ingest", json={'payload': _payload()})
        assert resp.status_code == 400

    def test_unknown_vote_is_404(self):
        resp = requests.get(f"{VERIFIER_URL}/verify/123456789", params={"current_hash": "x"})
        assert resp.status_code == 404
