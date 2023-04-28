"""This is the discord bot for the mongoDB server list
"""

import asyncio
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

bot = interactions.Client(
    token=DISCORD_TOKEN,
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
    "online": Date(12345),
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
    try:
        await ctx.defer()

        # print out the parameters that were passed
        print(
            f"find command called with parameters:",
            "version={version},",
            "max_players={max_players},",
            "player={player},",
            "sign={sign},",
            "description={description}",
            "cracked={cracked}",
        )

        logger.print(
            f"[main.find] find command called with parameters:",
            f"version={version},",
            f"max_players={max_players},",
            f"player={player},",
            f"sign={sign},",
            f"description={description}",
            f"cracked={cracked}",
        )

        msg = await ctx.send(
            embed=messageLib.standardEmbed(
                title="Finding servers...",
                description="This may take a while",
                color=BLUE,
            ),
            components=messageLib.buttons(True, True, True, True, True, )
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
            if version.isnumeric():
                pipeline[0]["$match"]["$and"].append(
                    {"version.protocol": {"$regex": f"^{version}"}}
                )
            else:
                pipeline[0]["$match"]["$and"].append(
                    {"version.name": {"$regex": f".*{version}.*"}}
                )
        if max_players is not None:
            pipeline[0]["$match"]["$and"].append({"players.max": max_players})
        if sign is not None:
            pipeline[0]["$match"]["$and"].append(
                {"world.signs": {"$elemMatch": {"text": {"$regex": f".*{sign}.*"}}}}
            )
        if description is not None:
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
                components=messageLib.buttons(True, True, True, True, True),
            )
            return

        # check how many servers match
        msg = await msg.edit(
            embed=messageLib.standardEmbed(
                title="Finding servers...",
                description=f"Found {total} servers",
                color=BLUE,
            ),
            components=messageLib.buttons(True, True, True, True, True),
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
                components=messageLib.buttons(True, True, True, True, True),
            )
            return

        embed = stuff["embed"]
        comps = stuff["components"]

        await msg.edit(
            embed=embed,
            components=comps,
        )
    except Exception as err:
        logger.error(f"[main.find] {err}")
        await ctx.send(
            embed=messageLib.standardEmbed(
                title="An error occurred",
                description="Please try again later",
                color=RED,
            ),
        )


# command to get the next page of servers
@interactions.component_callback("next")
async def next_page(ctx: interactions.ComponentContext):
    try:
        org = ctx.message
        orgFoot = org.embeds[0].footer.text
        await ctx.defer(edit_origin=True)

        logger.print(f"[main.next_page] next page called")

        msg = await ctx.edit_origin(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description="Loading...",
                color=BLUE,
            ),
            components=messageLib.buttons(True, True, True, True, True),
        )

        # get the pipeline and index from the message
        pipeline = orgFoot.split(" servers in: ")[1]
        pipeline = json.loads(pipeline.replace("'", '"'))

        index = int(orgFoot.split("Showing ")[1].split(" of ")[0]) - 1

        total = databaseLib.count(pipeline)

        if index + 1 < total:
            index += 1
        else:
            index = 0

        logger.print(f"[main.next_page] index: {index} total: {total} pipeline: {pipeline}")

        msg = await msg.edit(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description=f"Loading server {index + 1} of {total}",
                color=BLUE,
            ),
            components=messageLib.buttons(True, True, True, True, True),
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
                components=messageLib.buttons(True, True, True, True, True),
            )

        embed = stuff["embed"]
        comps = stuff["components"]

        await msg.edit(
            embed=embed,
            components=comps,
        )
    except Exception as err:
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


# command to get the previous page of servers
@interactions.component_callback("previous")
async def previous_page(ctx: interactions.ComponentContext):
    try:
        org = ctx.message
        orgFoot = org.embeds[0].footer.text
        await ctx.defer(edit_origin=True)

        logger.print(f"[main.previous_page] previous page called")

        msg = await ctx.edit_origin(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description="Loading...",
                color=BLUE,
            ),
            components=messageLib.buttons(True, True, True, True, True),
        )

        # get the pipeline and index from the message
        pipeline = orgFoot.split(" servers in: ")[1]
        pipeline = json.loads(pipeline.replace("'", '"'))

        index = int(orgFoot.split("Showing ")[1].split(" of ")[0]) - 1

        total = databaseLib.count(pipeline)

        if index - 1 >= 0:
            index -= 1
        else:
            index = total - 1

        logger.print(f"[main.previous_page] index: {index} total: {total} pipeline: {pipeline}")

        msg = await msg.edit(
            embed=messageLib.standardEmbed(
                title="Loading...",
                description=f"Loading server {index + 1} of {total}",
                color=BLUE,
            ),
            components=messageLib.buttons(True, True, True, True, True),
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
                components=messageLib.buttons(True, True, True, True, True),
            )

        embed = stuff["embed"]
        comps = stuff["components"]

        await msg.edit(
            embed=embed,
            components=comps,
        )
    except Exception as err:
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


# command to send the players that are online
@interactions.component_callback("players")
async def players(ctx: interactions.ComponentContext):
    try:
        await ctx.defer(ephemeral=True)

        logger.print(f"[main.players] players called")

        org = ctx.message

        # get the host dict from the db
        pipeline = json.loads(org.embeds[0].footer.text.split(" servers in: ")[1])
        index = int(org.embeds[0].footer.text.split(" servers in: ")[0].split(" ")[-1])

        host = databaseLib.get_doc_at_index(pipeline, index)

        player_list = await playerLib.playerList(host["ip"], host["port"])

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


# command to change the sort method
@interactions.component_callback("sort")
async def sort(ctx: interactions.ComponentContext):
    try:
        org = ctx.message
        orgFooter = org.embeds[0].footer
        await ctx.defer(ephemeral=True)

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
                    sortMethod = {"$sample": {"size": 1}}
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
            )
    except AttributeError:
        logger.print(f"[main.sort] AttributeError")
    except Exception as err:
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


# other commands
# -----------------------------------------------------------------------------


# command to get stats about the server
@slash_command(
    name="stats",
    description="Get stats about the server",
)
async def stats(ctx: interactions.SlashContext):
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
            value=totalServers,
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
            value=totalPlayers,
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
            value=totalSamplePlayers,
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
        logger.print(f"[main.stats] topFiveVersions: {topFiveVersions}")

        mainEmbed.add_field(
            name="Top Five Versions",
            value="```css\n" + "\n".join([
                f"{i['_id']}: {round(i['count'] / totalServers * 100, 2)}%"
                for i in topFiveVersions
            ]) + "\n```",
            inline=True,
        )
        msg = await msg.edit(embed=mainEmbed, )
    except Exception as err:
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
    try:
        # start the bot
        bot.start()
    except KeyboardInterrupt:
        # stop the bot
        asyncio.run(bot.close())
    except Exception as e:
        # log the error
        logger.critical(f"[main] Error: {e}")
        time.sleep(5)
