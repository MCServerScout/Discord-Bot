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

    req_url = "https://raw.githubusercontent.com/MCServerScout/Discord-Bot/master/requirements.txt"
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


async def create_files():
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
# cstats = ""  # optional, custom text added to the stats message

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

    # create and populate the assets folder
    if not os.path.exists("assets"):
        os.mkdir("assets")
        print("Created assets folder")
    else:
        print("assets folder already exists")

    # populate the assets folder with the default images
    if not os.path.exists("assets/DefFavicon.png"):
        async with aiohttp.ClientSession() as session, session.get(
            "https://raw.githubusercontent.com/MCServerScout/Discord-Bot/master/assets/DefFavicon.png"
        ) as resp:
            with open("assets/DefFavicon.png", "wb") as f:
                f.write(await resp.read())
    if not os.path.exists("assets/loading.png"):
        async with aiohttp.ClientSession() as session, session.get(
            "https://raw.githubusercontent.com/MCServerScout/Discord-Bot/master/assets/loading.png"
        ) as resp:
            with open("assets/loading.png", "wb") as f:
                f.write(await resp.read())


async def main():
    await install_requirements()
    await create_files()
    print("Setup complete, please edit `privVars.py` before running the scanner.")


if __name__ == "__main__":
    asyncio.run(main())
