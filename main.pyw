"""This is the discord bot for the mongoDB server list
"""
# pyright: basic, reportGeneralTypeIssues=false, reportOptionalSubscript=false, reportOptionalMemberAccess=false

import asyncio
import datetime
import sys

import interactions
import pymongo
import requests
from interactions import slash_command

import utils

DISCORD_WEBHOOK = ""
DISCORD_TOKEN = ""
MONGO_URL = ""
DEBUG = False
try:
    from privVars import *
except ImportError:
    MONGO_URL = ""
    TOKEN = "..."

if MONGO_URL == "":
    print("Please add your mongo url to privVars.py")
    input()
    sys.exit()
if DISCORD_TOKEN == "":
    print("Please add your bot token to privVars.py")
    input()
    sys.exit()
if DISCORD_WEBHOOK == "":
    print("Please add your discord webhook to privVars.py")
    input()
    sys.exit()

# Setup
# ---------------------------------------------

client = pymongo.MongoClient(MONGO_URL, server_api=pymongo.server_api.ServerApi("1"))  # type: ignore
db = client["mc"]
col = db["servers"]

utils = utils.utils(
    col,
    debug=DEBUG,
)
logger = utils.logger
databaseLib = utils.database
playerLib = utils.player
messageLib = utils.message

bot = interactions.Client(
    token=DISCORD_TOKEN,
    intents=interactions.Intents.GUILD_MESSAGES
    | interactions.Intents.GUILDS
    | interactions.Intents.GUILD_INTEGRATIONS,
    status=interactions.Status.ONLINE,
    activity=interactions.Activity(
        type=interactions.ActivityType.WATCHING, name="for servers"
    ),
    logger=logger,
)

RED = 0xFF0000  # error
GREEN = 0x00FF00  # success
YELLOW = 0xFFFF00  # warning
BLUE = 0x0000FF  # info
PINK = 0xFFC0CB  # offline


def print(*args, **kwargs):
    logger.print(" ".join(map(str, args)), **kwargs)


def timeNow():
    # return local time
    return datetime.datetime.now(
        datetime.timezone(
            datetime.timedelta(hours=0)  # no clue why this is needed but it works now?
        )
    ).strftime("%Y-%m-%d %H:%M:%S")


# Commands
# ---------------------------------------------

"""example document in the database
{
    "host": {
        "ip": "127.0.0.1",
        "hostname": "localhost",
        "port": 25565,
    }
    "version": {
        "name": "1.19.3",
        "protocol": 761
    },
    "players": {
        "max": 100,
        "online": 5,
        "sample": [
            {
                "name": "thinkofdeath",
                "id": "4566e69f-c907-48ee-8d71-d7ba5aa00d20"
            },
        ]
    },
    "world": {
        "signs": [
            {
                "pos": {0,0,0},
                "text": "Hello World!",
            },
        ]
    },
    "description": {
        "text": "Hello world!"
    },
    "favicon": "data:image/png;base64,<data>",
    "cracked": false,
    "oneline": Date(12345),
    "enforcesSecureChat": true
}
"""


# command to file by anything in the doc
@slash_command(
    name="find",
    description="Find a server by anything in the database",
    options=[
        interactions.Option(
            name="version",
            description="The version of the server",
            type=interactions.OptionType.STRING,
            required=False,
        ),
        interactions.Option(
            name="max_players",
            description="The max players of the server",
            type=interactions.OptionType.INTEGER,
            required=False,
        ),
        interactions.Option(
            name="player",
            description="The player on the server",
            type=interactions.OptionType.STRING,
            required=False,
        ),
        interactions.Option(
            name="sign",
            description="The text of a sign on the server",
            type=interactions.OptionType.STRING,
            required=False,
        ),
        interactions.Option(
            name="description",
            description="The description of the server",
            type=interactions.OptionType.STRING,
            required=False,
        ),
        interactions.Option(
            name="cracked",
            description="If the server is cracked",
            type=interactions.OptionType.BOOLEAN,
            required=False,
        ),
    ],
)
async def find(
    ctx: interactions.SlashContext,
    version: str = None,
    max_players: int = None,
    player: str = None,
    sign: str = None,
    description: str = None,
    cracked: bool = None,
):
    await ctx.defer()

    # print out the paramters that were passed
    print(
        f"find command called by {ctx.author} with parameters:",
        "version={version},",
        "max_players={max_players},",
        "player={player},",
        "sign={sign},",
        "description={description}",
        "cracked={cracked}",
    )

    logger.print(
        f"[main.find] find command called by {ctx.author} with parameters:",
        f"version={version},",
        f"max_players={max_players},",
        f"player={player},",
        f"sign={sign},",
        f"description={description}",
        f"cracked={cracked}",
    )

    msg = await ctx.send(
        embed=interactions.Embed(
            title="Finding servers...",
            description="This may take a while",
            color=BLUE,
            timestamp=timeNow(),
        ),
    )

    # default pipeline
    pipeline = [{"$match": {"$and": []}}]

    # filter out servers that have max players less than zero
    pipeline[0]["$match"]["$and"].append({"players.max": {"$gt": 0}})
    # filter out servers that have more than 150k players online
    pipeline[0]["$match"]["$and"].append({"players.online": {"$lt": 150000}})

    if player is not None:
        # get the uuid of the player
        uuid = playerLib.getUUID(player)

        pipeline[0]["$match"]["$and"].append(
            {"players.sample": {"$elemMatch": {"id": uuid}}}
        )

    if version is not None:
        if version.replace(".", "").isnumeric():
            pipeline[0]["$match"]["$and"].append(
                {"version.protocol": {"$regex": f"^{version}"}}
            )
        else:
            pipeline[0]["$match"]["$and"].append(
                {"version.name": {"$regex": f"^.*{version}.*"}}
            )
    if max_players is not None:
        pipeline[0]["$match"]["$and"].append({"players.max": max_players})
    if sign is not None:
        pipeline[0]["$match"]["$and"].append(
            {"world.signs": {"$elemMatch": {"text": {"$regex": f".*{sign}.*"}}}}
        )
    if description is not None:
        pipeline[0]["$match"]["$and"].append(
            {"description.text": {"$regex": f".*{description}.*"}}
        )
    if cracked is not None:
        pipeline[0]["$match"]["$and"].append({"cracked": cracked})

    # check how many servers match
    msg = await msg.edit(
        embed=interactions.Embed(
            title="Finding servers...",
            description=f"Found {databaseLib.countPipeline(pipeline)} servers",
            color=BLUE,
            timestamp=timeNow(),
        ),
    )

    index = 0

    stuff = messageLib.embed(
        pipeline=pipeline,
        index=index,
    )

    embed = stuff["embed"]
    comps = stuff["components"]

    await msg.edit(
        embed=embed,
        components=comps,
    )


# main
if __name__ == "__main__":
    while True:
        try:
            # start the bot
            bot.run()
        except KeyboardInterrupt:
            # stop the bot
            asyncio.run(bot.close())
            break
        except Exception as e:
            # log the error
            print(f"Error: {e}")
            logger.print(f"[main] Error: {e}")

            requests.post(
                DISCORD_WEBHOOK,
                json={
                    "content": f"Error: {e}",
                    "username": "Minecraft Server Finder",
                },
            )
