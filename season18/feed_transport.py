"""Read GitHub JSON snapshots without the contents API's 1 MiB embedding limit."""
import base64
import json

RAW_ACCEPT='application/vnd.github.raw+json'


def decode_snapshot(payload):
    # Raw-media responses contain the snapshot itself, regardless of file size.
    # Accept embedded legacy responses too, for backwards-compatible readers.
    if isinstance(payload,dict) and payload.get('encoding')=='base64' and payload.get('content'):
        payload=json.loads(base64.b64decode(payload['content']))
    elif isinstance(payload,dict) and payload.get('content') and 'version' not in payload:
        payload=json.loads(base64.b64decode(payload['content']))
    if not isinstance(payload,dict) or payload.get('version')!=1 or payload.get('season')!=18 or not isinstance(payload.get('players'),dict):
        raise ValueError('Saved competition snapshot is unavailable or invalid; existing results must be retained.')
    return payload
