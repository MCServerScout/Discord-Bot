"""Install requirements.txt and create privVars.py"""

import asyncio
import os
import sys

import aiohttp


async def install_requirements():
    # check that python is 3.10+
    if sys.version_info[0] != 3 and sys.version_info[1] < 10:
        print("Python 3.10+ is required.")
        sys.exit("Python 3.10+ is required.")

    req_url = "https://raw.githubusercontent.com/ServerScout-bust-cosmic-trespass/Discord-Bot/master/requirements.txt"
    print("Downloading requirements.txt")
    async with aiohttp.ClientSession() as session, session.get(req_url) as resp:
        with open("requirements.txt", "wb") as f:
            f.write(await resp.read())

    proc = await asyncio.create_subprocess_shell(
        "pip install -Ur requirements.txt",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    print(f"[stdout]\n{stdout.decode()}")
    print(f"[stderr]\n{stderr.decode()}")


async def create_priv_vars():
    text = """#  Path: privVars.py
# any variable with a default value is optional, while those with '...' are required
DISCORD_TOKEN = "..."
DISCORD_WEBHOOK = "..."
MONGO_URL = "..."
# db_name = "MCSS"  # optional
# col_name = "scannedServers"  # optional
client_id = "..."  # twitch client id
client_secret = "..."  # twitch client secret
# DEBUG = False  # optional
IP_INFO_TOKEN = "..."  # ipinfo.io token

# scanner settings
max_threads = 10
max_pps = 1000

"""
    if not os.path.exists("privVars.py"):
        with open("privVars.py", "w") as f:
            f.write(text)
            print("Created privVars.py")
    else:
        print("privVars.py already exists")


async def main():
    await install_requirements()
    await create_priv_vars()


if __name__ == "__main__":
    asyncio.run(main())
