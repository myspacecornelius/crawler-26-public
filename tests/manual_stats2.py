import asyncio
from fastapi.testclient import TestClient
from api.main import app

def main():
    with TestClient(app) as client:
        # Register/Login
        res = client.post("/api/users/login", json={"email": "test2@test.com", "password": "password"})
        if "access_token" not in res.json():
            res = client.post("/api/users/register", json={"email": "test2@test.com", "password": "password", "name": "Test2"})
            res = client.post("/api/users/login", json={"email": "test2@test.com", "password": "password"})
            
        token = res.json()["access_token"]
        
        # Create campaign
        res = client.post("/api/campaigns", json={
            "name": "Test Campaign 2",
            "vertical": "vc",
            "target_roles": ["Partner"]
        }, headers={"Authorization": f"Bearer {token}"})
        
        camp_id = res.json()["id"]
        
        print("Testing stats via TestClient...")
        try:
            res = client.get(f"/api/leads/campaign/{camp_id}?page=1&per_page=50", headers={"Authorization": f"Bearer {token}"})
            print("Status:", res.status_code)
            print("Response:", res.text)
        except Exception as e:
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
