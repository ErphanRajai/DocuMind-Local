import httpx
import asyncio

async def test():
    async with httpx.AsyncClient() as client:
        # Test a standard global API
        res = await client.get("https://api.github.com")
        print("Status Code:", res.status_code)

asyncio.run(test())