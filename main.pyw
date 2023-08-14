# bin/python3

"""This is the discord bot for the mongoDB server list
"""

import asyncio
import datetime
import json
import os
import re
import sys
import time
import traceback
from threading import Thread
from typing import Optional, Tuple

import aiohttp
import interactions
from interactions import SlashCommandOption, slash_command
from interactions.ext.paginators import Paginator
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

import pyutils

DISCORD_WEBHOOK, DISCORD_TOKEN, MONGO_URL, db_name, \
    col_name, client_id, client_secret, IP_INFO_TOKEN, \
    cstats, azure_client_id, azure_redirect_uri \
    = ["..." for _ in range(11)]

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

# test the db connection
print("Connecting to database...")
try:
    client = MongoClient(MONGO_URL)
    db = client['MCSS' if db_name == "..." else db_name]
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
)
logger = utils.logger
databaseLib = utils.database
playerLib = utils.player
messageLib = utils.message
twitchLib = utils.twitch
textLib = utils.text
serverLib = utils.server
mcLib = utils.mc

bot = interactions.Client(
    token=DISCORD_TOKEN,
    status=interactions.Status.IDLE,
    activity=interactions.Activity(
        type=interactions.ActivityType.GAME,
        name="Trolling through {} servers".format(num_docs),
    ),
    logger=logger,
    intents=interactions.Intents.DEFAULT,
    disable_dm_commands=True,
)

RED = 0xFF0000  # error
GREEN = 0x00FF00  # success
YELLOW = 0xFFFF00  # warning
BLUE = 0x0000FF  # info
PINK = 0xFFC0CB  # offline


async def get_pipe(msg: interactions.Message) -> Optional[Tuple[int, dict]]:
    # make sure it has an embed with at least one attachment and a footer
    if len(msg.embeds) == 0 or len(msg.attachments) == 0 or msg.embeds[0].footer is None:
        return None

    # grab the index
    index = int(msg.embeds[0].footer.text.split("Showing ")[1].split(" of ")[0]) - 1

    # grab the attachment
    for file in msg.attachments:
        if file.filename == "pipeline.ason":
            async with aiohttp.ClientSession() as session, session.get(file.url) as resp:
                pipeline = await resp.text()

            return index, (textLib.convert_string_to_json(pipeline) if pipeline is not None else None)

    return None


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
        ),
        SlashCommandOption(
            name="country",
            description="The country of the server",
            type=interactions.OptionType.STRING,
            required=False,
            min_length=2,
            max_length=2,
        ),
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
        country: str = None,
):
    msg = None
    try:
        await ctx.defer()

        msg = await ctx.send(
            embed=messageLib.standard_embed(
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
                uuid = await playerLib.async_get_uuid(player)
            else:
                uuid = player.replace("-", "")

            if uuid == "":
                await msg.edit(
                    embed=messageLib.standard_embed(
                        title="Error",
                        description=f"Player `{player}` not a valid player",
                        color=RED,
                    ),
                    components=messageLib.buttons()
                )
                return
            else:
                msg = await msg.edit(
                    embed=messageLib.standard_embed(
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
            if not str(online_players).isdigit() and not online_players.startswith(
                    ">") and not online_players.startswith("<") and not online_players.startswith("="):
                await msg.edit(
                    embed=messageLib.standard_embed(
                        title="Error",
                        description=f"Online players `{online_players}` not a valid number",
                        color=RED,
                    ),
                    components=messageLib.buttons()
                )
                logger.error(f"Online players `{online_players}` not a valid number: {online_players}")
                return
            if online_players.startswith(">"):
                online_players = {"$gt": int(online_players[1:])}
            elif online_players.startswith("<"):
                online_players = {"$lt": int(online_players[1:])}
            elif online_players.startswith("="):
                online_players = int(online_players[1:])
            elif str(online_players).isdigit():
                online_players = int(online_players)
            else:
                await msg.edit(
                    embed=messageLib.standard_embed(
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
                    embed=messageLib.standard_embed(
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
            if not str(logged_players).isdigit() and not logged_players.startswith(
                    ">") and not logged_players.startswith("<") and not logged_players.startswith("="):
                await msg.edit(
                    embed=messageLib.standard_embed(
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
            elif logged_players.isdigit():
                pipeline[0]["$match"]["$and"].append(
                    {"players.sample.length": int(logged_players)}
                )
            else:
                await msg.edit(
                    embed=messageLib.standard_embed(
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
                            exp = fr"{ip[0]}\.{ip[1]}\.{ip[2]}\.\d+"
                        case "16":
                            exp = fr"{ip[0]}\.{ip[1]}\.\d+\.\d+"
                        case "24":
                            exp = fr"{ip[0]}\.\d+\.\d+\.\d+"
                        case "32":
                            exp = fr"{ip[0]}\.{ip[1]}\.{ip[2]}\.{ip[3]}"
                        case _:
                            await msg.edit(
                                embed=messageLib.standard_embed(
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
                        embed=messageLib.standard_embed(
                            title="Error",
                            description=f"Mask `{mask}` not a valid mask",
                            color=RED,
                        ),
                        components=messageLib.buttons()
                    )
                    return
            else:
                pipeline[0]["$match"]["$and"].append({"ip": {"$regex": f"^{ip}$", "$options": "i"}})
        if country is not None:
            pipeline[0]["$match"]["$and"].append({"geo": {"$exists": True}})
            pipeline[0]["$match"]["$and"].append({"geo.country": {"$regex": f"^{country}$", "$options": "i"}})

        total = databaseLib.count(pipeline)

        if total == 0:
            await msg.edit(
                embed=messageLib.standard_embed(
                    title="No servers found",
                    description="Try again with different parameters",
                    color=RED,
                ),
                components=messageLib.buttons(),
            )
            return

        # check how many servers match
        msg = await msg.edit(
            embed=messageLib.standard_embed(
                title="Finding servers...",
                description=f"Found {total} servers",
                color=BLUE,
            ),
            components=messageLib.buttons(),
        )

        await messageLib.async_load_server(
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
            logger.error(err)
            logger.print(traceback.format_exc())
            await ctx.send(
                embed=messageLib.standard_embed(
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
        org = ctx.message

        index, pipeline = await get_pipe(org)

        await ctx.defer(edit_origin=True)

        logger.print(f"next page called")

        msg = await ctx.edit_origin(
            embed=messageLib.standard_embed(
                title="Loading...",
                description="Loading...",
                color=BLUE,
            ),
            components=messageLib.buttons(),
            file=interactions.File(file="assets/loading.png", file_name="favicon.png"),
        )

        # get the pipeline and index from the message
        total = databaseLib.count(pipeline)
        if index + 1 >= total:
            index = 0
        else:
            index += 1

        msg = await msg.edit(
            embed=messageLib.standard_embed(
                title="Loading...",
                description=f"Loading server {index + 1} of {total}",
                color=BLUE,
            ),
            components=messageLib.buttons(),
            file=None
        )

        await messageLib.async_load_server(
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

        logger.error(err)
        logger.print(f"Full traceback: {traceback.format_exc()}")

        await ctx.send(
            embed=messageLib.standard_embed(
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
        org = ctx.message
        index, pipeline = await get_pipe(org)
        await ctx.defer(edit_origin=True)

        logger.print(f"previous page called")

        msg = await ctx.edit_origin(
            embed=messageLib.standard_embed(
                title="Loading...",
                description="Loading...",
                color=BLUE,
            ),
            components=messageLib.buttons(),
            file=interactions.File(file="assets/loading.png", file_name="favicon.png"),
        )

        # get the pipeline and index from the message
        total = databaseLib.count(pipeline)
        if index - 1 >= 0:
            index -= 1
        else:
            index = total - 1

        msg = await msg.edit(
            embed=messageLib.standard_embed(
                title="Loading...",
                description=f"Loading server {index + 1} of {total}",
                color=BLUE,
            ),
            components=messageLib.buttons(),
            file=None
        )

        await messageLib.async_load_server(
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

        logger.error(err)
        logger.print(f"Full traceback: {traceback.format_exc()}")

        await ctx.send(
            embed=messageLib.standard_embed(
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
        index, pipeline = await get_pipe(org)
        await ctx.defer(ephemeral=True)

        logger.print(f"players called")

        host = databaseLib.get_doc_at_index(pipeline, index)

        player_list = await playerLib.async_player_list(host["ip"], host["port"])

        if player_list is None:
            await ctx.send(
                embed=messageLib.standard_embed(
                    title="Error",
                    description="An error occurred while trying to get the players (server offline?)",
                    color=RED,
                ),
                ephemeral=True,
            )
            return

        # remove players that have duplicate names
        for player in player_list:
            if player_list.count(player) > 1:
                player_list.remove(player)

        logger.print(f"Found {len(player_list)} players")

        # create a list of player lists that are 25 players long
        player_list_list = [player_list[i:i + 25] for i in range(0, len(player_list), 25)]
        pages = []

        for player_list in player_list_list:
            embed = messageLib.standard_embed(
                title=f"Players on {host['ip']}",
                description=f"Found {len(player_list)} players",
                color=BLUE,
            )
            for player in player_list:
                online = "🟢" if player["online"] else "🔴"
                if "lastSeen" in str(player):
                    time_ago = textLib.time_ago(datetime.datetime.utcfromtimestamp(player["lastSeen"]))
                else:
                    time_ago = "Unknown"
                embed.add_field(
                    name=f'{online} `{player["name"]}`',
                    value=f'`{player["id"]}` | Last Online: {time_ago}',
                    inline=True,
                )

            pages.append(embed)

        pag = Paginator.create_from_embeds(ctx.bot, *pages, timeout=60)
        await pag.send(ctx)
    except Exception as err:
        if "403|Forbidden" in str(err):
            await ctx.send(
                embed=messageLib.standard_embed(
                    title="An error occurred",
                    description="Wrong channel for this bot",
                    color=RED,
                ),
                ephemeral=True,
            )
            return

        logger.error(err)
        logger.print(f"Full traceback: {traceback.format_exc()}")

        await ctx.send(
            embed=messageLib.standard_embed(
                title="Error",
                description="An error occurred while trying to get the players",
                color=RED,
            ),
            ephemeral=True,
        )


# button to jump to a specific index
@interactions.component_callback("jump")
async def jump(ctx: interactions.ComponentContext):
    org = None
    # when pressed should spawn a modal with a text input and then edit the message with the new index
    try:
        org = ctx.message

        logger.print(f"jump called")
        # get the files attached to the message
        index, pipeline = await get_pipe(org)

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
                logger.warning(f"Invalid index: {index}")
                await ctx.send(
                    embed=messageLib.standard_embed(
                        title="Error",
                        description=f"Invalid index, must be between 1 and {total}",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return
            else:
                await modal_ctx.send(
                    embed=messageLib.standard_embed(
                        title="Success",
                        description=f"Jumping to index {index}",
                        color=GREEN,
                    ),
                    ephemeral=True,
                )

            # edit the message
            await messageLib.async_load_server(
                index=index - 1,
                pipeline=pipeline,
                msg=org,
            )
        except asyncio.TimeoutError:
            await ctx.send(
                embed=messageLib.standard_embed(
                    title="Error",
                    description="Timed out",
                    color=RED,
                ),
                ephemeral=True,
            )
    except Exception as err:
        if "403|Forbidden" in str(err):
            await ctx.delete(
                message=org,
            )
            return

        logger.error(err)
        logger.print(f"Full traceback: {traceback.format_exc()}")
        await ctx.send(
            embed=messageLib.standard_embed(
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

        index, pipeline = await get_pipe(org)

        logger.print(f"sort called")

        # get the pipeline
        logger.print(f"pipeline: {pipeline}")

        # send a message with a string menu that express after 60s
        string_menu = interactions.StringSelectMenu(
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
            custom_id="sort_method",
            min_values=1,
            max_values=1,
            disabled=False,
        )

        msg = await ctx.send(
            embed=messageLib.standard_embed(
                title="Sort",
                description="Sort the servers by...",
                color=BLUE,
            ),
            components=[
                interactions.ActionRow(
                    string_menu,
                ),
            ],
            ephemeral=True,
        )

        try:
            # wait for the response
            menu = await ctx.bot.wait_for_component(timeout=60, components=string_menu)
        except asyncio.TimeoutError:
            await msg.delete(context=ctx)
            return
        else:
            # get the value
            value = menu.ctx.values[0]
            logger.print(f"sort method: {value}")
            sort_method = {}

            match value:
                case "players":
                    sort_method = {"$sort": {"players.online": -1}}
                case "limit":
                    sort_method = {"$sort": {"players.max": -1}}
                case "version":
                    sort_method = {"$sort": {"version": -1}}
                case "last_scan":
                    sort_method = {"$sort": {"lastSeen": -1}}
                case "random":
                    sort_method = {"$sample": {"size": 1000}}
                case _:
                    await ctx.send(
                        embed=messageLib.standard_embed(
                            title="Error",
                            description="Invalid sort method",
                            color=RED,
                        ),
                        ephemeral=True,
                    )

            await msg.delete(context=ctx)
            msg = await ctx.send(
                embed=messageLib.standard_embed(
                    title="Success",
                    description=f"Sorting by `{value}`",
                    color=GREEN,
                ),
                ephemeral=True,
            )

            # loop through the pipeline and replace the sort method
            for i in range(len(pipeline)):
                if "$sort" in pipeline[i] or "$sample" in pipeline[i]:
                    pipeline[i] = sort_method
                    break
            else:
                pipeline.append(sort_method)

            # loop through the pipeline and remove the limit
            for i in range(len(pipeline)):
                if "$limit" in pipeline[i]:
                    pipeline.pop(i)
                    break

            # limit to 1k servers
            pipeline.append({"$limit": 1000})

            # edit the message
            await messageLib.async_load_server(
                index=0,
                pipeline=pipeline,
                msg=org,
            )

            await msg.delete(context=ctx)
    except AttributeError:
        logger.print(f"AttributeError")
    except Exception as err:
        if "403|Forbidden" in str(err):
            await ctx.send(
                embed=messageLib.standard_embed(
                    title="An error occurred",
                    description="Wrong channel for this bot",
                    color=RED,
                ),
                ephemeral=True,
            )
            return
        logger.error(err)
        logger.print(f"Full traceback: {traceback.format_exc()}")
        await ctx.send(
            embed=messageLib.standard_embed(
                title="Error",
                description="An error occurred while trying to sort the servers",
                color=RED,
            ),
            ephemeral=True,
        )


# button to update the message
@interactions.component_callback("update")
async def update_command(ctx: interactions.ComponentContext):
    await update(ctx)


async def update(ctx: interactions.ComponentContext | interactions.ContextMenuContext):
    try:
        org = ctx.message if type(ctx) is interactions.ComponentContext else ctx.target

        logger.print(f"update page called for {org.id}")
        index, pipeline = await get_pipe(org)
        await ctx.defer(edit_origin=True) if type(ctx) is interactions.ComponentContext else ctx.send(
            embed=messageLib.standard_embed(
                title="Loading...",
                description="Loading...",
                color=BLUE,
            ),
            ephemeral=True,
        )

        msg = await org.edit(
            embed=messageLib.standard_embed(
                title="Loading...",
                description="Loading...",
                color=BLUE,
            ),
            components=messageLib.buttons(),
            file=interactions.File(file="assets/loading.png", file_name="favicon.png"),
        )

        # get the pipeline and index from the message
        total = databaseLib.count(pipeline)

        msg = await msg.edit(
            embed=messageLib.standard_embed(
                title="Loading...",
                description=f"Loading server {index + 1} of {total}",
                color=BLUE,
            ),
            components=messageLib.buttons(),
        )

        # load the server
        await messageLib.async_load_server(
            index=index,
            pipeline=pipeline,
            msg=msg,
        )
    except Exception as err:
        if "403|Forbidden" in str(err):
            await ctx.send(
                embed=messageLib.standard_embed(
                    title="An error occurred",
                    description="Wrong channel for this bot",
                    color=RED,
                ),
                ephemeral=True,
            )
            return

        logger.error(err)
        logger.print(f"Full traceback: {traceback.format_exc()}")

        await ctx.send(
            embed=messageLib.standard_embed(
                title="Error",
                description="An error occurred while trying to update the message",
                color=RED,
            ),
            ephemeral=True,
        )


# button to show mods
@interactions.component_callback("mods")
async def mods(ctx: interactions.ComponentContext):
    try:
        org = ctx.message

        index, pipeline = await get_pipe(org)

        logger.print(f"mods called")

        await ctx.defer(ephemeral=True)

        # get the pipeline
        logger.print(f"pipeline: {pipeline}")

        host = databaseLib.get_doc_at_index(pipeline, index)

        if "mods" not in host.keys():
            await ctx.send(
                embed=messageLib.standard_embed(
                    title="Error",
                    description="No mods found",
                    color=RED,
                ),
                ephemeral=True,
            )
            return

        mod_list = host["mods"]

        # create a paginator
        pages = []
        for mod in mod_list:
            logger.print(mod)
            embed = messageLib.standard_embed(
                title=mod["name"],
                description=f"Version: {mod['version']}\nModID: {mod['id']}\nRequired: {mod['required']}",
                color=BLUE,
            )
            pages.append(embed)

        if pages:
            pag = Paginator.create_from_embeds(ctx.bot, *pages, timeout=60)
            await pag.send(ctx)
        else:
            await ctx.send(
                embed=messageLib.standard_embed(
                    title="Error",
                    description="No mods found",
                    color=RED,
                ),
                ephemeral=True,
            )
    except Exception as err:
        if "403|Forbidden" in str(err):
            await ctx.send(
                embed=messageLib.standard_embed(
                    title="An error occurred",
                    description="Wrong channel for this bot",
                    color=RED,
                ),
                ephemeral=True,
            )
            return

        logger.error(err)
        logger.print(f"Full traceback: {traceback.format_exc()}")

        await ctx.send(
            embed=messageLib.standard_embed(
                title="Error",
                description="An error occurred while trying to get the players",
                color=RED,
            ),
            ephemeral=True,
        )


# button to try and join the server
@interactions.component_callback("join")
async def join(ctx: interactions.ComponentContext):
    # get the user tag
    user = ctx.message.interaction._user_id
    user = ctx.bot.get_user(user)
    logger.print(f"user: {user}")

    # 504758496370360330
    if user != "@pilot1782":
        await ctx.send(
            embed=messageLib.standard_embed(
                title="Error",
                description="You are not allowed to use this feature, it's in alpha rn",
                color=RED,
            ),
            ephemeral=True,
        )
    try:
        # step one get the server info
        org = ctx.message
        org_file = org.attachments[0]
        with open("pipeline.ason", "w") as f:
            async with aiohttp.ClientSession() as session, session.get(org_file.url) as resp:
                pipeline = await resp.text()
            f.write(pipeline)

        index, pipeline = await get_pipe(org)

        logger.print(f"join called")

        await ctx.defer(ephemeral=True)

        # get the pipeline
        logger.print(f"pipeline: {pipeline}")

        host = databaseLib.get_doc_at_index(pipeline, index)

        # step two is the server online
        host = serverLib.update(host=host["ip"], fast=False, port=host["port"])

        if host["lastSeen"] < time.time() - 60:
            await ctx.send(
                embed=messageLib.standard_embed(
                    title="Error",
                    description="Server is offline",
                    color=RED,
                ),
                ephemeral=True,
            )
            return

        # step three it's joinin' time
        # get the activation code url
        url = mcLib.get_activation_code_url(clientID=azure_client_id, redirect_uri=azure_redirect_uri)

        # send the url
        embed = messageLib.standard_embed(
            title="Sign in to Microsoft to join",
            description=f"Open [this link]({url}) to sign in to Microsoft and join the server, then click the `Submit` button below and paste the provided code",
            color=BLUE,
        )
        embed.set_footer(text='org_id ' + str(org.id))
        await ctx.send(
            embed=embed,
            components=[interactions.Button(label="Submit", custom_id="submit", style=interactions.ButtonStyle.DANGER)],
            ephemeral=True,
        )
    except Exception as err:
        if "403|Forbidden" in str(err):
            await ctx.send(
                embed=messageLib.standard_embed(
                    title="An error occurred",
                    description="Wrong channel for this bot",
                    color=RED,
                ),
                ephemeral=True,
            )
            return

        logger.error(err)
        logger.print(f"Full traceback: {traceback.format_exc()}")

        await ctx.send(
            embed=messageLib.standard_embed(
                title="Error",
                description="An error occurred while trying to get the players",
                color=RED,
            ),
            ephemeral=True,
        )


# button to try and join the server for realziez
@interactions.component_callback("submit")
async def submit(ctx: interactions.ComponentContext):
    try:
        org = ctx.message
        org_org_id = org.embeds[0].footer.text.split(' ')[1]
        org = ctx.channel.get_message(org_org_id)
        logger.print(f"org: {org}")

        logger.print(f"submit called")
        # get the files attached to the message
        index, pipeline = await get_pipe(org)

        # create the text input
        text_input = interactions.ShortText(
            label="Activation Code",
            placeholder="A.A0_AA0.0.aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            min_length=40,
            max_length=55,
            custom_id="code",
            required=True,
        )

        # create a modal
        modal = interactions.Modal(
            text_input,
            title="Activation Code",
        )

        # send the modal
        await ctx.send_modal(modal)

        # wait for the modal to be submitted
        try:
            # wait for the response
            modal_ctx = await ctx.bot.wait_for_modal(modal=modal, timeout=60)

            # get the response
            code = modal_ctx.responses["code"]
        except asyncio.TimeoutError:
            await ctx.edit_origin(
                embed=messageLib.standard_embed(
                    title="Error",
                    description="Timed out",
                    color=RED,
                ),
                components=[],
            )
            return
        else:
            await modal_ctx.send(
                embed=messageLib.standard_embed(
                    title="Success",
                    description="Code received",
                    color=GREEN,
                ),
                ephemeral=True,
            )

        # try and get the minecraft token
        try:
            res = await mcLib.get_minecraft_token(clientID=azure_client_id,
                                                  redirect_uri=azure_redirect_uri,
                                                  act_code=code, )

            if res["type"] == "error":
                logger.error(res["error"])
                await ctx.send(
                    embed=messageLib.standard_embed(
                        title="Error",
                        description="An error occurred while trying to get the token",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return
            else:
                uuid = res["uuid"]
                name = res["name"]
                token = res["minecraft_token"]

            # try and delete the original message
            try:
                await org.delete(context=ctx)
            except Exception:
                pass

            mod_msg = await ctx.send(
                embed=messageLib.standard_embed(
                    title="Joining...",
                    description=f"Joining the server with the player:\nName: {name}\nUUID: {uuid}",
                    color=BLUE,
                ),
                ephemeral=True,
            )
        except Exception as err:
            await ctx.send(
                embed=messageLib.standard_embed(
                    title="Error",
                    description="An error occurred while trying to get the token",
                    color=RED,
                ),
                ephemeral=True,
            )
            return

        # try and join the server
        host = databaseLib.get_doc_at_index(pipeline, index)
        res = mcLib.join(
            ip=host["ip"],
            port=host["port"],
            player_username=name,
            version=host["version"]["protocol"],
            mine_token=token,
        )

        # try and delete the original message
        try:
            await mod_msg.delete(context=ctx)
        except Exception:
            pass

        # send the res as a json file after removing the favicon if it's there
        if "favicon" in res:
            del res["favicon"]

        await ctx.send(
            embed=messageLib.standard_embed(
                title="Joining...",
                description=f"Joining the server with the player:\nName: {name}\nUUID: {uuid}",
                color=BLUE,
            ),
            file=interactions.File(json.dumps(res, indent=4), "join.json"),
            ephemeral=True,
        )
    except Exception as err:
        logger.error(err)
        logger.print(f"Full traceback: {traceback.format_exc()}")

        await ctx.send(
            embed=messageLib.standard_embed(
                title="Error",
                description="An error occurred while trying to join the server",
                color=RED,
            ),
            components=[],
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
        if ":" in ip:
            ip, port = ip.split(":")
            port = int(port)

        pipeline = {
            "ip": ip,
            "port": port,
        }

        msg = await ctx.send(
            embed=messageLib.standard_embed(
                title="Loading...",
                description="Loading server 1 of 1",
                color=BLUE,
            ),
            components=messageLib.buttons(),
        )

        # test if the server is online
        if databaseLib.count([{"$match": pipeline}]) == 0:
            doc = serverLib.update(host=ip, port=port)
            if doc is None:
                await ctx.send(
                    embed=messageLib.standard_embed(
                        title="An error occurred",
                        description="The server is offline",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                await ctx.delete(
                    message=msg,
                )
                return
            else:
                pipeline = doc
        else:
            pipeline = [{"$match": pipeline}]

        # get the server
        await messageLib.async_load_server(
            index=0,
            pipeline=pipeline,
            msg=msg,
        )
    except Exception as err:
        if "403|Forbidden" in str(err):
            await ctx.send(
                embed=messageLib.standard_embed(
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
        logger.error(err)
        logger.print(f"Full traceback: {traceback.format_exc()}")

        await ctx.send(
            embed=messageLib.standard_embed(
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
            embed=messageLib.standard_embed(
                title="Loading...",
                description="Loading...",
                color=BLUE,
            ),
        )

        global client_id, client_secret

        # test if 'client_id' and 'client_secret' are not None
        if client_id == "" or client_secret == "":
            # spawn a modal asking for client id and secret
            client_id = interactions.ShortText(
                label="Client ID",
                placeholder="Client ID",
                custom_id="clientId",
                min_length=1,
                max_length=100,
            )
            client_secret = interactions.ShortText(
                label="Client Secret",
                placeholder="Client Secret",
                custom_id="clientSecret",
                min_length=1,
                max_length=100,
            )

            modal = interactions.Modal(
                client_id, client_secret,
                title="Auth",
            )

            await ctx.send_modal(modal)

            modal_ctx = ctx
            try:
                modal_ctx = await ctx.bot.wait_for_modal(timeout=90, modal=modal)
            except asyncio.TimeoutError:
                logger.print(f"Timed out")
                await modal_ctx.send(
                    embed=messageLib.standard_embed(
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
                embed=messageLib.standard_embed(
                    title="Success",
                    description="Got the client id and secret",
                    color=GREEN,
                ),
                ephemeral=True,
            )

        if (client_id == "" or client_secret == "") or (client_id is None or client_secret is None):
            await ctx.send(
                embed=messageLib.standard_embed(
                    title="Error",
                    description="Client ID or Client Secret is empty",
                    color=RED,
                ),
                ephemeral=True,
            )
            return

        streams = await twitchLib.async_get_streamers(
            client_id=client_id,
            client_secret=client_secret,
            lang=lang,
        )

        if streams is None or streams == []:
            await msg.edit(
                embed=messageLib.standard_embed(
                    title="Error",
                    description="No streams found",
                    color=RED,
                ),
            )
            return
        else:
            msg = await msg.edit(
                embed=messageLib.standard_embed(
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
        logger.debug(f"Got {total} servers: {names}")
        msg = await msg.edit(
            embed=messageLib.standard_embed(
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
                embed=messageLib.standard_embed(
                    title="Error",
                    description="No servers found",
                    color=RED,
                ),
            )
            return
        else:
            msg = await msg.edit(
                embed=messageLib.standard_embed(
                    title="Loading...",
                    description="Loading 1 of " + str(total),
                    color=BLUE,
                ),
            )

        await messageLib.async_load_server(
            pipeline=pipeline,
            index=0,
            msg=msg,
        )
    except Exception as err:
        if "403|Forbidden" in str(err):
            await ctx.send(
                embed=messageLib.standard_embed(
                    title="An error occurred",
                    description="Wrong channel for this bot",
                    color=RED,
                ),
                ephemeral=True,
            )
            return

        logger.error(err)
        logger.print(f"Full traceback: {traceback.format_exc()}")
        await ctx.send(
            embed=messageLib.standard_embed(
                title="Error",
                description="An error occurred while trying to get the streamers",
                color=RED,
            ),
            ephemeral=True,
        )
        return


# command to upload a character-separated file of ip subnets
@slash_command(
    name="scan",
    description="Scan a list of IP subnets",
    options=[
        SlashCommandOption(
            name="file",
            description="The file of delimited IP subnets",
            type=interactions.OptionType.ATTACHMENT,
            required=True,
        ),
        SlashCommandOption(
            name="delimiter",
            description="The delimiter to use",
            type=interactions.OptionType.STRING,
            required=True,
            choices=[
                interactions.SlashCommandChoice(
                    name="comma",
                    value=",",
                ),
                interactions.SlashCommandChoice(
                    name="semicolon",
                    value=";",
                ),
                interactions.SlashCommandChoice(
                    name="space",
                    value=" ",
                ),
                interactions.SlashCommandChoice(
                    name="line break",
                    value="\n",
                ),
            ]
        )
    ],
)
async def scan(ctx: interactions.SlashContext, file: interactions.Attachment, delimiter: str):
    try:
        await ctx.defer(ephemeral=True)

        # make sure the bot is running on linux
        if os.name != "posix":
            await ctx.send(
                embed=messageLib.standard_embed(
                    title="Error",
                    description="This command only works on Linux hosts",
                    color=RED,
                ),
                ephemeral=True,
            )
            return
        await ctx.send(
            embed=messageLib.standard_embed(
                title="Loading...",
                description="Loading the scanner with the provided ranges",
                color=GREEN,
            ),
            ephemeral=True,
        )

        # load the file
        async with aiohttp.ClientSession() as session:
            async with session.get(file.url) as resp:
                data = await resp.read()
                lines = data.decode("utf-8").split("\n")
        # remove the newlines
        lines = delimiter.join(lines)
        lines = lines.split(delimiter)
        lines = [line.strip() for line in lines]

        # loop through each range and make sure it's a valid mask
        for line in lines:
            pattern = r"^((25[0-5]|(2[0-4]|1\d|[1-9]|)\d)\.?\b){4}\/(1[0-9]|2[0-9]|3[0-2])$"
            if re.match(pattern, line) is None:
                await ctx.send(
                    embed=messageLib.standard_embed(
                        title="Error",
                        description="Invalid subnet: " + line,
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return

        # send the user how many ranges we're scanning
        await ctx.send(
            embed=messageLib.standard_embed(
                title="Loading...",
                description="Scanning " + str(len(lines)) + " ranges",
                color=GREEN,
            ),
            ephemeral=True,
        )

        def _scan(ip_ranges):
            from pyutils.scanner import Scanner
            scan_func = Scanner(logger_func=logger, serverLib=serverLib)
            scan_func.start(ip_ranges=ip_ranges)

        try:
            from pyutils.scanner import Scanner
        except ImportError:
            await ctx.send(
                embed=messageLib.standard_embed(
                    title="Error",
                    description="Scanner import error",
                    color=RED,
                ),
                ephemeral=True,
            )
            return
        else:
            scanner = Thread(target=_scan, args=(lines,))
            scanner.start()
            await ctx.send(
                embed=messageLib.standard_embed(
                    title="Success",
                    description="Started the scanner",
                    color=GREEN,
                ),
                ephemeral=True,
            )
    except Exception as err:
        logger.error(err)
        logger.print(f"Full traceback: {traceback.format_exc()}")
        await ctx.send(
            embed=messageLib.standard_embed(
                title="Error",
                description="An error occurred while trying to scan the file",
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
        logger.debug(f"Getting stats")
        main_embed = messageLib.standard_embed(
            title="Stats",
            description="General stats about the database",
            color=BLUE,
        )

        msg = await ctx.send(embed=main_embed, )

        # get the stats
        total_servers = databaseLib.col.count_documents({})

        main_embed.add_field(
            name="Servers",
            value=f"{total_servers:,}",
            inline=True,
        )
        msg = await msg.edit(embed=main_embed, )

        # get the total player count, ignoring servers with over 150k players and less than 1 player, and the version name is not Unknown, or UNKNOWN or null
        pipeline = [
            {"$match": {"$and": [{"players.online": {"$lt": 150000}}, {"players.online": {"$gt": 0}},
                                 {"version.name": {"$nin": ["Unknown", "UNKNOWN", None]}}]}},
            {"$group": {"_id": None, "total": {"$sum": "$players.online"}}},
        ]
        total_players = databaseLib.aggregate(pipeline)[0]["total"]

        main_embed.add_field(
            name="Players",
            value=f"{total_players:,}",
            inline=True,
        )
        msg = await msg.edit(embed=main_embed, )

        # get the total number of players in players.sample
        pipeline = [
            {"$unwind": "$players.sample"},
            {"$group": {"_id": None, "total": {"$sum": 1}}},
        ]
        total_sample_players = databaseLib.aggregate(pipeline)[0]["total"]

        main_embed.add_field(
            name="Logged Players",
            value=f"{total_sample_players:,} ({round(total_sample_players / total_players * 100, 2)}%)",
            inline=True,
        )
        msg = await msg.edit(embed=main_embed, )

        # get the number of players which do not have a player id of "00000000-0000-0000-0000-000000000000"
        pipeline = [
            {"$match": {"players.sample.id": {"$ne": "00000000-0000-0000-0000-000000000000"}}},
            {"$group": {"_id": None, "total": {"$sum": 1}}},
        ]
        total_real_players = databaseLib.aggregate(pipeline)[0]["total"]

        main_embed.add_field(
            name="Real Players",
            value=f"{total_real_players:,} ({round(total_real_players / total_sample_players * 100, 2)}%)",
            inline=True,
        )
        msg = await msg.edit(embed=main_embed, )

        # get the number of players which have a player id of "00000000-0000-0000-0000-000000000000"
        pipeline = [
            {"$match": {"players.sample.id": "00000000-0000-0000-0000-000000000000"}},
            {"$group": {"_id": None, "total": {"$sum": 1}}},
        ]
        total_fake_players = databaseLib.aggregate(pipeline)[0]["total"]

        main_embed.add_field(
            name="Fake Players",
            value=f"{total_fake_players:,} ({round(total_fake_players / total_sample_players * 100, 2)}%)",
            inline=True,
        )
        msg = await msg.edit(embed=main_embed, )

        # top three orgs
        pipeline = [
            {"$match": {"org": {"$ne": None}}},
            {"$group": {"_id": "$org", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 3},
        ]
        top_three_orgs = list(databaseLib.aggregate(pipeline))

        main_embed.add_field(
            name="Top Three Orgs",
            value="```css\n" + "\n".join([
                f"{i['_id']}: {round(i['count'] / total_servers * 100, 2)}%"
                for i in top_three_orgs
            ]) + "\n```",
            inline=True,
        )
        msg = await msg.edit(embed=main_embed, )

        # get the five most common server version names
        pipeline = [
            {"$match": {"$and": [{"players.online": {"$lt": 150000}}, {"players.online": {"$gt": 0}},
                                 {"version.name": {"$nin": ["Unknown", "UNKNOWN", None]}}]}},
            {"$group": {"_id": "$version.name", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5},
        ]
        top_five_versions = list(databaseLib.aggregate(pipeline))

        main_embed.add_field(
            name="Top Five Versions",
            value="```css\n" + "\n".join([
                f"{i['_id']}: {round(i['count'] / total_servers * 100, 2)}%"
                for i in top_five_versions
            ]) + "\n```",
            inline=True,
        )
        msg = await msg.edit(embed=main_embed, )

        # get the five most common server version ids
        pipeline = [
            {"$match": {"$and": [{"players.online": {"$lt": 150000}}, {"players.online": {"$gt": 0}},
                                 {"version.name": {"$nin": ["Unknown", "UNKNOWN", None]}}]}},
            {"$group": {"_id": "$version.protocol", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5},
        ]
        top_five_version_ids = list(databaseLib.aggregate(pipeline))

        main_embed.add_field(
            name="Top Five Version IDs",
            value="```css\n" + "\n".join([
                f"{textLib.protocol_str(i['_id'])}: {round(i['count'] / total_servers * 100, 2)}%"
                for i in top_five_version_ids
            ]) + "\n```",
            inline=True,
        )
        msg = await msg.edit(embed=main_embed, )

        # get the percent of servers which are cracked (cracked == True)
        pipeline = [
            {"$match": {"cracked": True}},
            {"$group": {"_id": None, "count": {"$sum": 1}}},
        ]
        cracked = list(databaseLib.aggregate(pipeline))

        main_embed.add_field(
            name="Cracked",
            value=textLib.percent_bar(cracked[0]['count'], total_servers),
            inline=True,
        )
        msg = await msg.edit(embed=main_embed, )

        # get the percent of servers which have favicons (hasFavicon == True)
        pipeline = [
            {"$match": {"hasFavicon": True}},
            {"$group": {"_id": None, "count": {"$sum": 1}}},
        ]
        has_favicon = list(databaseLib.aggregate(pipeline))

        main_embed.add_field(
            name="Has Favicon",
            value=textLib.percent_bar(has_favicon[0]['count'], total_servers),
            inline=True,
        )
        msg = await msg.edit(embed=main_embed, )

        # get the percent of servers which have forge mods (hasForgeData == True)
        pipeline = [
            {"$match": {"hasForgeData": True}},
            {"$group": {"_id": None, "count": {"$sum": 1}}},
        ]
        has_forge_data = list(databaseLib.aggregate(pipeline))

        main_embed.add_field(
            name="Has Forge Data",
            value=textLib.percent_bar(has_forge_data[0]['count'], total_servers),
            inline=True,
        )
        msg = await msg.edit(embed=main_embed, )

        if cstats not in ["", "...", None]:
            # add the custom text
            main_embed.add_field(
                name="Custom Text",
                value=cstats,
                inline=False,
            )
            await msg.edit(embed=main_embed, )
    except Exception as err:
        if "403|Forbidden" in str(err):
            await ctx.delete(
                message=msg
            )
            return

        logger.error(err)
        logger.print(f"Full traceback: {traceback.format_exc()}")
        await ctx.send(
            embed=messageLib.standard_embed(
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
        embed=messageLib.standard_embed(
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
            name="`/scan`",
            value="Scan a list of ip ranges",
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
    logger.critical(f"Logged in as {user.username}#{user.discriminator}")


# -----------------------------------------------------------------------------
# bot apps

@interactions.message_context_menu(name="Refresh")
async def refresh(ctx: interactions.ContextMenuContext):
    if ctx.target is None or ctx.target.embeds is None:
        await ctx.send(
            embed=messageLib.standard_embed(
                title="Error",
                description="This message does not have an embed",
                color=RED,
            ),
            ephemeral=True,
        )
    else:
        logger.print(f"Found {len(ctx.target.attachments)} embeds in message {ctx.target.id}: {ctx.target.attachments}")
        # run the update command
        await update(ctx)


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
            logger.critical(e)
            logger.print("Stopping bot")
            asyncio.run(bot.close())
