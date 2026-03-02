from __future__ import annotations


def test_guest_session_start_and_me(client):
    start = client.post('/api/session/start', json={'role': 'student'})
    assert start.status_code == 200
    assert start.json()['data']['role'] == 'student'

    me = client.get('/api/session/me')
    assert me.status_code == 200
    assert me.json()['data']['role'] == 'student'


def test_guest_session_requires_valid_role(client):
    res = client.post('/api/session/start', json={'role': 'admin'})
    assert res.status_code == 400
