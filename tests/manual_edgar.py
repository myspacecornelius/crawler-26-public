import asyncio
import aiohttp
import json

async def test():
    async with aiohttp.ClientSession() as s:
        params = {
            "entityName": "accel",
            "dateRange": "all",
            "category": "custom",
            "forms": "D,ADV",
        }
        async with s.get("https://efts.sec.gov/LATEST/search-index", params=params, headers={"User-Agent": "CRAWL EmailMiner/1.0 (contact@example.com)"}) as r:
            data = await r.json()
            print("Hits for accel:", data.get("hits", {}).get("total", {}))
            
asyncio.run(test())
