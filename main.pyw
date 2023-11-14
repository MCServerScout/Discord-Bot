# bin/python3

"""This is the discord bot for the mongoDB server list
"""

import asyncio
import sys
import time
import traceback

import sentry_sdk
from interactions import (
    listen,
    Intents,
    ActivityType,
    Status,
    Activity,
    Client,
)
from interactions.api.events import Ready, CommandCompletion, CommandError
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from sentry_sdk.integrations.aiohttp import AioHttpIntegration

import pyutils
from pyutils.scanner import Scanner

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
    upload_serv,
) = ["..." for _ in range(14)]

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

    units = {
        0: "",
        1: "K",
        2: "M",
        3: "B",
    }

    num_docs = "{:.3g}".format(num_docs).split("e+")

    if len(num_docs) == 1:
        num_docs = int(num_docs[0])
    else:
        power = int(num_docs[1])
        num_docs = float(num_docs[0]) * 10 ** (power % 3)
        num_docs = f"{num_docs}{units[power // 3]}"
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

bot = Client(
    token=DISCORD_TOKEN,
    status=Status.IDLE,
    activity=Activity(
        type=ActivityType.GAME,
        name="Trolling through {} servers".format(num_docs),
    ),
    logger=logger,
    intents=Intents.DEFAULT,
    disable_dm_commands=True,
    send_command_tracebacks=False,
)
bot.load_extension(
    "interactions.ext.sentry", token=SENTRY_TOKEN, dsn=SENTRY_URI
) if SENTRY_URI != "..." and SENTRY_TOKEN != "..." else None

RED = 0xFF0000  # error
GREEN = 0x00FF00  # success
YELLOW = 0xFFFF00  # warning
BLUE = 0x0000FF  # info
PINK = 0xFFC0CB  # offline


# Load extensions
exts = ["Apps", "Buttons", "Commands"]
kwargs = {
    "messageLib": messageLib,
    "playerLib": playerLib,
    "logger": logger,
    "databaseLib": databaseLib,
    "serverLib": serverLib,
    "twitchLib": twitchLib,
    "Scanner": Scanner,
    "textLib": textLib,
    "mcLib": mcLib,
    "cstats": cstats,
    "azure_client_id": azure_client_id,
    "azure_redirect_uri": azure_redirect_uri,
    "client_id": client_id,
    "client_secret": client_secret,
    "upload_serv": upload_serv,
}
for ext in exts:
    try:
        bot.load_extension("Extensions." + ext, None, **kwargs)
    except Exception as e:
        logger.critical(f"Failed to load extension {ext}")
        logger.critical(traceback.format_exc())
    else:
        logger.print(f"Loaded extension {ext}")
        sentry_sdk.add_breadcrumb(category="extensions", message=f"Loaded {ext}")

bot.load_extension("interactions.ext.dynhelp")


# -----------------------------------------------------------------------------
# bot events


@listen(Ready)
async def on_ready():
    user = await bot.fetch_user(bot.user.id)
    logger.hook(f"Logged in as {user.username}#{user.discriminator}")


@listen(CommandCompletion, disable_default_listeners=True)
async def on_command_completion(event):
    sentry_sdk.add_breadcrumb(
        category="command",
        message=f"Command {event.ctx.invoke_target} completed",
    )
    sentry_sdk.set_tag("command", event.ctx.invoke_target)


@listen(CommandError, disable_default_listeners=True)
async def on_command_error(event):
    filters = ["HTTPEXCEPTION", "403|Forbidden || Missing Access"]

    if any(fil in str(event.error) for fil in filters):
        # log at a lower level as to prevent log spam
        logger.error(event.error)
        await event.ctx.send(
            "An error occurred while running the command", ephemeral=True
        )
        return

    sentry_sdk.add_breadcrumb(
        category="command",
        message=f"Command {event.ctx.invoke_target} errored, with args {[arg for arg in event.ctx.kwargs]}",
    )
    sentry_sdk.set_tag("command", event.ctx.invoke_target)
    sentry_sdk.capture_exception(event.error)
    logger.critical(event.error)
    await event.ctx.send("An error occurred while running the command", ephemeral=True)


# -----------------------------------------------------------------------------
# bot loop

if __name__ == "__main__":
    """Main loop for the bot

    This is the main loop for the bot. It will restart the bot if the websocket closes.
    """

    try:
        bot.start()
    except KeyboardInterrupt:
        logger.print("Keyboard interrupt, stopping bot")
        asyncio.run(bot.close())
    except Exception as e:
        if "Error: The Websocket closed with code: 1000" in str(e):
            logger.print("Websocket closed, restarting bot")

            time.sleep(5)
            asyncio.run(bot.close())
        else:
            logger.debug(traceback.format_exc())
            logger.critical(e)
            logger.print("Stopping bot")
            asyncio.run(bot.close())
