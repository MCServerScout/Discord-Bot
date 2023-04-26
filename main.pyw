"""This is the discord bot for the mongoDB server list
"""

import asyncio
import datetime
import json
import sys
import time
import traceback

import interactions
import pymongo
from interactions import slash_command, SlashCommandOption

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
    print("Please add your mongo url to 'privVars.py'")
    sys.exit("Config error in privVars.py, please fix before rerunning")
if DISCORD_TOKEN == "":
    print("Please add your bot token to 'privVars.py'")
    sys.exit("Config error in privVars.py, please fix before rerunning")
if DISCORD_WEBHOOK == "":
    print("Please add your discord webhook to 'privVars.py'")
    sys.exit("Config error in privVars.py, please fix before rerunning")

# Setup
# ---------------------------------------------

client = pymongo.MongoClient(MONGO_URL, server_api=pymongo.server_api.ServerApi("1"))  # type: ignore
db = client["mc"]
col = db["servers"]

utils = utils.Utils(
    col,
    debug=DEBUG,
    discord_webhook=DISCORD_WEBHOOK,
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
        type=interactions.ActivityType.GAME, name="Trolling the masses"
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


def time_now() -> "Timestamp":  # type: ignore
    # return local time
    return datetime.datetime.now(
        datetime.timezone(
            datetime.timedelta(hours=0)  # no clue why this is needed, but it works now?
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
        SlashCommandOption(
            name="version",
            description="The version of the server",
            type=interactions.OptionType.STRING,
            required=False,
        ),
        SlashCommandOption(
            name="max_players",
            description="The max players of the server",
            type=interactions.OptionType.INTEGER,
            required=False,
        ),
        SlashCommandOption(
            name="player",
            description="The player on the server",
            type=interactions.OptionType.STRING,
            required=False,
        ),
        SlashCommandOption(
            name="sign",
            description="The text of a sign on the server",
            type=interactions.OptionType.STRING,
            required=False,
        ),
        SlashCommandOption(
            name="description",
            description="The description of the server",
            type=interactions.OptionType.STRING,
            required=False,
        ),
        SlashCommandOption(
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

    # print out the parameters that were passed
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
            timestamp=time_now(),
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

    total = databaseLib.count(pipeline)

    if total == 0:
        await msg.edit(
            embed=messageLib.standardEmbed(
                title="No servers found",
                description="Try again with different parameters",
                color=RED,
            ),
            components=messageLib.buttons(True, True, True, True),
        )
        return

    # check how many servers match
    msg = await msg.edit(
        embed=messageLib.standardEmbed(
            title="Finding servers...",
            description=f"Found {total} servers",
            color=BLUE,
        ),
        components=messageLib.buttons(True, True, True, True),
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


# command to get the next page of servers
@interactions.component_callback("next")
async def next_page(ctx: interactions.ComponentContext):
    try:
        org = ctx.message
        await ctx.defer(edit_origin=True)

        logger.print(f"[main.next_page] next page called by {ctx.author}")

        msg = await ctx.edit_origin(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description="Loading the next server",
                color=BLUE,
            ),
            components=messageLib.buttons(True, True, True),
        )

        # get the pipeline and index from the message
        pipeline = org.embeds[0].footer.text.split(" servers in: ")[1]
        pipeline = json.loads(pipeline)

        index = int(org.embeds[0].footer.text.split(" servers in: ")[0].split(" ")[-1])

        total = databaseLib.count(pipeline)

        msg = await msg.edit(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description=f"Loading server {org.embeds[0].title[2:]} of {total}",
                color=BLUE,
            ),
            components=messageLib.buttons(True, True, True),
        )

        if index + 1 < total:
            index += 1
        else:
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
    except Exception:
        logger.error(f"[main.next_page] {traceback.format_exc()}")

        await ctx.edit_origin(
            embed=messageLib.standardEmbed(
                title="Error",
                description="An error occurred while trying to get the next page of servers",
                color=RED,
            )
        )


# command to get the previous page of servers
@interactions.component_callback("previous")
async def previous_page(ctx: interactions.ComponentContext):
    try:
        org = ctx.message
        await ctx.defer(edit_origin=True)

        logger.print(f"[main.previous_page] previous page called by {ctx.author}")

        msg = await ctx.edit_origin(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description="Loading the previous server",
                color=BLUE,
            ),
            components=messageLib.buttons(True, True, True),
        )

        # get the pipeline and index from the message
        pipeline = org.embeds[0].footer.text.split(" servers in: ")[1]
        pipeline = json.loads(pipeline)

        index = int(org.embeds[0].footer.text.split(" servers in: ")[0].split(" ")[-1])

        total = databaseLib.count(pipeline)

        msg = await msg.edit(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description=f"Loading server {org.embeds[0].title[2:]} of {total}",
                color=BLUE,
            ),
            components=messageLib.buttons(True, True, True),
        )

        if index - 1 >= 0:
            index -= 1
        else:
            index = total - 1

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
    except Exception:
        logger.error(f"[main.previous_page] {traceback.format_exc()}")

        await ctx.edit_origin(
            embed=messageLib.standardEmbed(
                title="Error",
                description="An error occurred while trying to get the previous page of servers",
                color=RED,
            )
        )


# command to send the players that are online
@interactions.component_callback("players")
async def players(ctx: interactions.ComponentContext):
    try:
        await ctx.defer(ephemeral=True)

        logger.print(f"[main.players] players called by {ctx.author}")

        org = ctx.message

        # get the host dict from the db
        pipeline = json.loads(org.embeds[0].footer.text.split(" servers in: ")[1])
        index = int(org.embeds[0].footer.text.split(" servers in: ")[0].split(" ")[-1])

        host = databaseLib.get_doc_at_index(pipeline, index)["host"]

        player_list = await playerLib.playerList(host)

        if player_list is None:
            await ctx.send(
                embed=messageLib.standardEmbed(
                    title="Error",
                    description="An error occurred while trying to get the players",
                    color=RED,
                ),
                ephemeral=True,
            )
            return

        embed = messageLib.standardEmbed(
            title=f"Players on {host}",
            description=f"Found {len(player_list)} players",
            color=BLUE,
        )
        for player in player_list:
            online = "🟢" if player["online"] else "🔴"
            embed.add_field(
                name=f'{online} `{player["name"]}`',
                value=f'`{player["id"]}`',
                inline=False,
            )
    except Exception:
        logger.error(f"[main.players] {traceback.format_exc()}")

        await ctx.send(
            embed=messageLib.standardEmbed(
                title="Error",
                description="An error occurred while trying to get the players",
                color=RED,
            ),
            ephemeral=True,
        )


# command to jump to a specific index
@interactions.component_callback("jump")
async def jump(ctx: interactions.ComponentContext):
    # when pressed should spawn a modal with a text input and then edit the message with the new index
    try:
        original = ctx.message

        await ctx.defer(ephemeral=True)

        logger.print(f"[main.jump] jump called by {ctx.author}")

        org = ctx.message

        # get the pipeline and index from the message
        pipeline = json.loads(org.embeds[0].footer.text.split(" servers in: ")[1])
        index = int(org.embeds[0].footer.text.split(" servers in: ")[0].split(" ")[-1])

        # get the total number of servers
        total = databaseLib.count(pipeline)

        # create the text input
        text_input = interactions.ShortText(
            label="Jump to index",
            placeholder=f"Enter a number between 1 and {total}",
            min_length=1,
            max_length=len(str(total)),
            custom_id="jump",
            required=True,
        )

        # create a modal
        modal = interactions.Modal(
            text_input,
            title="Jump",
        )

        # send the modal
        await ctx.send_modal(modal)

        try:
            # wait for the response
            modal_ctx = await ctx.bot.wait_for_modal(modal=modal, timeout=60)

            # get the response
            index = int(modal_ctx.responses["jump"])

            # check if the index is valid
            if index < 1 or index > total:
                await ctx.send(
                    embed=messageLib.standardEmbed(
                        title="Error",
                        description=f"Invalid index, must be between 1 and {total}",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return

            # get the original pipeline
            pipeline = json.loads(original.embeds[0].footer.text.split(" servers in: ")[1])

            # get the new embed
            stuff = messageLib.embed(
                pipeline=pipeline,
                index=index - 1,
            )

            # edit the message
            await original.edit(
                embed=stuff["embed"],
                components=stuff["components"],
            )
        except asyncio.TimeoutError:
            await ctx.send(
                embed=messageLib.standardEmbed(
                    title="Error",
                    description="Timed out",
                    color=RED,
                ),
                ephemeral=True,
            )
    except Exception:
        logger.error(f"[main.jump] {traceback.format_exc()}")
        await ctx.send(
            embed=messageLib.standardEmbed(
                title="Error",
                description="An error occurred while trying to jump to a specific index",
                color=RED,
            ),
            ephemeral=True,
        )


# general help
@slash_command(
    name="help",
    description="Get help",
)
async def help_command(ctx: interactions.SlashContext):
    await ctx.send(
        embed=interactions.Embed(
            title="Help",
            description="Help",
            color=BLUE,
            timestamp=time_now(),
        )
        .add_field(
            name="find",
            value="Find a server by anything in the database",
            inline=False,
        )
        .add_field(
            name="help",
            value="Get help",
            inline=False,
        ),
        ephemeral=True,
    )


# -----------------------------------------------------------------------------
# bot events

@interactions.listen()
async def on_ready():
    user = await bot.fetch_user(bot.user.id)
    logger.print(f"[main.on_ready] Logged in as {user.username}#{user.discriminator}")


# -----------------------------------------------------------------------------
# bot loop

# main
if __name__ == "__main__":
    while True:
        try:
            # start the bot
            bot.start()
        except KeyboardInterrupt:
            # stop the bot
            asyncio.run(bot.close())
            break
        except Exception as e:
            # log the error
            logger.critical(f"[main] Error: {e}")
            time.sleep(5)
