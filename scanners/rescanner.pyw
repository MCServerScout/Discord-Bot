import asyncio
import os
import sys
import traceback

import sentry_sdk
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from sentry_sdk.integrations.aiohttp import AioHttpIntegration

try:
    import pyutils
except ImportError:
    # get the path of the parent directory
    current = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(current)

    # add the parent directory to the path
    sys.path.append(parent)

    # try importing again
    import pyutils

(
    DISCORD_WEBHOOK,
    DISCORD_TOKEN,
    MONGO_URL,
    db_name,
    col_name,
    client_id,
    client_secret,
    IP_INFO_TOKEN,
    cstats,
    azure_client_id,
    azure_redirect_uri,
    SENTRY_TOKEN,
    SENTRY_URI,
) = ["..." for _ in range(13)]

DEBUG = False
try:
    from privVars import *
except ImportError:
    MONGO_URL = ""
    TOKEN = "..."

if MONGO_URL == "...":
    print("Please add your mongo url to 'privVars.py'")
    sys.exit("Config error in privVars.py, please fix before rerunning")
if DISCORD_TOKEN == "...":
    print("Please add your bot token to 'privVars.py'")
    sys.exit("Config error in privVars.py, please fix before rerunning")

# Setup
# ---------------------------------------------

# error tracking
sentry_sdk.init(
    dsn=SENTRY_URI,
    traces_sample_rate=1.0,
    profiles_sample_rate=0.6,
    integrations=[AioHttpIntegration()],
) if SENTRY_URI != "..." else None

# test the db connection
print("Connecting to database...")
try:
    client = MongoClient(MONGO_URL)
    db = client["MCSS" if db_name == "..." else db_name]
    col = db["scannedServers" if col_name == "..." else col_name]
except ServerSelectionTimeoutError:
    print("Error connecting to database")
    print(traceback.format_exc())
    sys.exit("Config error in privVars.py, please fix before rerunning")
else:
    print("Connected to database")

utils = pyutils.Utils(
    col,
    debug=DEBUG,
    discord_webhook=DISCORD_WEBHOOK,
    client_id=client_id,
    client_secret=client_secret,
    info_token=IP_INFO_TOKEN,
    ssdk=((sentry_sdk,),),
)
logger = utils.logger
databaseLib = utils.database
playerLib = utils.player
messageLib = utils.message
twitchLib = utils.twitch
textLib = utils.text
serverLib = utils.server
mcLib = utils.mc


async def main():
    pipeline = [
        {
            "$match": {
                "$and": [
                    {"players.sample": {"$exists": True}},
                    {"players.max": {"$gt": 0}},
                    {"hasForgeData": False},
                    {"modpackData": {"$exists": False}},
                    {"whitelist": {"$exists": False}},
                ]
            }
        },
        {"$sort": {"lastSeen": -1}},
    ]

    # whitelist can be False, True, or None (not online to test)

    # we need a minecraft token, to join the server
    # first a link
    link, vCode = mcLib.get_activation_code_url(azure_client_id, azure_redirect_uri)
    logger.print(f"Please visit {link} and enter the code below")

    access_code = input("Code: ").strip()

    # then we need to get the token
    result = await mcLib.get_minecraft_token_async(
        azure_client_id, azure_redirect_uri, access_code, vCode
    )
    assert result["type"] == "success", "Error getting minecraft token"
    token = result["minecraft_token"]
    uname = result["name"]

    # now we can join the server
    servers = databaseLib.aggregate(pipeline)
    count = databaseLib.count(pipeline)
    logger.print(f"Found {count} servers to scan")

    for server in servers:
        try:
            sType = await mcLib.join(
                ip=server["ip"],
                port=server["port"],
                player_username=uname,
                mine_token=token,
                version=server["version"]["protocol"],
            )
        except Exception as e:
            logger.print(f"Error joining {server['ip']}")
            logger.print(e)
            sentry_sdk.capture_exception(e)
            continue

        if sType.status == "WHITELISTED":
            logger.print(f"Whitelisted: {server['ip']}")
            databaseLib.update_one(
                {"_id": server["_id"]}, {"$set": {"whitelist": True}}
            )
        elif sType.status == "PREMIUM" or sType.status == "MODDED":
            logger.print(f"Premium: {server['ip']}")
            databaseLib.update_one(
                {"_id": server["_id"]}, {"$set": {"whitelist": False}}
            )
        elif sType.status == "HONEY_POT":
            logger.print(f"Honey Pot: {server['ip']}")
            databaseLib.update_one(
                {"_id": server["_id"]}, {"$set": {"whitelist": True}}
            )
        else:
            # logger.print(f"Unknown: {server['ip']} ({sType.status})", end="\r")
            databaseLib.update_one(
                {"_id": server["_id"]}, {"$set": {"whitelist": None}}
            )


if __name__ == "__main__":
    asyncio.run(main())
