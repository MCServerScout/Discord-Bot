"""This is the discord bot for the mongoDB server list
"""

import asyncio
import re
import sys
import time
import traceback

import aiohttp
import interactions
from interactions import slash_command, SlashCommandOption
from pymongo import MongoClient

import utils

DISCORD_WEBHOOK, DISCORD_TOKEN, MONGO_URL, db_name, col_name, client_id, client_secret, IP_INFO_TOKEN = "", "", "", "", "", "", "", ""
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

# test the db connection
try:
    client = MongoClient(MONGO_URL)
    db = client['MCSS' if db_name == "" else db_name]
    col = db["scannedServers" if col_name == "" else col_name]

    col.count_documents({})
except Exception as e:
    print("Error connecting to database")
    print(traceback.format_exc())
    sys.exit("Config error in privVars.py, please fix before rerunning")

utils = utils.Utils(
    col,
    debug=DEBUG,
    discord_webhook=DISCORD_WEBHOOK,
    client_id=client_id,
    client_secret=client_secret,
    info_token=IP_INFO_TOKEN,
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
        type=interactions.ActivityType.GAME,
        name="Sussing out servers",
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

# command to file by anything in the doc

@slash_command(
    name="find",
    description="Find a server by anything in the database",
    options=[
        SlashCommandOption(
            name="ip",
            description="The ip of the server or a subnet mask (ex:10.0.0.0/24)",
            type=interactions.OptionType.STRING,
            required=False,
        ),
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
            min_value=0,
        ),
        SlashCommandOption(
            name="online_players",
            description="The online players of the server",
            type=interactions.OptionType.STRING,
            required=False,
            min_length=1,
        ),
        SlashCommandOption(
            name="logged_players",
            description="The logged players of the server",
            type=interactions.OptionType.STRING,
            required=False,
            min_length=1,
        ),
        SlashCommandOption(
            name="player",
            description="The player on the server",
            type=interactions.OptionType.STRING,
            required=False,
            min_length=1,
        ),
        SlashCommandOption(
            name="sign",
            description="The text of a sign on the server",
            type=interactions.OptionType.STRING,
            required=False,
            min_length=1,
        ),
        SlashCommandOption(
            name="description",
            description="The description of the server, via regex, the default is \".*<your search>.*\"",
            type=interactions.OptionType.STRING,
            required=False,
            min_length=1,
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
        ip: str = None,
        version: str = None,
        max_players: int = None,
        online_players: str = None,
        logged_players: str = None,
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
                uuid = await playerLib.asyncGetUUID(player)
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
            if not online_players[1:].isnumeric():
                await msg.edit(
                    embed=messageLib.standardEmbed(
                        title="Error",
                        description=f"Online players `{online_players}` not a valid number",
                        color=RED,
                    ),
                    components=messageLib.buttons()
                )
                return
            if online_players.startswith(">"):
                online_players = {"$gt": int(online_players[1:])}
            elif online_players.startswith("<"):
                online_players = {"$lt": int(online_players[1:])}
            elif online_players.startswith("="):
                online_players = int(online_players[1:])
            elif online_players.isnumeric():
                online_players = int(online_players)
            else:
                await msg.edit(
                    embed=messageLib.standardEmbed(
                        title="Error",
                        description=f"Online players `{online_players}` not a valid number",
                        color=RED,
                    ),
                    components=messageLib.buttons()
                )
                return
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
            pipeline[0]["$match"]["$and"].append({"players.sample": {"$exists": True}})
            if not logged_players[1:].isnumeric():
                await msg.edit(
                    embed=messageLib.standardEmbed(
                        title="Error",
                        description=f"Logged players `{logged_players}` not a valid number",
                        color=RED,
                    ),
                    components=messageLib.buttons()
                )
                return
            if logged_players.startswith(">"):
                pipeline[0]["$match"]["$and"].append(
                    {f"players.sample.{int(logged_players[1:]) + 1}": {"$exists": True}}
                )
            elif logged_players.startswith("<"):
                pipeline[0]["$match"]["$and"].append(
                    {f"players.sample.{int(logged_players[1:]) - 1}": {"$exists": True}}
                )
            elif logged_players.startswith("="):
                pipeline[0]["$match"]["$and"].append(
                    {"players.sample": {"$size": int(logged_players[1:])}}
                )
            elif logged_players.isnumeric():
                pipeline[0]["$match"]["$and"].append(
                    {"players.sample.length": int(logged_players)}
                )
            else:
                await msg.edit(
                    embed=messageLib.standardEmbed(
                        title="Error",
                        description=f"Logged players `{logged_players}` not a valid number",
                        color=RED,
                    ),
                    components=messageLib.buttons()
                )
                return
        if cracked is not None:
            pipeline[0]["$match"]["$and"].append({"cracked": cracked})
        if ip is not None:
            # test if the ip is a valid subnet mask like 10.0.0.0/24

            if "/" in ip:
                mask = ip.split("/")[1]
                ip = ip.split("/")[0]
                if mask.isnumeric():
                    ip = ip.split(".")
                    match mask:
                        case "8":
                            exp = f"{ip[0]}\.{ip[1]}\.{ip[2]}\.\d+"
                        case "16":
                            exp = f"{ip[0]}\.{ip[1]}\.\d+\.\d+"
                        case "24":
                            exp = f"{ip[0]}\.\d+\.\d+\.\d+"
                        case "32":
                            exp = f"{ip[0]}\.{ip[1]}\.{ip[2]}\.{ip[3]}"
                        case _:
                            await msg.edit(
                                embed=messageLib.standardEmbed(
                                    title="Error",
                                    description=f"Mask `{mask}` not a valid mask",
                                    color=RED,
                                ),
                                components=messageLib.buttons()
                            )
                            return

                    pipeline[0]["$match"]["$and"].append(
                        {"ip": {"$regex": f"^{exp}$", "$options": "i"}}
                    )
                else:
                    await msg.edit(
                        embed=messageLib.standardEmbed(
                            title="Error",
                            description=f"Mask `{mask}` not a valid mask",
                            color=RED,
                        ),
                        components=messageLib.buttons()
                    )
                    return
            else:
                pipeline[0]["$match"]["$and"].append({"ip": {"$regex": f"^{ip}$", "$options": "i"}})

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

        await messageLib.asyncLoadServer(
            index=0,
            pipeline=pipeline,
            msg=msg,
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

        # get the files attached to the message
        files = ctx.message.attachments
        pipeline = []
        for file in files:
            if file.filename == "pipeline.ason":
                url = file.url
                async with aiohttp.ClientSession() as session, session.get(url) as resp:
                    pipeline = await resp.text()
                pipeline = textLib.convert_string_to_json(pipeline)

        await ctx.defer(edit_origin=True)

        logger.print(f"[main.previous_page] next page called")

        msg = await ctx.edit_origin(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description="Loading...",
                color=BLUE,
            ),
            components=messageLib.buttons(),
            file=interactions.File(file="assets/loading.png", file_name="favicon.png"),
        )

        # get the pipeline and index from the message
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
            file=None
        )

        await messageLib.asyncLoadServer(
            index=index,
            pipeline=pipeline,
            msg=msg,
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
        # get the files attached to the message
        files = ctx.message.attachments
        pipeline = []
        for file in files:
            if file.filename == "pipeline.ason":
                url = file.url
                async with aiohttp.ClientSession() as session, session.get(url) as resp:
                    pipeline = await resp.text()
                pipeline = textLib.convert_string_to_json(pipeline)
        await ctx.defer(edit_origin=True)

        logger.print(f"[main.previous_page] previous page called")

        msg = await ctx.edit_origin(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description="Loading...",
                color=BLUE,
            ),
            components=messageLib.buttons(),
            file=interactions.File(file="assets/loading.png", file_name="favicon.png"),
        )

        # get the pipeline and index from the message
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
            file=None
        )

        await messageLib.asyncLoadServer(
            index=index,
            pipeline=pipeline,
            msg=msg,
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
        # get the files attached to the message
        files = ctx.message.attachments
        pipeline = []
        for file in files:
            if file.filename == "pipeline.ason":
                url = file.url
                async with aiohttp.ClientSession() as session, session.get(url) as resp:
                    pipeline = await resp.text()
                pipeline = textLib.convert_string_to_json(pipeline)
        await ctx.defer(ephemeral=True)

        logger.print(f"[main.players] players called")

        # get the host dict from the db
        index = int(orgFoot.split("Showing ")[1].split(" of ")[0]) - 1

        host = databaseLib.get_doc_at_index(pipeline, index)

        player_list = await playerLib.asyncPlayerList(host["ip"], host["port"])

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
        # get the files attached to the message
        files = ctx.message.attachments
        pipeline = []
        for file in files:
            if file.filename == "pipeline.ason":
                url = file.url
                async with aiohttp.ClientSession() as session, session.get(url) as resp:
                    pipeline = await resp.text()
                pipeline = textLib.convert_string_to_json(pipeline)

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

            # edit the message
            await messageLib.asyncLoadServer(
                index=index - 1,
                pipeline=pipeline,
                msg=original,
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

        # get the files attached to the message
        files = ctx.message.attachments
        pipelineCP = []
        for file in files:
            if file.filename == "pipeline.ason":
                url = file.url
                async with aiohttp.ClientSession() as session, session.get(url) as resp:
                    pipeline = await resp.text()
                pipelineCP = textLib.convert_string_to_json(pipeline)

        logger.print(f"[main.sort] sort called")

        # get the pipeline
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
                label="Last scan",
                value="last_scan",
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
                case "last_scan":
                    sortMethod = {"$sort": {"lastSeen": -1}}
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

            # edit the message
            await messageLib.asyncLoadServer(
                index=0,
                pipeline=pipeline,
                msg=org,
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
        # get the files attached to the message
        files = ctx.message.attachments
        pipeline = []
        for file in files:
            if file.filename == "pipeline.ason":
                url = file.url
                async with aiohttp.ClientSession() as session, session.get(url) as resp:
                    pipeline = await resp.text()
                pipeline = textLib.convert_string_to_json(pipeline)
        await ctx.defer(edit_origin=True)

        logger.print(f"[main.update] update page called")

        msg = await ctx.edit_origin(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description="Loading...",
                color=BLUE,
            ),
            components=messageLib.buttons(),
            file=interactions.File(file="assets/loading.png", file_name="favicon.png"),
        )

        # get the pipeline and index from the message
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

        # load the server
        await messageLib.asyncLoadServer(
            index=index,
            pipeline=pipeline,
            msg=msg,
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
    msg = None
    try:
        port = port if port is not None else 25565

        pipeline = {
            "ip": ip,
            "port": port,
        }

        msg = await ctx.send(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description="Loading server 1 of 1",
                color=BLUE,
            ),
            components=messageLib.buttons(),
        )

        # get the server
        await messageLib.asyncLoadServer(
            index=0,
            pipeline=pipeline,
            msg=msg,
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
            await ctx.delete(
                message=msg,
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
    options=[
        SlashCommandOption(
            name="lang",
            description="The language of the stream",
            type=interactions.OptionType.STRING,
            required=False,
            min_length=2,
            max_length=2,
        ),
    ],
)
async def streamers(ctx: interactions.SlashContext, lang: str = None):
    try:
        msg = await ctx.send(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description="Loading...",
                color=BLUE,
            ),
        )

        global client_id, client_secret

        # test if 'client_id' and 'client_secret' are not None
        if client_id == "" or client_secret == "":
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
                client_id = modal_ctx.responses["clientId"]
                client_secret = modal_ctx.responses["clientSecret"]

            await modal_ctx.send(
                embed=messageLib.standardEmbed(
                    title="Success",
                    description="Got the client id and secret",
                    color=GREEN,
                ),
                ephemeral=True,
            )

        if (client_id == "" or client_secret == "") or (client_id is None or client_secret is None):
            await ctx.send(
                embed=messageLib.standardEmbed(
                    title="Error",
                    description="Client ID or Client Secret is empty",
                    color=RED,
                ),
                ephemeral=True,
            )
            return

        streams = await twitchLib.asyncGetStreamers(
            client_id=client_id,
            client_secret=client_secret,
            lang=lang,
        )

        if streams is None or streams == []:
            await msg.edit(
                embed=messageLib.standardEmbed(
                    title="Error",
                    description="No streams found",
                    color=RED,
                ),
            )
            return
        else:
            msg = await msg.edit(
                embed=messageLib.standardEmbed(
                    title="Loading...",
                    description="Found " + str(len(streams)) + " streams",
                    color=BLUE,
                ),
            )

        names = []
        for stream in streams:
            names.append(stream["user_name"])

        # get the servers
        # by case-insensitive name of streamer and players.sample is greater than 0
        pipeline = [
            {
                "$match": {
                    "$and": [
                        {
                            "players.sample.name": {
                                "$in": [re.compile(name, re.IGNORECASE) for name in names]
                            }
                        },
                        {"players.sample": {"$exists": True}},
                    ]
                }
            }
        ]

        total = databaseLib.count(pipeline)
        logger.debug(f"[main.streamers] Got {total} servers: {names}")
        msg = await msg.edit(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description="Found " + str(total) + " servers in the database",
                color=BLUE,
            ),
        )

        _ids = []
        for doc in databaseLib.aggregate(pipeline):
            _ids.append(doc["_id"])
        pipeline = [
            {
                "$match": {
                    "$and": [
                        {"_id": {"$in": _ids}},
                        {"players.sample": {"$exists": True}},
                    ]
                }
            }
        ]

        if total == 0:
            await msg.edit(
                embed=messageLib.standardEmbed(
                    title="Error",
                    description="No servers found",
                    color=RED,
                ),
            )
            return
        else:
            msg = await msg.edit(
                embed=messageLib.standardEmbed(
                    title="Loading...",
                    description="Loading 1 of " + str(total),
                    color=BLUE,
                ),
            )

        await messageLib.asyncLoadServer(
            pipeline=pipeline,
            index=0,
            msg=msg,
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
            value=f"{totalSamplePlayers:,} ({round(totalSamplePlayers / totalPlayers * 100, 2)}%)",
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
            value="Get info about a single server",
            inline=False,
        )
        .add_field(
            name="`/streamers`",
            value="... it's just stream sniping, but now with language support",
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
    logger.critical(f"[main.on_ready] Logged in as {user.username}#{user.discriminator}")


# -----------------------------------------------------------------------------
# bot apps


# -----------------------------------------------------------------------------
# bot loop

if __name__ == "__main__":
    """Main loop for the bot
    
    This is the main loop for the bot. It will restart the bot if the websocket closes.
    """

    try:
        bot.start()
    except KeyboardInterrupt:
        logger.print("[main] Keyboard interrupt, stopping bot")
        asyncio.run(bot.close())
    except Exception as e:
        if "Error: The Websocket closed with code: 1000" in str(e):
            logger.print("[main] Websocket closed, restarting bot")

            time.sleep(5)
            asyncio.run(bot.close())
        else:
            logger.critical(f"[main] {e}")
            logger.print("[main] Stopping bot")
            asyncio.run(bot.close())
