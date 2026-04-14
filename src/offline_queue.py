"""Offline queue for storing actions when offline and syncing later.

This module stores offline actions in the DB (`OfflineAction`) and provides
helpers to enqueue actions and attempt to sync them to a remote API endpoint.
"""
import json
import logging
import requests
import time
from typing import Any, Dict, List, Optional

from .db import get_session, OfflineAction

LOG = logging.getLogger(__name__)


def enqueue_action(action_type: str, payload: Dict[str, Any]) -> int:
    """Store an offline action in DB and return its id."""
    sess = get_session()
    try:
        oa = OfflineAction(action_type=action_type, payload=payload)
        sess.add(oa)
        sess.commit()
        oid = oa.id
        return oid
    except Exception:
        sess.rollback()
        LOG.exception('Failed to enqueue offline action')
        return -1
    finally:
        sess.close()


def get_pending(limit: int = 50) -> List[OfflineAction]:
    sess = get_session()
    try:
        rows = sess.query(OfflineAction).filter(OfflineAction.processed == False).order_by(OfflineAction.created_at).limit(limit).all()
        return rows
    finally:
        sess.close()


def mark_processed(action_id: int, success: bool, error: Optional[str] = None):
    sess = get_session()
    try:
        oa = sess.query(OfflineAction).get(action_id)
        if not oa:
            return
        oa.processed = success
        oa.attempts = (oa.attempts or 0) + 1
        oa.last_error = error
        sess.add(oa)
        sess.commit()
    except Exception:
        sess.rollback()
        LOG.exception('Failed to mark offline action processed')
    finally:
        sess.close()


def process_queue(server_url: str, api_key: Optional[str] = None, limit: int = 50, backoff: float = 1.5) -> Dict[str, Any]:
    """Attempt to deliver pending offline actions to server endpoint.

    Sends a POST to `{server_url}/api/v1/sync/actions` with a JSON list of actions.
    Returns summary dict.
    """
    pending = get_pending(limit=limit)
    if not pending:
        return {'sent': 0, 'errors': 0}

    payload = []
    for oa in pending:
        payload.append({
            'id': oa.id,
            'action_type': oa.action_type,
            'payload': oa.payload,
            'created_at': oa.created_at.isoformat() if oa.created_at is not None else None,
        })

    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'

    url = server_url.rstrip('/') + '/api/v1/sync/actions'
    try:
        resp = requests.post(url, json={'actions': payload}, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json() or {}
            processed_ids = data.get('processed_ids') or []
            errors = data.get('errors') or []
            for pid in processed_ids:
                mark_processed(pid, True, None)
            for err in errors:
                try:
                    mark_processed(err.get('id'), False, err.get('error'))
                except Exception:
                    pass
            return {'sent': len(processed_ids), 'errors': len(errors)}
        else:
            LOG.warning('Server returned %s when syncing offline queue', resp.status_code)
            return {'sent': 0, 'errors': 1}
    except Exception as e:
        LOG.exception('Failed to process offline queue')
        return {'sent': 0, 'errors': 1}
