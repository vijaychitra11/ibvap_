from fastapi.testclient import TestClient
from app.main import app

c=TestClient(app)
assert c.get('/api/status').status_code == 200
assert c.get('/cameras').status_code == 200
assert c.get('/alerts').status_code == 200
assert c.get('/fence/zones').status_code == 200
assert c.get('/fence/settings').status_code == 200
assert c.get('/analytics/models/status').status_code == 200
assert c.get('/analytics/summary').status_code == 200
assert c.get('/fence/polygons').status_code == 200
assert c.get('/watchlist/plates').status_code == 200
assert c.get('/faces/profiles').status_code == 200
print('IBVAP smoke tests passed')
