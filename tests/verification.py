"""HTTP fixtures using real enrollment, RSA proof and an intentionally static replay.

These inputs must be rejected by active liveness. They verify the complete API
path and persisted results, not positive live-person acceptance.
"""
import base64
import uuid
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def prepare_static_replay(client, headers, session_id, issue_challenges=True):
    consent = client.put('/api/v1/users/me', headers=headers, json={
        'camera_consent': True, 'geolocation_consent': True})
    assert consent.status_code == 200, consent.text
    image = base64.b64encode((Path(__file__).resolve().parents[1] / 'sample_images/obama.jpg').read_bytes()).decode()
    enrolled = client.post('/api/v1/users/me/face/enroll', headers=headers, json={'image': image}, timeout=90)
    assert enrolled.status_code == 200, enrolled.text
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    fingerprint = uuid.uuid4().hex
    registered = client.post('/api/v1/devices/register', headers=headers, json={
        'device_fingerprint': fingerprint, 'platform': 'web', 'public_key': public})
    assert registered.status_code == 201, registered.text
    body = {'session_id': session_id, 'latitude': 1.3483, 'longitude': 103.6831,
        'location_accuracy_meters': 20, 'device_fingerprint': fingerprint,
        'liveness_challenge_response': [image] * 15, '_private_key': key}
    return issue_proofs(client, headers, body) if issue_challenges else body


def issue_proofs(client, headers, prepared):
    body = dict(prepared)
    key = body.pop('_private_key')
    fingerprint, session_id = body['device_fingerprint'], body['session_id']
    nonce = client.post('/api/v1/devices/challenge', headers=headers, json={
        'device_fingerprint': fingerprint, 'session_id': session_id})
    assert nonce.status_code == 200, nonce.text
    challenge = nonce.json()['challenge']
    signature = key.sign(challenge.encode(), padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())
    ticket = client.post('/api/v1/checkins/liveness-challenge', headers=headers, json={'session_id': session_id})
    assert ticket.status_code == 200, ticket.text
    body.update(device_challenge=challenge, device_signature=base64.b64encode(signature).decode(),
        liveness_challenge_id=ticket.json()['challenge_id'], liveness_challenge_type=ticket.json()['challenge_type'])
    return body
