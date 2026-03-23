import asyncio
import httpx

async def main():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # Try login to get token
        login_payload = {"email": "test@test.com", "password": "password"}
        res = await client.post("/api/users/login", json=login_payload)
        token = res.json().get("access_token")
        
        # Create campaign
        res = await client.post("/api/campaigns", json={
            "name": "Test Campaign",
            "vertical": "vc",
            "target_roles": ["Partner"]
        }, headers={"Authorization": f"Bearer {token}"})
        
        if res.status_code != 201:
            print("Failed to create campaign:", res.text)
            return
            
        camp_id = res.json()["id"]
        print(f"Testing stats for campaign {camp_id}...")
        
        # Hit stats
        res = await client.get(f"/api/leads/campaign/{camp_id}/stats", headers={"Authorization": f"Bearer {token}"})
        print("Stats Status:", res.status_code)
        if res.status_code != 200:
            print("Stats Body:", res.text)
        else:
            print("Stats successful:", res.json())
        
        # Hit leads list
        res = await client.get(f"/api/leads/campaign/{camp_id}?page=1&per_page=50", headers={"Authorization": f"Bearer {token}"})
        print("Leads List Status:", res.status_code)
        if res.status_code != 200:
            print("Leads List Error:", res.text)
        else:
            print("Leads returned:", len(res.json().get('leads', [])))

if __name__ == "__main__":
    asyncio.run(main())
