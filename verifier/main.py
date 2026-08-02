import hashlib
import hmac
import json
import os
import sqlite3
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException

app = FastAPI()

DB = "/data/verifier_chain.db"
SHARED_SECRET = os.environ["VERIFIER_SHARED_SECRET"]
MAX_CLOCK_SKEW_SECONDS = 30


def init_db():
    conn = sqlite3.connect(DB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS observed_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vote_id INTEGER,
            record_hash TEXT,
            previous_hash TEXT,
            action TEXT,
            observed_at TEXT,
            received_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


init_db()


def sign_payload(payload: dict, secret: str) -> str:
    message = json.dumps(payload, sort_keys=True).encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


@app.post("/ingest")
def ingest(body: dict):
    payload = body.get("payload")
    signature = body.get("signature")

    if payload is None or signature is None:
        raise HTTPException(400, "Payload ou assinatura ausente")

    expected = sign_payload(payload, SHARED_SECRET)
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(403, "Assinatura inválida — payload rejeitado")

    try:
        observed = datetime.fromisoformat(payload["observed_at"])
    except (KeyError, ValueError):
        raise HTTPException(400, "observed_at ausente ou inválido")

    now = datetime.now(timezone.utc)
    if abs((now - observed).total_seconds()) > MAX_CLOCK_SKEW_SECONDS:
        raise HTTPException(403, "Payload expirado — possível replay attack")

    conn = sqlite3.connect(DB)
    conn.execute(
        "INSERT INTO observed_votes (vote_id, record_hash, previous_hash, action, observed_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            payload["vote_id"],
            payload["record_hash"],
            payload["previous_hash"],
            payload["action"],
            payload["observed_at"],
        ),
    )
    conn.commit()
    conn.close()
    return {"status": "recorded"}


@app.get("/verify/{vote_id}")
def verify(vote_id: int, current_hash: str):
    conn = sqlite3.connect(DB)
    row = conn.execute(
        "SELECT record_hash FROM observed_votes WHERE vote_id = ? ORDER BY id DESC LIMIT 1",
        (vote_id,),
    ).fetchone()
    conn.close()

    if row is None:
        raise HTTPException(404, "Voto nunca foi observado pelo verificador")

    if row[0] != current_hash:
        return {"status": "MISMATCH", "expected": row[0], "got": current_hash}
    return {"status": "OK"}
