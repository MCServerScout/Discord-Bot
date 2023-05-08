"""This is the discord bot for the mongoDB server list
"""

import asyncio
import json
import re
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

# Setup
# ---------------------------------------------

client = pymongo.MongoClient(MONGO_URL, server_api=pymongo.server_api.ServerApi("1"))  # type: ignore
db = client["MCSS"]
col = db["scannedServers"]

utils = utils.Utils(
    col,
    debug=DEBUG,
    discord_webhook=DISCORD_WEBHOOK,
)
logger = utils.logger
databaseLib = utils.database
playerLib = utils.player
messageLib = utils.message
twitchLib = utils.twitch
textLib = utils.text
serverLib = utils.server

bot = interactions.Client(
    token=DISCORD_TOKEN,
    status=interactions.Status.IDLE,
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


# Commands
# ---------------------------------------------

"""example document in the database
{
    "ip": "127.0.0.1",
    "port": 25565,
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
    "online": 12345,
    "hasForgeData": true,
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
            name="online_players",
            description="The online players of the server",
            type=interactions.OptionType.INTEGER,
            required=False,
        ),
        SlashCommandOption(
            name="logged_players",
            description="The logged players of the server",
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
            description="The description of the server, via regex, the default is \".*<your search>.*\"",
            type=interactions.OptionType.STRING,
            required=False,
        ),
        SlashCommandOption(
            name="cracked",
            description="If the server is cracked",
            type=interactions.OptionType.BOOLEAN,
            required=False,
        ),
        SlashCommandOption(
            name="has_favicon",
            description="If the server has a favicon",
            type=interactions.OptionType.BOOLEAN,
            required=False,
        )
    ],
)
async def find(
        ctx: interactions.SlashContext,
        version: str = None,
        max_players: int = None,
        online_players: int = None,
        logged_players: int = None,
        player: str = None,
        sign: str = None,
        description: str = None,
        cracked: bool = None,
        has_favicon: bool = None,
):
    msg = None
    try:
        await ctx.defer()

        msg = await ctx.send(
            embed=messageLib.standardEmbed(
                title="Finding servers...",
                description="This may take a while",
                color=BLUE,
            ),
            components=messageLib.buttons()
        )

        # default pipeline
        pipeline = [{"$match": {"$and": []}}]

        # filter out servers that have max players less than zero
        pipeline[0]["$match"]["$and"].append({"players.max": {"$gt": 0}})
        # filter out servers that have more than 150k players online
        pipeline[0]["$match"]["$and"].append({"players.online": {"$lt": 150000}})

        if player is not None:
            if len(player) < 16:
                # get the uuid of the player
                uuid = playerLib.getUUID(player)
            else:
                uuid = player.replace("-", "")

            if uuid == "":
                await msg.edit(
                    embed=messageLib.standardEmbed(
                        title="Error",
                        description=f"Player `{player}` not a valid player",
                        color=RED,
                    ),
                    components=messageLib.buttons()
                )
                return
            else:
                msg = await msg.edit(
                    embed=messageLib.standardEmbed(
                        title="Finding servers...",
                        description="Looking for servers with " + player + " on them",
                        color=BLUE,
                    ),
                    components=messageLib.buttons()
                )

            # insert dashes every 8 characters
            uuid = uuid[0:8] + "-" + uuid[8:12] + "-" + uuid[12:16] + "-" + uuid[16:20] + "-" + uuid[20:32]

            pipeline[0]["$match"]["$and"].append(
                {"players.sample": {"$elemMatch": {"id": uuid}}}
            )

        if version is not None:
            if version.isnumeric() and '.' not in version:
                pipeline[0]["$match"]["$and"].append(
                    {"version.protocol": {"$regex": f"^{version}"}}
                )
            else:
                pipeline[0]["$match"]["$and"].append(
                    {"version.name": {"$regex": f".*{version}.*"}}
                )
        if max_players is not None:
            pipeline[0]["$match"]["$and"].append({"players.max": max_players})
        if online_players is not None:
            pipeline[0]["$match"]["$and"].append({"players.online": online_players})
        if sign is not None:
            pipeline[0]["$match"]["$and"].append(
                {"world.signs": {"$elemMatch": {"text": {"$regex": f".*{sign}.*"}}}}
            )
        if description is not None:
            description = description.replace("'", ".")

            # validate that the description is a valid regex
            try:
                re.compile(description)
            except re.error:
                await msg.edit(
                    embed=messageLib.standardEmbed(
                        title="Error",
                        description=f"Description `{description}` not a valid regex",
                        color=RED,
                    ),
                    components=messageLib.buttons()
                )
                return

            # case-insensitive regex, search through desc.text and through desc.extra.text
            pipeline[0]["$match"]["$and"].append(
                {
                    "$or": [
                        {"description.text": {"$regex": f".*{description}.*", "$options": "i"}},
                        {
                            "description.extra.text": {
                                "$regex": f".*{description}.*",
                                "$options": "i",
                            }
                        },
                    ]
                }
            )
        if has_favicon is not None:
            pipeline[0]["$match"]["$and"].append({"hasFavicon": has_favicon})
        if logged_players is not None:
            # match to the length of players.sample
            pipeline[0]["$match"]["$and"].append(
                {"players.sample": {"$size": logged_players}}
            )

        total = databaseLib.count(pipeline)

        if total == 0:
            await msg.edit(
                embed=messageLib.standardEmbed(
                    title="No servers found",
                    description="Try again with different parameters",
                    color=RED,
                ),
                components=messageLib.buttons(),
            )
            return

        # check how many servers match
        msg = await msg.edit(
            embed=messageLib.standardEmbed(
                title="Finding servers...",
                description=f"Found {total} servers",
                color=BLUE,
            ),
            components=messageLib.buttons(),
        )

        index = 0

        stuff = messageLib.embed(
            pipeline=pipeline,
            index=index,
        )

        if stuff is None:
            logger.error("Stuff is None")
            await msg.edit(
                embed=messageLib.standardEmbed(
                    title="No servers found",
                    description="Try again with different parameters",
                    color=RED,
                ),
                components=messageLib.buttons(),
            )
            return

        embed = stuff["embed"]
        comps = stuff["components"]

        await msg.edit(
            embed=embed,
            components=comps,
            file=interactions.File(file="favicon.png", file_name="favicon.png"),
        )
    except Exception as err:
        if "403|Forbidden" in str(err):
            await ctx.delete(
                message=msg
            )
            return
        else:
            logger.error(f"[main.find] {err}")
            logger.print(f"[main.find] {traceback.format_exc()}")
            await ctx.send(
                embed=messageLib.standardEmbed(
                    title="An error occurred",
                    description="Please try again later",
                    color=RED,
                ),
            )


# button to get the next page of servers
@interactions.component_callback("next")
async def next_page(ctx: interactions.ComponentContext):
    msg = None
    try:
        orgFoot = ctx.message.embeds[0].footer.text
        await ctx.defer(edit_origin=True)

        logger.print(f"[main.previous_page] previous page called")

        msg = await ctx.edit_origin(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description="Loading...",
                color=BLUE,
            ),
            components=messageLib.buttons(),
        )

        # get the pipeline and index from the message
        pipeline = json.loads(orgFoot.split(" servers in: ")[1].replace("'", '"'))
        index = int(orgFoot.split("Showing ")[1].split(" of ")[0]) - 1
        total = databaseLib.count(pipeline)
        if index + 1 >= total:
            index = 0
        else:
            index += 1

        msg = await msg.edit(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description=f"Loading server {index + 1} of {total}",
                color=BLUE,
            ),
            components=messageLib.buttons(),
        )

        stuff = messageLib.embed(
            pipeline=pipeline,
            index=index,
        )

        if stuff is None:
            await msg.edit(
                embed=messageLib.standardEmbed(
                    title="No servers found",
                    description="Try again with different parameters",
                    color=RED,
                ),
                components=messageLib.buttons(),
            )
            return

        embed = stuff["embed"]
        comps = stuff["components"]

        await msg.edit(
            embed=embed,
            components=comps,
            file=interactions.File(file="favicon.png", file_name="favicon.png"),
        )
    except Exception as err:
        if "403|Forbidden" in str(err):
            await ctx.delete(
                message=msg
            )
            return

        logger.error(f"[main.next_page] {err}")
        logger.print(f"[main.next_page] Full traceback: {traceback.format_exc()}")

        await ctx.send(
            embed=messageLib.standardEmbed(
                title="Error",
                description="An error occurred while trying to get the next page of servers",
                color=RED,
            ),
            ephemeral=True,
        )


# button to get the previous page of servers
@interactions.component_callback("previous")
async def previous_page(ctx: interactions.ComponentContext):
    msg = None
    try:
        orgFoot = ctx.message.embeds[0].footer.text
        await ctx.defer(edit_origin=True)

        logger.print(f"[main.previous_page] previous page called")

        msg = await ctx.edit_origin(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description="Loading...",
                color=BLUE,
            ),
            components=messageLib.buttons(),
        )

        # get the pipeline and index from the message
        pipeline = json.loads(orgFoot.split(" servers in: ")[1].replace("'", '"'))
        index = int(orgFoot.split("Showing ")[1].split(" of ")[0]) - 1
        total = databaseLib.count(pipeline)
        if index - 1 >= 0:
            index -= 1
        else:
            index = total - 1

        msg = await msg.edit(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description=f"Loading server {index + 1} of {total}",
                color=BLUE,
            ),
            components=messageLib.buttons(),
        )

        stuff = messageLib.embed(
            pipeline=pipeline,
            index=index,
        )

        if stuff is None:
            await msg.edit(
                embed=messageLib.standardEmbed(
                    title="No servers found",
                    description="Try again with different parameters",
                    color=RED,
                ),
                components=messageLib.buttons(),
            )
            return

        embed = stuff["embed"]
        comps = stuff["components"]

        await msg.edit(
            embed=embed,
            components=comps,
            file=interactions.File(file="favicon.png", file_name="favicon.png"),
        )
    except Exception as err:
        if "403|Forbidden" in str(err):
            await ctx.delete(
                message=msg
            )
            return

        logger.error(f"[main.previous_page] {err}")
        logger.print(f"[main.previous_page] Full traceback: {traceback.format_exc()}")

        await ctx.send(
            embed=messageLib.standardEmbed(
                title="Error",
                description="An error occurred while trying to get the previous page of servers",
                color=RED,
            ),
            ephemeral=True,
        )


# button to send the players that are online
@interactions.component_callback("players")
async def players(ctx: interactions.ComponentContext):
    try:
        org = ctx.message
        orgFoot = org.embeds[0].footer.text
        await ctx.defer(ephemeral=True)

        logger.print(f"[main.players] players called")

        # get the host dict from the db
        pipeline = json.loads(orgFoot.split(" servers in: ")[1].replace("'", '"'))
        index = int(orgFoot.split("Showing ")[1].split(" of ")[0]) - 1

        host = databaseLib.get_doc_at_index(pipeline, index)

        player_list = playerLib.playerList(host["ip"], host["port"])

        if player_list is None:
            await ctx.send(
                embed=messageLib.standardEmbed(
                    title="Error",
                    description="An error occurred while trying to get the players (server offline?)",
                    color=RED,
                ),
                ephemeral=True,
            )
            return

        logger.print(f"[main.players] Found {len(player_list)} players")

        embed = messageLib.standardEmbed(
            title=f"Players on {host['ip']}",
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

        await ctx.send(
            embed=embed,
            ephemeral=True,
        )
    except Exception as err:
        if "403|Forbidden" in str(err):
            await ctx.send(
                embed=messageLib.standardEmbed(
                    title="An error occurred",
                    description="Wrong channel for this bot",
                    color=RED,
                ),
                ephemeral=True,
            )
            return

        logger.error(f"[main.players] {err}")
        logger.print(f"[main.players] Full traceback: {traceback.format_exc()}")

        await ctx.send(
            embed=messageLib.standardEmbed(
                title="Error",
                description="An error occurred while trying to get the players",
                color=RED,
            ),
            ephemeral=True,
        )


# button to jump to a specific index
@interactions.component_callback("jump")
async def jump(ctx: interactions.ComponentContext):
    original = None
    # when pressed should spawn a modal with a text input and then edit the message with the new index
    try:
        original = ctx.message

        logger.print(f"[main.jump] jump called")

        # get the pipeline and index from the message
        pipeline = json.loads(original.embeds[0].footer.text.split(" servers in: ")[1].replace("'", '"'))

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
            if index < 1 or index > total or not str(index).isnumeric():
                logger.warning(f"[main.jump] Invalid index: {index}")
                await ctx.send(
                    embed=messageLib.standardEmbed(
                        title="Error",
                        description=f"Invalid index, must be between 1 and {total}",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return
            else:
                await modal_ctx.send(
                    embed=messageLib.standardEmbed(
                        title="Success",
                        description=f"Jumping to index {index}",
                        color=GREEN,
                    ),
                    ephemeral=True,
                )

            # get the new embed
            stuff = messageLib.embed(
                pipeline=pipeline,
                index=index - 1,
            )

            # edit the message
            await original.edit(
                embed=stuff["embed"],
                components=stuff["components"],
                file=interactions.File(file="favicon.png", file_name="favicon.png"),
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
    except Exception as err:
        if "403|Forbidden" in str(err):
            await ctx.delete(
                message=original,
            )
            return

        logger.error(f"[main.jump] {err}")
        logger.print(f"[main.jump] Full traceback: {traceback.format_exc()}")
        await ctx.send(
            embed=messageLib.standardEmbed(
                title="Error",
                description="An error occurred while trying to jump to a specific index",
                color=RED,
            ),
            ephemeral=True,
        )


# button to change the sort method
@interactions.component_callback("sort")
async def sort(ctx: interactions.ComponentContext):
    try:
        org = ctx.message
        orgFooter = org.embeds[0].footer

        logger.print(f"[main.sort] sort called")

        # get the pipeline
        pipelineCP = json.loads(orgFooter.text.split(" servers in: ")[1].replace("'", '"'))
        logger.print(f"[main.sort] pipeline: {pipelineCP}")
        pipeline = pipelineCP.copy()

        # send a message with a string menu that express after 60s
        stringMenu = interactions.StringSelectMenu(
            interactions.StringSelectOption(
                label="Player Count",
                value="players",
            ),
            interactions.StringSelectOption(
                label="Player Limit",
                value="limit",
            ),
            interactions.StringSelectOption(
                label="Server Version ID",
                value="version",
            ),
            interactions.StringSelectOption(
                label="Random",
                value="random",
            ),
            placeholder="Sort the servers by...",
            custom_id="sort",
            min_values=1,
            max_values=1,
            disabled=False,
        )

        await ctx.send(
            embed=messageLib.standardEmbed(
                title="Sort",
                description="Sort the servers by...",
                color=BLUE,
            ),
            components=[
                interactions.ActionRow(
                    stringMenu,
                ),
            ],
            ephemeral=True,
        )

        try:
            # wait for the response
            menu = await ctx.bot.wait_for_component(timeout=60, components=stringMenu)
        except asyncio.TimeoutError:
            await ctx.send(
                embed=messageLib.standardEmbed(
                    title="Error",
                    description="Timed out",
                    color=RED,
                ),
                ephemeral=True,
            )
            return
        else:
            # get the value
            value = menu.ctx.values[0]
            logger.print(f"[main.sort] sort method: {value}")
            sortMethod = {}

            match value:
                case "players":
                    sortMethod = {"$sort": {"players.online": -1}}
                case "limit":
                    sortMethod = {"$sort": {"players.max": -1}}
                case "version":
                    sortMethod = {"$sort": {"version": -1}}
                case "random":
                    sortMethod = {"$sample": {"size": 1000}}
                case _:
                    await ctx.send(
                        embed=messageLib.standardEmbed(
                            title="Error",
                            description="Invalid sort method",
                            color=RED,
                        ),
                        ephemeral=True,
                    )

            # loop through the pipeline and replace the sort method
            for i in range(len(pipeline)):
                if "$sort" in pipeline[i] or "$sample" in pipeline[i]:
                    pipeline[i] = sortMethod
                    break
            else:
                pipeline.append(sortMethod)

            # loop through the pipeline and remove the limit
            for i in range(len(pipeline)):
                if "$limit" in pipeline[i]:
                    pipeline.pop(i)
                    break

            # limit to 1k servers
            pipeline.append({"$limit": 1000})

            # get the new embed
            stuff = messageLib.embed(
                pipeline=pipeline,
                index=0,
            )

            # edit the message
            await org.edit(
                embed=stuff["embed"],
                components=stuff["components"],
                file=interactions.File(file="favicon.png", file_name="favicon.png"),
            )

            await ctx.send(
                embed=messageLib.standardEmbed(
                    title="Success",
                    description="Sorted the servers",
                    color=GREEN,
                ),
                ephemeral=True,
            )
    except AttributeError:
        logger.print(f"[main.sort] AttributeError")
    except Exception as err:
        if "403|Forbidden" in str(err):
            await ctx.send(
                embed=messageLib.standardEmbed(
                    title="An error occurred",
                    description="Wrong channel for this bot",
                    color=RED,
                ),
                ephemeral=True,
            )
            return
        logger.error(f"[main.sort] {err}")
        logger.print(f"[main.sort] Full traceback: {traceback.format_exc()}")
        await ctx.send(
            embed=messageLib.standardEmbed(
                title="Error",
                description="An error occurred while trying to sort the servers",
                color=RED,
            ),
            ephemeral=True,
        )


# button to update the message
@interactions.component_callback("update")
async def update(ctx: interactions.ComponentContext):
    try:
        orgFoot = ctx.message.embeds[0].footer.text
        await ctx.defer(edit_origin=True)

        logger.print(f"[main.update] update page called")

        msg = await ctx.edit_origin(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description="Loading...",
                color=BLUE,
            ),
            components=messageLib.buttons(),
        )

        # get the pipeline and index from the message
        pipeline = json.loads(orgFoot.split(" servers in: ")[1].replace("'", '"'))
        index = int(orgFoot.split("Showing ")[1].split(" of ")[0]) - 1
        total = databaseLib.count(pipeline)

        msg = await msg.edit(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description=f"Loading server {index + 1} of {total}",
                color=BLUE,
            ),
            components=messageLib.buttons(),
        )

        stuff = messageLib.embed(
            pipeline=pipeline,
            index=index,
        )

        if stuff is None:
            await msg.edit(
                embed=messageLib.standardEmbed(
                    title="No servers found",
                    description="Try again with different parameters",
                    color=RED,
                ),
                components=messageLib.buttons(),
            )
            return

        embed = stuff["embed"]
        comps = stuff["components"]

        await msg.edit(
            embed=embed,
            components=comps,
            file=interactions.File(file="favicon.png", file_name="favicon.png"),
        )
    except Exception as err:
        if "403|Forbidden" in str(err):
            await ctx.send(
                embed=messageLib.standardEmbed(
                    title="An error occurred",
                    description="Wrong channel for this bot",
                    color=RED,
                ),
                ephemeral=True,
            )
            return

        logger.error(f"[main.update] {err}")
        logger.print(f"[main.update] Full traceback: {traceback.format_exc()}")

        await ctx.send(
            embed=messageLib.standardEmbed(
                title="Error",
                description="An error occurred while trying to update the message",
                color=RED,
            ),
            ephemeral=True,
        )


# other commands
# -----------------------------------------------------------------------------


# command to ping a single server
@slash_command(
    name="ping",
    description="Ping a single server",
    options=[
        SlashCommandOption(
            name="ip",
            description="The IPv4 address or hostname of the server",
            type=interactions.OptionType.STRING,
            required=True,
        ),
        SlashCommandOption(
            name="port",
            description="The port of the server",
            type=interactions.OptionType.INTEGER,
            required=False,
            min_value=1,
            max_value=65535,
        ),
    ],
)
async def ping(ctx: interactions.SlashContext, ip: str, port: int = None):
    try:
        await ctx.send(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description="Loading...",
                color=BLUE,
            ),
            ephemeral=True,
        )

        port = port if port is not None else 25565

        # check if the server is in the database
        pipeline = [
            {
                "$match": {
                    "ip": ip,
                    "port": port,
                }
            },
            {"$limit": 1},
        ]

        count = databaseLib.count(pipeline)

        if count == 0:
            logger.print(f"[main.ping] Server not in database")
            status = serverLib.status(ip, port)
            if status is None:
                logger.print(f"[main.ping] Server not found")
                await ctx.send(
                    embed=messageLib.standardEmbed(
                        title="Error",
                        description="Server not found",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return

            status["cracked"] = serverLib.join(ip, port, ) == "CRACKED"

            if "hasForgeData" not in status:
                status["hasForgeData"] = False

            status["ip"] = ip
            status["port"] = port
            status["lastSeen"] = int(time.time())

            logger.print(f"[main.ping] Got info from server: {type(status)}")

            pipeline = status

        # get the server
        stuff = messageLib.embed(
            pipeline=pipeline,
            index=0,
        )

        if stuff is None:
            logger.print(f"[main.ping] Server not in database")
            await ctx.send(
                embed=messageLib.standardEmbed(
                    title="Error",
                    description="Server not in database",
                    color=RED,
                ),
                ephemeral=True,
            )
            return

        embed = stuff["embed"]
        comps = stuff["components"]

        await ctx.send(
            embed=embed,
            components=comps,
            file=interactions.File(file="favicon.png", file_name="favicon.png"),
            ephemeral=True,
        )
    except Exception as err:
        if "403|Forbidden" in str(err):
            await ctx.send(
                embed=messageLib.standardEmbed(
                    title="An error occurred",
                    description="Wrong channel for this bot",
                    color=RED,
                ),
                ephemeral=True,
            )
            return
        logger.error(f"[main.ping] {err}")
        logger.print(f"[main.ping] Full traceback: {traceback.format_exc()}")

        await ctx.send(
            embed=messageLib.standardEmbed(
                title="Error",
                description="An error occurred while trying to ping the server",
                color=RED,
            ),
            ephemeral=True,
        )


# command to get a list of streamers playing on a server in the database
@slash_command(
    name="streamers",
    description="Get a list of servers with streams on them",
)
async def streamers(ctx: interactions.SlashContext):
    try:
        await ctx.send(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description="Loading...",
                color=BLUE,
            ),
            ephemeral=True,
        )

        # spawn a modal asking for client id and secret
        clientId = interactions.ShortText(
            label="Client ID",
            placeholder="Client ID",
            custom_id="clientId",
            min_length=1,
            max_length=100,
        )
        clientSecret = interactions.ShortText(
            label="Client Secret",
            placeholder="Client Secret",
            custom_id="clientSecret",
            min_length=1,
            max_length=100,
        )

        modal = interactions.Modal(
            clientId, clientSecret,
            title="Auth",
        )

        await ctx.send_modal(modal)

        modal_ctx = ctx
        try:
            modal_ctx = await ctx.bot.wait_for_modal(timeout=90, modal=modal)
        except asyncio.TimeoutError:
            logger.print(f"[main.streamers] Timed out")
            await modal_ctx.send(
                embed=messageLib.standardEmbed(
                    title="Error",
                    description="Timed out",
                    color=RED,
                ),
                ephemeral=True,
            )
            return
        else:
            clientId = modal_ctx.responses["clientId"]
            clientSecret = modal_ctx.responses["clientSecret"]

            await modal_ctx.send(
                embed=messageLib.standardEmbed(
                    title="Success",
                    description="Got the client id and secret",
                    color=GREEN,
                ),
                ephemeral=True,
            )

            streams = twitchLib.getStreamers(
                client_id=clientId,
                client_secret=clientSecret,
            )

            if streams is None or streams == []:
                await ctx.send(
                    embed=messageLib.standardEmbed(
                        title="Error",
                        description="No streamers found",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return

            # streams is a list of data in the format of {"name": "username", "title": "title", "viewer_count": 0, "url": "url"}

            # sort streams by viewer_count
            streams = sorted(streams, key=lambda k: k["viewer_count"], reverse=True)

            uuids = []
            for stream in streams[:100]:
                uuid = playerLib.getUUID(stream["name"])
                if len(uuid) > 0:
                    # add dashes
                    uuid = f"{uuid[0:8]}-{uuid[8:12]}-{uuid[12:16]}-{uuid[16:20]}-{uuid[20:32]}"
                    uuids.append(uuid)

            # get the servers
            # by getting the servers with the streamers in sample
            pipeline = [
                {
                    "$match": {
                        "players.sample": {
                            "$elemMatch": {
                                "id": {
                                    "$in": uuids,
                                }
                            }
                        }
                    }
                },
                {"$limit": 10},
            ]

            total = databaseLib.count(pipeline)
            logger.print(f"[main.streamers] Got {total} servers")

            if total == 0:
                await ctx.send(
                    embed=messageLib.standardEmbed(
                        title="Error",
                        description="No servers found",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return

            stuff = messageLib.embed(
                pipeline=pipeline,
                index=0,
            )

            if stuff is None:
                await ctx.send(
                    embed=messageLib.standardEmbed(
                        title="Error",
                        description="No servers found",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return

            # send the embed
            await ctx.send(
                embed=stuff["embed"],
                components=stuff["components"],
                file=interactions.File(file="favicon.png", file_name="favicon.png"),
            )
    except Exception as err:
        if "403|Forbidden" in str(err):
            await ctx.send(
                embed=messageLib.standardEmbed(
                    title="An error occurred",
                    description="Wrong channel for this bot",
                    color=RED,
                ),
                ephemeral=True,
            )
            return

        logger.error(f"[main.streamers] {err}")
        logger.print(f"[main.streamers] Full traceback: {traceback.format_exc()}")
        await ctx.send(
            embed=messageLib.standardEmbed(
                title="Error",
                description="An error occurred while trying to get the streamers",
                color=RED,
            ),
            ephemeral=True,
        )
        return


# command to get stats about the server
@slash_command(
    name="stats",
    description="Get stats about the server",
)
async def stats(ctx: interactions.SlashContext):
    msg = None
    await ctx.defer()

    try:
        mainEmbed = messageLib.standardEmbed(
            title="Stats",
            description="General stats about the database",
            color=BLUE,
        )

        msg = await ctx.send(embed=mainEmbed, )

        # get the stats
        totalServers = databaseLib.col.count_documents({})

        mainEmbed.add_field(
            name="Total Servers",
            value=f"{totalServers:,}",
            inline=True,
        )
        msg = await msg.edit(embed=mainEmbed, )

        # get the total player count, ignoring servers with over 150k players and less than 1 player
        pipeline = [
            {"$match": {"players.online": {"$lt": 150000, "$gt": 0}}},
            {"$group": {"_id": None, "total": {"$sum": "$players.online"}}},
        ]
        totalPlayers = databaseLib.aggregate(pipeline)[0]["total"]

        mainEmbed.add_field(
            name="Total Players",
            value=f"{totalPlayers:,}",
            inline=True,
        )
        msg = await msg.edit(embed=mainEmbed, )

        # get the total number of players in players.sample
        pipeline = [
            {"$unwind": "$players.sample"},
            {"$group": {"_id": None, "total": {"$sum": 1}}},
        ]
        totalSamplePlayers = databaseLib.aggregate(pipeline)[0]["total"]

        mainEmbed.add_field(
            name="Total Logged Players",
            value=f"{totalSamplePlayers:,}",
            inline=True,
        )
        msg = await msg.edit(embed=mainEmbed, )

        # get the five most common server version names
        pipeline = [
            {"$match": {"version.name": {"$ne": None}}},
            {"$group": {"_id": "$version.name", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5},
        ]
        topFiveVersions = list(databaseLib.aggregate(pipeline))

        mainEmbed.add_field(
            name="Top Five Versions",
            value="```css\n" + "\n".join([
                f"{i['_id']}: {round(i['count'] / totalServers * 100, 2)}%"
                for i in topFiveVersions
            ]) + "\n```",
            inline=True,
        )
        msg = await msg.edit(embed=mainEmbed, )

        # get the five most common server version ids
        pipeline = [
            {"$match": {"version.protocol": {"$ne": None}}},
            {"$group": {"_id": "$version.protocol", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5},
        ]
        topFiveVersionIds = list(databaseLib.aggregate(pipeline))

        mainEmbed.add_field(
            name="Top Five Version IDs",
            value="```css\n" + "\n".join([
                f"{textLib.protocolStr(i['_id'])}: {round(i['count'] / totalServers * 100, 2)}%"
                for i in topFiveVersionIds
            ]) + "\n```",
            inline=True,
        )
        await msg.edit(embed=mainEmbed, )
    except Exception as err:
        if "403|Forbidden" in str(err):
            await ctx.delete(
                message=msg
            )
            return

        logger.error(f"[main.stats] {err}")
        logger.print(f"[main.stats] Full traceback: {traceback.format_exc()}")
        await ctx.send(
            embed=messageLib.standardEmbed(
                title="Error",
                description="An error occurred while trying to get stats",
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
        embed=messageLib.standardEmbed(
            title="Help",
            description="Help",
            color=BLUE,
        )
        .add_field(
            name="`/find`",
            value="Find a server by anything in the database",
            inline=False,
        )
        .add_field(
            name="`/ping`",
            value="Get info about a server",
            inline=False,
        )
        .add_field(
            name="`/streamers`",
            value="Get a list of servers with streams on them",
            inline=False,
        )
        .add_field(
            name="`/stats`",
            value="Get stats about the database",
            inline=False,
        )
        .add_field(
            name="`/help`",
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
    try:
        # start the bot
        bot.start()
    except KeyboardInterrupt:
        logger.print("[main] Keyboard interrupt, stopping bot")
        # stop the bot
        asyncio.run(bot.close())
    except Exception as e:
        # log the error
        logger.critical(f"[main] Error: {e}")
        time.sleep(5)
