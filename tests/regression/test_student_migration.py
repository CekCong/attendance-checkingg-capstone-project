"""Real backend and face-service integration using repository sample images."""
import base64
import uuid
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def test_enroll_sign_and_reject_static_replay(client, test_student, test_session,
                                             test_enrollment, auth_headers_student):
    headers = auth_headers_student
    update = client.put('/api/v1/users/me', headers=headers, json={'camera_consent':True, 'geolocation_consent':True})
    assert update.status_code == 200
    sample = Path(__file__).resolve().parents[2] / 'sample_images' / 'obama.jpg'
    image = base64.b64encode(sample.read_bytes()).decode()
    enrollment = client.post('/api/v1/users/me/face/enroll', headers=headers, json={'image':image}, timeout=90)
    assert enrollment.status_code == 200, enrollment.text
    assert enrollment.json()['face_enrolled']
    profile = client.get('/api/v1/users/me', headers=headers)
    assert profile.json()['camera_consent'] and profile.json()['geolocation_consent']
    sessions = client.get('/api/v1/sessions/my-sessions?status=active', headers=headers)
    assert sessions.status_code == 200
    assert any(row['id'] == test_session['id'] for row in sessions.json())

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    fingerprint = uuid.uuid4().hex
    registered = client.post('/api/v1/devices/register', headers=headers, json={'device_fingerprint':fingerprint, 'platform':'web', 'public_key':public})
    assert registered.status_code == 201
    device = client.post('/api/v1/devices/challenge', headers=headers, json={'device_fingerprint':fingerprint, 'session_id':test_session['id']})
    assert device.status_code == 200
    challenge = device.json()['challenge']
    signature = key.sign(challenge.encode(), padding.PSS(mgf=padding.MGF1(hashes.SHA256()),salt_length=32), hashes.SHA256())
    ticket = client.post('/api/v1/checkins/liveness-challenge', headers=headers, json={'session_id':test_session['id']})
    assert ticket.status_code == 200
    submitted = client.post('/api/v1/checkins/', headers=headers, timeout=120, json={
        'session_id':test_session['id'], 'latitude':1.3483, 'longitude':103.6831, 'location_accuracy_meters':20,
        'device_fingerprint':fingerprint, 'device_challenge':challenge, 'device_signature':base64.b64encode(signature).decode(),
        'liveness_challenge_id':ticket.json()['challenge_id'], 'liveness_challenge_type':ticket.json()['challenge_type'],
        'liveness_challenge_response':[image] * 15,
    })
    assert submitted.status_code == 201, submitted.text
    assert submitted.json()['liveness_passed'] is False
    assert submitted.json()['status'] == 'rejected'
    assert 'face_image' not in submitted.json()
    history = client.get('/api/v1/checkins/my-checkins', headers=headers)
    assert any(row['id'] == submitted.json()['id'] and row['status'] == 'rejected' for row in history.json())
