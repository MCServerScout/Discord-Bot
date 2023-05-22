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


async def create_privVars():
    text = """#  Path: privVars.py
DISCORD_TOKEN = ""
DISCORD_WEBHOOK = ""
MONGO_URL = ""
"""
    if not os.path.exists("privVars.py"):
        with open("privVars.py", "w") as f:
            f.write(text)
            print("Created privVars.py")
    else:
        print("privVars.py already exists")


async def main():
    await install_requirements()
    await create_privVars()


if __name__ == "__main__":
    asyncio.run(main())
