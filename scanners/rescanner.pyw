import asyncio
import os
import queue
import sys
import threading
import time
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


async def queue_online_servers(servers, _queue):
    for server in servers:
        # check if the server is online
        # first try and send a syn packet
        try:
            assert await mcLib.send_syn(server["ip"], server["port"])
        except AssertionError:
            continue
        except Exception as e:
            logger.print(f"Error sending syn to {server['ip']}")
            logger.print(e)
            sentry_sdk.capture_exception(e)
            continue

        # next try and get the server status
        try:
            status = serverLib.status(server["ip"], server["port"])
        except Exception as e:
            logger.print(f"Error getting status for {server['ip']}")
            logger.print(e)
            sentry_sdk.capture_exception(e)
            continue

        if status is None:
            logger.print(f"Error getting status for {server['ip']}")
            continue

        # add the server to the list of online servers
        new_dict = {
            "_id": server["_id"],
            "ip": server["ip"],
            "port": server["port"],
            "version": status["version"],
        }

        _queue.put(new_dict)


def queue_callback(servers, _queue):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(queue_online_servers(servers, _queue))
    loop.close()


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

    online_servers = queue.Queue()

    status_thread = threading.Thread(
        target=queue_callback, args=(servers, online_servers)
    )
    status_thread.start()

    num_requests = 0
    max_requests = 30
    requests_start = 0
    request_duration = 60

    try:
        while True:
            server = online_servers.get()
            # the join function is rate limited, so we need to use round-robin scheduling
            # the rate limit is 300 per 10 minutes, so we can do 0.5 per second

            if num_requests >= max_requests:
                # we have reached the rate limit, wait until the next 10-minute period
                logger.print("Rate limit reached, waiting until the next period")
                while time.time() - requests_start < request_duration:
                    await asyncio.sleep(1)

            if requests_start == 0:
                # initialize the start time
                requests_start = time.time()
            elif time.time() - requests_start >= request_duration:
                # reset the start time
                requests_start = time.time()
                num_requests = 0

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
            elif sType.status == "PREMIUM":
                logger.print(f"(Not Whitelisted) Premium: {server['ip']}")
                databaseLib.update_one(
                    {"_id": server["_id"]}, {"$set": {"whitelist": False}}
                )
            elif sType.status == "HONEY_POT":
                logger.print(f"(Fake server) Honey Pot: {server['ip']}")
                databaseLib.update_one(
                    {"_id": server["_id"]}, {"$set": {"whitelist": True}}
                )
            elif "INCOMPATIBLE" in sType.status:
                logger.print(f"(Incompatible) {server['ip']} ({sType.status})")
                databaseLib.update_one(
                    {"_id": server["_id"]}, {"$set": {"whitelist": None}}
                )
            elif sType.status == "CRACKED":
                logger.print(f"(Cracked) {server['ip']}")
                databaseLib.update_one(
                    {"_id": server["_id"]}, {"$set": {"whitelist": False}}
                )
            elif sType.status == "MODDED":
                logger.print(f"(Modded) {server['ip']}")
                databaseLib.update_one(
                    {"_id": server["_id"]}, {"$set": {"whitelist": None}}
                )
            else:
                databaseLib.update_one(
                    {"_id": server["_id"]}, {"$set": {"whitelist": None}}
                )
                continue

            num_requests += 1
    except KeyboardInterrupt:
        logger.print("Exiting...")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
