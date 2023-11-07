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

    num_docs = col.count_documents({})
    num_docs = str(num_docs)[0:2] + "0" * (len(str(num_docs)) - 2)
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
    server = "10.0.0.134"
    port = 25565

    res = await mcLib.join(
        ip=server,
        port=port,
        player_username=uname,
        mine_token=token,
    )

    print(res)


if __name__ == "__main__":
    asyncio.run(main())
