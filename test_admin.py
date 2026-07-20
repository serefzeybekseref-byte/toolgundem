import os
# Mock the env var so we can hit the route without knowing it, or just read it
from app import app

admin_token = os.environ.get("ADMIN_TOKEN", "")

with app.test_client() as c:
    try:
        response = c.get(f'/admin?token={admin_token}')
        print("Status code:", response.status_code)
        if response.status_code == 500:
            print("Response:", response.data.decode('utf-8'))
    except Exception as e:
        import traceback
        traceback.print_exc()
