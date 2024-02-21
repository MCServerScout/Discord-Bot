"""Install requirements.txt and create privVars.py"""

import asyncio
import os
import sys

import aiohttp


async def install_requirements():
    # check that python is 3.10+
    if sys.version_info[0] != 3 or (
        sys.version_info[0] == 3 and sys.version_info[1] < 10
    ):
        print("Python 3.10+ is required.")
        sys.exit("Python 3.10+ is required.")

    req_url = "https://raw.githubusercontent.com/MCServerScout/Discord-Bot/master/requirements.txt"
    print("Downloading requirements.txt")
    async with aiohttp.ClientSession() as session, session.get(req_url) as resp:
        with open("requirements.txt", "wb") as f:
            f.write(await resp.read())

    try:
        from pip import pipmain
    except ImportError:
        from pip._internal.main import main as pipmain

    print("Installing requirements.txt")
    pipmain(["install", "-Ur", "requirements.txt"])

    # download the botHandler
    async with aiohttp.ClientSession() as session, session.get(
        "https://raw.githubusercontent.com/MCServerScout/Discord-Bot/master/botHandler.pyw"
    ) as resp:
        with open("botHandler.py", "wb") as f:
            f.write(await resp.read())

    os.mkdir("Discord-Bot")


async def create_files():
    text = """#  Path: privVars.py
# any variable with a default value is optional, while those with '...' are required
DISCORD_TOKEN = "..."
DISCORD_WEBHOOK = "..."
MONGO_URL = "..."
client_id = "..."  # twitch client id
client_secret = "..."  # twitch client secret

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

    if not os.path.exists("assets/graphs"):
        os.mkdir("assets/graphs")
        print("Created assets/graphs folder")
    else:
        print("assets/graphs folder already exists")

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

    # create the main git folder
    if not os.path.exists("Discord-Bot"):
        os.mkdir("Discord-Bot")
        print("Created Discord-Bot folder")
    else:
        print("Discord-Bot folder already exists")


def setup_db():
    uri = input("Enter the MongoDB URI or press ENTER to skip:\n>")
    if not uri:
        return

    with open("privVars.py", "r") as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        if line.startswith("MONGO_URL"):
            lines[i] = f'MONGO_URL = "{uri}"\n'
            break
    with open("privVars.py", "w") as f:
        f.writelines(lines)

    from pymongo import MongoClient

    try:
        client = MongoClient(uri)
        client.list_database_names()
    except Exception as e:
        print(f"Failed to connect to MongoDB: {e}")
        sys.exit(1)

    # create the MCSS database if it doesn't exist
    if "MCSS" not in client.list_database_names():
        db = client["MCSS"]
        print("Created MCSS database")
    else:
        db = client.MCSS

    # create the collection scannedServers if it doesn't exist
    if "scannedServers" not in db.list_collection_names():
        db.create_collection("scannedServers")
        print("Created scannedServers collection")

    # add a bogus entry to the collection if no entries exist
    if db.scannedServers.count_documents({}) == 0:
        db.scannedServers.insert_one(
            {
                "description": {"text": "A Minecraft Server"},
                "hasFavicon": False,
                "hasForgeData": True,
                "ip": "127.0.0.1",
                "lastSeen": 0,
                "cracked": False,
                "players": {
                    "max": 20,
                    "online": 1,
                    "sample": [
                        {
                            "id": "00000000-0000-0000-0000-000000000000",
                            "name": "Player",
                            "lastSeen": 1234567890,
                        }
                    ],
                },
                "port": 25565,
                "version": {"name": "1.16.5", "protocol": 754},
                "modpackData": {},
                "mods": [],
                "preventsChatReports": False,
                "previewsChat": False,
                "forgeData": {},
                "geo": {"lat": 0, "lon": 0, "city": "", "country": "", "hostname": ""},
                "whitelist": None,
                "domain": "example.com",
            }
        )
        print("Added a bogus entry to scannedServers collection")

    print("Database setup complete")


async def main():
    await install_requirements()
    await create_files()
    setup_db()
    print("Setup complete, please edit `privVars.py` before running the scanner.")


if __name__ == "__main__":
    asyncio.run(main())
