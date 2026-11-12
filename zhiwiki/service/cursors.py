"""Authenticated pagination tokens bound to owner, query, order and expiration."""

import base64
import hashlib
import hmac
import json
import secrets
import time

from .common import ServiceError, encode


def secret(connection):
    # This is server state, not a browser key or caller-supplied identity.
    connection.execute("INSERT OR IGNORE INTO team_runtime VALUES('cursor_key',?)", (secrets.token_hex(32),))
    return connection.execute("SELECT payload FROM team_runtime WHERE name='cursor_key'").fetchone()[0].encode()


def issue(key, owner, kb_id, after, limit):
    payload = encode([owner, kb_id, after, limit, int(time.time()) + 600]).encode()
    signature = hmac.new(key, payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature + payload).decode().rstrip('=')


def decode(key, value, owner, kb_id, limit):
    try:
        if len(value) > 2048:
            raise ValueError()
        raw = base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
        signature, payload = raw[:32], raw[32:]
        data = json.loads(payload)
        if (not hmac.compare_digest(signature, hmac.new(key, payload, hashlib.sha256).digest())
                or data[:2] != [owner, kb_id] or data[3] != limit or data[4] <= time.time()
                or not isinstance(data[2], str) or len(data[2]) > 100):
            raise ValueError()
        return data[2]
    except (ValueError, TypeError, IndexError, UnicodeError):
        raise ServiceError(400, 'INVALID_CURSOR') from None


def issue_scoped(key, owner, query_identity, after, limit):
    """Domain-separate new lists from legacy document pagination tokens."""
    payload = encode(["console-v1", owner, query_identity, after, limit, int(time.time()) + 600]).encode()
    signature = hmac.new(key, payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature + payload).decode().rstrip("=")


def decode_scoped(key, value, owner, query_identity, limit):
    """Bind the cursor to its list, filters, identity and current ACL epoch."""
    try:
        if not isinstance(value, str) or len(value) > 2048:
            raise ValueError()
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        signature, payload = raw[:32], raw[32:]
        data = json.loads(payload)
        valid = (hmac.compare_digest(signature, hmac.new(key, payload, hashlib.sha256).digest())
                 and isinstance(data, list) and len(data) == 6
                 and data[:3] == ["console-v1", owner, query_identity]
                 and isinstance(data[3], str) and len(data[3]) <= 100
                 and type(data[4]) is int and data[4] == limit
                 and type(data[5]) is int and data[5] > time.time())
        if not valid:
            raise ValueError()
        return data[3]
    except (ValueError, TypeError, IndexError, UnicodeError):
        raise ServiceError(400, "INVALID_CURSOR") from None
