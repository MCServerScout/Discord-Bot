import asyncio
import json
import os
import re
import traceback
from datetime import datetime
from threading import Thread

import aiohttp
import country_converter
import requests
import sentry_sdk
from interactions import (
    slash_command,
    Extension,
    SlashContext,
    SlashCommandOption,
    OptionType,
    ShortText,
    Modal,
    SlashCommandChoice,
    Attachment,
    File,
)
from interactions.ext.paginators import Paginator

from .Colors import *  # skipcq: PYL-W0614

base_match = {
    "$match": {
        "$and": [
            {"players.max": {"$gt": 0}},
            {"players.online": {"$lt": 150000}},
            {"players.online": {"$gte": 0}},
        ]
    }
}


class Commands(Extension):
    def __init__(
        self,
        *_,
        mcLib,
        messageLib,
        playerLib,
        logger,
        databaseLib,
        serverLib,
        twitchLib,
        Scanner,
        textLib,
        cstats,
        azure_client_id,
        azure_redirect_uri,
        client_id,
        client_secret,
        upload_serv,
        **__,
    ):
        super().__init__()

        self.mcLib = mcLib
        self.messageLib = messageLib
        self.playerLib = playerLib
        self.logger = logger
        self.databaseLib = databaseLib
        self.serverLib = serverLib
        self.twitchLib = twitchLib
        self.Scanner = Scanner
        self.textLib = textLib
        self.cstats = cstats
        self.azure_client_id = azure_client_id
        self.azure_redirect_uri = azure_redirect_uri
        self.client_id = client_id
        self.client_secret = client_secret
        self.upload_serv = upload_serv

    @slash_command(
        name="find",
        description="Find a server by anything in the database, any ranges must be in interval notation",
        options=[
            SlashCommandOption(
                name="ip",
                description="The ip of the server or a subnet mask (ex:10.0.0.0/24)",
                type=OptionType.STRING,
                required=False,
            ),
            SlashCommandOption(
                name="version",
                description="The version of the server",
                type=OptionType.STRING,
                required=False,
            ),
            SlashCommandOption(
                name="max_players",
                description="The max players of the server as an int or range",
                type=OptionType.STRING,
                required=False,
                min_length=1,
            ),
            SlashCommandOption(
                name="online_players",
                description="The online players of the server as an int or range",
                type=OptionType.STRING,
                required=False,
                min_length=1,
            ),
            SlashCommandOption(
                name="logged_players",
                description="The logged players of the server as an int or range",
                type=OptionType.STRING,
                required=False,
                min_length=1,
            ),
            SlashCommandOption(
                name="player",
                description="The player on the server",
                type=OptionType.STRING,
                required=False,
                min_length=1,
            ),
            SlashCommandOption(
                name="sign",
                description="The text of a sign on the server",
                type=OptionType.STRING,
                required=False,
                min_length=1,
            ),
            SlashCommandOption(
                name="description",
                description="The description of the server, via regex: `.*<your input>.*`",
                type=OptionType.STRING,
                required=False,
                min_length=1,
            ),
            SlashCommandOption(
                name="cracked",
                description="If the server is cracked",
                type=OptionType.BOOLEAN,
                required=False,
            ),
            SlashCommandOption(
                name="has_favicon",
                description="If the server has a favicon",
                type=OptionType.BOOLEAN,
                required=False,
            ),
            SlashCommandOption(
                name="country",
                description="The country of the server in a two char ISO code, ex: us",
                type=OptionType.STRING,
                required=False,
                min_length=2,
                max_length=2,
            ),
            SlashCommandOption(
                name="whitelisted",
                description="If the server is whitelisted",
                type=OptionType.BOOLEAN,
                required=False,
            ),
        ],
    )
    async def find(
        self,
        ctx: SlashContext,
        ip: str = None,
        version: str = None,
        max_players: str = None,
        online_players: str = None,
        logged_players: str = None,
        player: str = None,
        sign: str = None,
        description: str = None,
        cracked: bool = None,
        has_favicon: bool = None,
        country: str = None,
        whitelisted: bool = None,
    ):
        """
        Find a server by filtering through the database

        Interval notation:
        - Intervals are a shorthand expression of a range of two numbers
        - Brackets are inclusive, parentheses are exclusive
        - Ex:
            - `[a, b]` is a to b inclusive or `a <= x <= b`
            - `(a, b)` is a to b exclusive or `a < x < b`
            - `[a, b)` is a to b inclusive on the left and exclusive on the right or `a <= x < b`
            - `(a, b]` is a to b exclusive on the left and inclusive on the right or `a < x <= b`

        :param ctx: The context of the command
        :param str ip: The ip of the server or a subnet mask (ex: 10.0.0.0/24)
        :param str|int version: The version of the server, can be either the name or the protocol (ex: 1.17.1 or 756)
        :param str max_players: The max players of the server as an int or range (ex: 10 or [0, 10])
        :param str online_players: The online players of the server as an int or range (ex: 10 or [0, 10])
        :param str logged_players: The logged players of the server as an int or range (ex: 10 or [0, 10])
        :param str player: The player on the server
        :param str sign: The text of a sign on the server
        :param str description: The description of the server, via regex: `.*<your input>.*`
        :param bool cracked: If the server is cracked
        :param bool has_favicon: If the server has a favicon
        :param str country: The country of the server in a two char ISO code, ex: us
        :param bool whitelisted: If the server is whitelisted

        :return: None
        """
        msg = None
        try:
            await ctx.defer()

            msg = await ctx.send(
                embed=self.messageLib.standard_embed(
                    title="Finding servers...",
                    description="This may take a while",
                    color=BLUE,
                ),
                components=self.messageLib.buttons(),
            )

            # default pipeline
            pipeline = [
                base_match,
                {"$sample": {"size": 10000}},
            ]

            if player is not None:
                player = player.strip()
                if len(player) < 16:
                    # get the uuid of the player
                    uuid = await self.playerLib.async_get_uuid(player)
                else:
                    uuid = player.replace("-", "")

                if uuid == "":
                    await msg.edit(
                        embed=self.messageLib.standard_embed(
                            title="Error",
                            description=f"Player `{player}` not a valid player",
                            color=RED,
                        ),
                        components=self.messageLib.buttons(),
                    )
                    return
                else:
                    msg = await msg.edit(
                        embed=self.messageLib.standard_embed(
                            title="Finding servers...",
                            description="Looking for servers with "
                            + player
                            + " on them",
                            color=BLUE,
                        ),
                        components=self.messageLib.buttons(),
                    )

                self.logger.debug(
                    f"Finding servers with player {player} on them ({uuid})"
                )

                pipeline[0]["$match"]["$and"].append(
                    {"players.sample.id": uuid},
                )

            if version is not None:
                if version.isnumeric() and "." not in version:
                    pipeline[0]["$match"]["$and"].append(
                        {"version.protocol": int(version)}
                    )
                else:
                    pipeline[0]["$match"]["$and"].append(
                        {"version.name": {"$regex": f".*{version}.*"}}
                    )
            if max_players is not None:
                if max_players.isnumeric():
                    pipeline[0]["$match"]["$and"].append({"players.max": max_players})
                elif (
                    max_players.startswith(("[", "("))
                    and max_players.endswith(("]", ")"))
                    and "," in max_players
                ):
                    rng = self.textLib.parse_range(max_players)

                    if rng[0]:
                        pipeline[0]["$match"]["$and"].append(
                            {
                                "players.max": {
                                    f"${'gt' if rng[0][0] else 'gte'}": int(rng[0][1])
                                }
                            }
                        )
                    if rng[1]:
                        pipeline[0]["$match"]["$and"].append(
                            {
                                "players.max": {
                                    f"${'lt' if rng[1][0] else 'lte'}": int(rng[1][1])
                                }
                            }
                        )
                else:
                    await msg.edit(
                        embed=self.messageLib.standard_embed(
                            title="Error",
                            description=f"Max players `{max_players}` not a valid range, use interval notation\nex:\n- [0, 10]\n- (0, 10)\n- [0, 10)\n- (0, 10]",
                            color=RED,
                        ),
                        components=self.messageLib.buttons(),
                    )
                    return
            if online_players is not None:
                if online_players.isnumeric():
                    pipeline[0]["$match"]["$and"].append(
                        {"players.max": online_players}
                    )
                elif (
                    online_players.startswith(("[", "("))
                    and online_players.endswith(("]", ")"))
                    and "," in online_players
                ):
                    rng = self.textLib.parse_range(online_players)

                    if rng[0]:
                        pipeline[0]["$match"]["$and"].append(
                            {
                                "players.max": {
                                    f"${'gt' if rng[0][0] else 'gte'}": int(rng[0][1])
                                }
                            }
                        )
                    if rng[1]:
                        pipeline[0]["$match"]["$and"].append(
                            {
                                "players.max": {
                                    f"${'lt' if rng[1][0] else 'lte'}": int(rng[1][1])
                                }
                            }
                        )
                else:
                    await msg.edit(
                        embed=self.messageLib.standard_embed(
                            title="Error",
                            description=f"Online players `{online_players}` not a valid range, use interval notation\nex:\n- [0, 10]\n- (0, 10)\n- [0, 10)\n- (0, 10]",
                            color=RED,
                        ),
                        components=self.messageLib.buttons(),
                    )
                    return
            if sign is not None:
                pipeline[0]["$match"]["$and"].append(
                    {"world.signs": {"$elemMatch": {"text": {"$regex": f".*{sign}.*"}}}}
                )
            if description is not None:
                description = description.replace("'", ".")

                # validate that the description is a valid regex
                try:
                    re.compile(description)
                    for rng in re.findall(r"\{\d+}", description):
                        if int(rng[1:-1]) > 1000:
                            await msg.edit(
                                embed=self.messageLib.standard_embed(
                                    title="Error",
                                    description=f"Quantifier range `{rng}` too large",
                                    color=RED,
                                ),
                                components=self.messageLib.buttons(),
                            )
                            return
                except (re.error, ValueError):
                    await msg.edit(
                        embed=self.messageLib.standard_embed(
                            title="Error",
                            description=f"Description `{description}` not a valid regex",
                            color=RED,
                        ),
                        components=self.messageLib.buttons(),
                    )
                    return

                # case-insensitive regex, search through desc.text and through desc.extra.text
                pipeline[0]["$match"]["$and"].append(
                    {
                        "$or": [
                            {
                                "description.text": {
                                    "$regex": f".*{description}.*",
                                    "$options": "i",
                                }
                            },
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
                pipeline[0]["$match"]["$and"].extend(
                    [
                        {"players.sample": {"$exists": True}},
                        {"players.sample.0": {"$exists": True}},
                    ]
                )
                if max_players.isnumeric():
                    pipeline[0]["$match"]["$and"].append({"players.max": max_players})
                elif (
                    max_players.startswith(("[", "("))
                    and max_players.endswith(("]", ")"))
                    and "," in max_players
                ):
                    rng = self.textLib.parse_range(max_players)

                    if rng[0]:
                        pipeline[0]["$match"]["$and"].append(
                            {
                                "players.max": {
                                    f"${'gt' if rng[0][0] else 'gte'}": int(rng[0][1])
                                }
                            }
                        )
                    pipeline[0]["$match"]["$and"].append(
                        {
                            "players.max": {
                                f"${'lt' if rng[1][0] else 'lte'}": int(rng[1][1])
                            }
                        }
                    )
                    if rng[1]:
                        pass
                else:
                    await msg.edit(
                        embed=self.messageLib.standard_embed(
                            title="Error",
                            description=f"Logged players `{logged_players}` not a valid range, use interval notation\nex:\n- [0, 10]\n- (0, 10)\n- [0, 10)\n- (0, 10]",
                            color=RED,
                        ),
                        components=self.messageLib.buttons(),
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
                                exp = rf"{ip[0]}\.{ip[1]}\.{ip[2]}\.\d+"
                            case "16":
                                exp = rf"{ip[0]}\.{ip[1]}\.\d+\.\d+"
                            case "24":
                                exp = rf"{ip[0]}\.\d+\.\d+\.\d+"
                            case "32":
                                exp = rf"{ip[0]}\.{ip[1]}\.{ip[2]}\.{ip[3]}"
                            case _:
                                await msg.edit(
                                    embed=self.messageLib.standard_embed(
                                        title="Error",
                                        description=f"Mask `{mask}` not a valid mask",
                                        color=RED,
                                    ),
                                    components=self.messageLib.buttons(),
                                )
                                return

                        pipeline[0]["$match"]["$and"].append(
                            {"ip": {"$regex": f"^{exp}$", "$options": "i"}}
                        )
                    else:
                        await msg.edit(
                            embed=self.messageLib.standard_embed(
                                title="Error",
                                description=f"Mask `{mask}` not a valid mask",
                                color=RED,
                            ),
                            components=self.messageLib.buttons(),
                        )
                        return
                else:
                    pipeline[0]["$match"]["$and"].append({"ip": ip})
            if country is not None:
                pipeline[0]["$match"]["$and"].append({"geo": {"$exists": True}})
                pipeline[0]["$match"]["$and"].append(
                    {"geo.country": {"$regex": f"^{country}$", "$options": "i"}}
                )
            if whitelisted is not None:
                pipeline[0]["$match"]["$and"].append({"whitelist": whitelisted})

            total = self.databaseLib.count(pipeline)

            if total == 0:
                await msg.edit(
                    embed=self.messageLib.standard_embed(
                        title="No servers found",
                        description="Try again with different parameters",
                        color=RED,
                    ),
                    components=self.messageLib.buttons(),
                )
                self.logger.debug(f"No servers found, saving pipeline to file")
                with open("pipeline.json", "w") as f:
                    f.write(json.dumps(pipeline, indent=4))
                return

            # check how many servers match
            msg = await msg.edit(
                embed=self.messageLib.standard_embed(
                    title="Finding servers...",
                    description=f"Found {total} servers",
                    color=BLUE,
                ),
                components=self.messageLib.buttons(),
            )
            sentry_sdk.add_breadcrumb(
                category="commands", message=f"Found {total} servers"
            )

            await self.messageLib.async_load_server(
                index=0,
                pipeline=pipeline,
                msg=msg,
            )
        except Exception as err:
            if "403|Forbidden" in str(err):
                await msg.delete(context=ctx)
                return
            else:
                self.logger.error(
                    f"Error: {err}\nFull traceback: {traceback.format_exc()}"
                )
                sentry_sdk.capture_exception(err)

                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="An error occurred",
                        description="Please try again later",
                        color=RED,
                    ),
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
                type=OptionType.STRING,
                required=True,
            ),
            SlashCommandOption(
                name="port",
                description="The port of the server",
                type=OptionType.INTEGER,
                required=False,
                min_value=1,
                max_value=65535,
            ),
        ],
    )
    async def ping(self, ctx: SlashContext, ip: str, port: int = None):
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
                embed=self.messageLib.standard_embed(
                    title="Loading...",
                    description="Loading server 1 of 1",
                    color=BLUE,
                ),
                components=self.messageLib.buttons(),
            )

            # test if the server is online
            if self.databaseLib.count([{"$match": pipeline}]) == 0:
                doc = self.serverLib.update(host=ip, port=port)
                if doc is None:
                    await ctx.send(
                        embed=self.messageLib.standard_embed(
                            title="An error occurred",
                            description="The server is offline",
                            color=RED,
                        ),
                        ephemeral=True,
                    )
                    await msg.delete(context=ctx)
                    return
                else:
                    pipeline = doc
            else:
                pipeline = [{"$match": pipeline}]

            # get the server
            await self.messageLib.async_load_server(
                index=0,
                pipeline=pipeline,
                msg=msg,
            )
        except Exception as err:
            if "403|Forbidden" in str(err):
                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="An error occurred",
                        description="Wrong channel for this bot",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                await msg.delete(context=ctx)
                return
            self.logger.error(f"Error: {err}\nFull traceback: {traceback.format_exc()}")
            sentry_sdk.capture_exception(err)

            await ctx.send(
                embed=self.messageLib.standard_embed(
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
                type=OptionType.STRING,
                required=False,
                min_length=2,
                max_length=2,
            ),
        ],
    )
    async def streamers(self, ctx: SlashContext, lang: str = None):
        try:
            msg = await ctx.send(
                embed=self.messageLib.standard_embed(
                    title="Loading...",
                    description="Loading...",
                    color=BLUE,
                ),
            )

            # test if 'client_id' and 'client_secret' are not None
            if self.client_id == "" or self.client_secret == "":
                # spawn a modal asking for client id and secret
                client_id = ShortText(
                    label="Client ID",
                    placeholder="Client ID",
                    custom_id="clientId",
                    min_length=1,
                    max_length=100,
                )
                client_secret = ShortText(
                    label="Client Secret",
                    placeholder="Client Secret",
                    custom_id="clientSecret",
                    min_length=1,
                    max_length=100,
                )

                modal = Modal(
                    client_id,
                    client_secret,
                    title="Auth",
                )

                await ctx.send_modal(modal)

                modal_ctx = ctx
                try:
                    modal_ctx = await ctx.bot.wait_for_modal(timeout=90, modal=modal)
                except asyncio.TimeoutError:
                    self.logger.print(f"Timed out")
                    await modal_ctx.send(
                        embed=self.messageLib.standard_embed(
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
                    embed=self.messageLib.standard_embed(
                        title="Success",
                        description="Got the client id and secret",
                        color=GREEN,
                    ),
                    ephemeral=True,
                )
            else:
                client_id = self.client_id
                client_secret = self.client_secret

            if (client_id == "" or client_secret == "") or (
                client_id is None or client_secret is None
            ):
                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="Error",
                        description="Client ID or Client Secret is empty",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return

            streams = await self.twitchLib.async_get_streamers(
                client_id=client_id,
                client_secret=client_secret,
                lang=lang,
            )

            if streams is None or streams == []:
                await msg.edit(
                    embed=self.messageLib.standard_embed(
                        title="Error",
                        description="No streams found",
                        color=RED,
                    ),
                )
                return
            else:
                msg = await msg.edit(
                    embed=self.messageLib.standard_embed(
                        title="Loading...",
                        description="Found " + str(len(streams)) + " streams",
                        color=BLUE,
                    ),
                )

            names = [i["user_name"] for i in streams]

            # get the servers
            # by case-insensitive name of streamer and players.sample is greater than 0
            pipeline = [
                base_match,
                {
                    "$project": {
                        "_id": 1,
                    }
                },
            ]

            total = self.databaseLib.count(pipeline)
            self.logger.debug(f"Got {total} servers")
            msg = await msg.edit(
                embed=self.messageLib.standard_embed(
                    title="Loading...",
                    description="Found " + str(total) + " servers in the database",
                    color=BLUE,
                ),
            )

            _ids = [i["_id"] for i in self.databaseLib.aggregate(pipeline)]

            self.logger.debug(f"Got {len(_ids)} ids")

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
                    embed=self.messageLib.standard_embed(
                        title="Error",
                        description="No servers found",
                        color=RED,
                    ),
                )
                return
            else:
                msg = await msg.edit(
                    embed=self.messageLib.standard_embed(
                        title="Loading...",
                        description="Loading 1 of " + str(total),
                        color=BLUE,
                    ),
                )

            await self.messageLib.async_load_server(
                pipeline=pipeline,
                index=0,
                msg=msg,
            )
        except Exception as err:
            if "403|Forbidden" in str(err):
                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="An error occurred",
                        description="Wrong channel for this bot",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return

            self.logger.error(f"Error: {err}\nFull traceback: {traceback.format_exc()}")
            sentry_sdk.capture_exception(err)

            await ctx.send(
                embed=self.messageLib.standard_embed(
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
                type=OptionType.ATTACHMENT,
                required=True,
            ),
            SlashCommandOption(
                name="delimiter",
                description="The delimiter to use",
                type=OptionType.STRING,
                required=True,
                choices=[
                    SlashCommandChoice(
                        name="comma",
                        value=",",
                    ),
                    SlashCommandChoice(
                        name="semicolon",
                        value=";",
                    ),
                    SlashCommandChoice(
                        name="space",
                        value=" ",
                    ),
                    SlashCommandChoice(
                        name="line break",
                        value="\n",
                    ),
                ],
            ),
        ],
    )
    async def scan(self, ctx: SlashContext, file: Attachment, delimiter: str):
        try:
            with sentry_sdk.configure_scope() as scope:
                scope.add_attachment(filename=file.filename, path=file.url)

            await ctx.defer(ephemeral=True)

            # make sure the bot is running on linux
            if os.name != "posix":
                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="Error",
                        description="This command only works on Linux hosts",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return
            await ctx.send(
                embed=self.messageLib.standard_embed(
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
                        embed=self.messageLib.standard_embed(
                            title="Error",
                            description="Invalid subnet: " + line,
                            color=RED,
                        ),
                        ephemeral=True,
                    )
                    return

            # send the user how many ranges we're scanning
            await ctx.send(
                embed=self.messageLib.standard_embed(
                    title="Loading...",
                    description="Scanning " + str(len(lines)) + " ranges",
                    color=GREEN,
                ),
                ephemeral=True,
            )

            def _scan(ip_ranges):
                from pyutils.scanner import Scanner

                scan_func = self.Scanner(
                    logger_func=self.logger, serverLib=self.serverLib
                )
                scan_func.start(ip_ranges=ip_ranges)

            try:
                from pyutils.scanner import Scanner
            except ImportError:
                await ctx.send(
                    embed=self.messageLib.standard_embed(
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
                    embed=self.messageLib.standard_embed(
                        title="Success",
                        description="Started the scanner",
                        color=GREEN,
                    ),
                    ephemeral=True,
                )
        except Exception as err:
            self.logger.error(f"Error: {err}\nFull traceback: {traceback.format_exc()}")
            sentry_sdk.capture_exception(err)

            await ctx.send(
                embed=self.messageLib.standard_embed(
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
    async def stats(self, ctx: SlashContext):
        """
        Get stats about the server, ...
        """
        msg = None
        await ctx.defer()

        try:
            self.logger.debug(f"Getting stats")
            main_embed = self.messageLib.standard_embed(
                title="Stats",
                description="General stats about the database",
                color=BLUE,
            )

            msg = await ctx.send(
                embed=main_embed,
            )

            # get the stats
            total_servers = self.databaseLib.col.count_documents({})

            main_embed.add_field(
                name="Servers",
                value=f"{total_servers:,}",
                inline=True,
            )
            msg = await msg.edit(
                embed=main_embed,
            )

            # get the total player count, ignoring servers with over 150k players and less than one player,
            # and the version name is not Unknown, or UNKNOWN or null
            pipeline = [
                {
                    "$match": {
                        "$and": [
                            {"players.online": {"$lt": 150000}},
                            {"players.online": {"$gt": 0}},
                            {"version.name": {"$nin": ["Unknown", "UNKNOWN", None]}},
                        ]
                    }
                },
                {"$group": {"_id": None, "total": {"$sum": "$players.online"}}},
            ]
            total_players = self.databaseLib.aggregate(pipeline).try_next()["total"]

            main_embed.add_field(
                name="Players",
                value=f"{total_players:,}",
                inline=True,
            )
            msg = await msg.edit(
                embed=main_embed,
            )

            # get the total number of players in players.sample
            pipeline = [
                {"$unwind": "$players.sample"},
                {"$group": {"_id": None, "total": {"$sum": 1}}},
            ]
            total_sample_players = self.databaseLib.aggregate(pipeline).try_next()[
                "total"
            ]

            main_embed.add_field(
                name="Logged Players",
                value=f"{total_sample_players:,} ({round(total_sample_players / total_players * 100, 2)}%)",
                inline=True,
            )
            msg = await msg.edit(
                embed=main_embed,
            )

            # get the number of players which do not have a player id of "00000000-0000-0000-0000-000000000000"
            pipeline = [
                {
                    "$match": {
                        "players.sample.id": {
                            "$ne": "00000000-0000-0000-0000-000000000000"
                        }
                    }
                },
                {"$group": {"_id": None, "total": {"$sum": 1}}},
            ]
            total_real_players = self.databaseLib.aggregate(pipeline).try_next()[
                "total"
            ]

            main_embed.add_field(
                name="Real Players",
                value=f"{total_real_players:,} ({round(total_real_players / total_sample_players * 100, 2)}%)",
                inline=True,
            )
            msg = await msg.edit(
                embed=main_embed,
            )

            # get the number of players which have a player id of "00000000-0000-0000-0000-000000000000"
            pipeline = [
                {
                    "$match": {
                        "players.sample.id": "00000000-0000-0000-0000-000000000000"
                    }
                },
                {"$group": {"_id": None, "total": {"$sum": 1}}},
            ]
            total_fake_players = self.databaseLib.aggregate(pipeline).try_next()[
                "total"
            ]

            main_embed.add_field(
                name="Fake Players",
                value=f"{total_fake_players:,} ({round(total_fake_players / total_sample_players * 100, 2)}%)",
                inline=True,
            )
            msg = await msg.edit(
                embed=main_embed,
            )

            # top three orgs
            pipeline = [
                {"$match": {"org": {"$ne": None}}},
                {"$group": {"_id": "$org", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 3},
            ]
            top_three_orgs = list(self.databaseLib.aggregate(pipeline))

            main_embed.add_field(
                name="Top Three Orgs",
                value="```css\n"
                + "\n".join(
                    [
                        f"{i['_id']}: {round(i['count'] / total_servers * 100, 2)}%"
                        for i in top_three_orgs
                    ]
                )
                + "\n```",
                inline=True,
            )
            msg = await msg.edit(
                embed=main_embed,
            )

            # get the five most common server version names
            pipeline = [
                {
                    "$match": {
                        "$and": [
                            {"players.online": {"$lt": 150000}},
                            {"players.online": {"$gt": 0}},
                            {"version.name": {"$nin": ["Unknown", "UNKNOWN", None]}},
                        ]
                    }
                },
                {"$group": {"_id": "$version.name", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 5},
            ]
            top_five_versions = list(self.databaseLib.aggregate(pipeline))

            main_embed.add_field(
                name="Top Five Versions",
                value="```css\n"
                + "\n".join(
                    [
                        f"{i['_id']}: {round(i['count'] / total_servers * 100, 2)}%"
                        for i in top_five_versions
                    ]
                )
                + "\n```",
                inline=True,
            )
            msg = await msg.edit(
                embed=main_embed,
            )

            # get the five most common server version ids
            pipeline = [
                {
                    "$match": {
                        "$and": [
                            {"players.online": {"$lt": 150000}},
                            {"players.online": {"$gt": 0}},
                            {"version.name": {"$nin": ["Unknown", "UNKNOWN", None]}},
                        ]
                    }
                },
                {"$group": {"_id": "$version.protocol", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 5},
            ]
            top_five_version_ids = list(self.databaseLib.aggregate(pipeline))

            main_embed.add_field(
                name="Top Five Version IDs",
                value="```css\n"
                + "\n".join(
                    [
                        f"{self.textLib.protocol_str(i['_id'])}: {round(i['count'] / total_servers * 100, 2)}%"
                        for i in top_five_version_ids
                    ]
                )
                + "\n```",
                inline=True,
            )
            msg = await msg.edit(
                embed=main_embed,
            )

            # get the percentage of servers which are cracked (cracked == True)
            pipeline = [
                {"$match": {"cracked": True}},
                {"$group": {"_id": None, "count": {"$sum": 1}}},
            ]
            cracked = list(self.databaseLib.aggregate(pipeline))[0]["count"]

            main_embed.add_field(
                name="Cracked",
                value=self.textLib.percent_bar(cracked, total_servers),
                inline=True,
            )
            msg = await msg.edit(
                embed=main_embed,
            )

            # get the percentage of servers which have favicons (hasFavicon == True)
            pipeline = [
                {"$match": {"hasFavicon": True}},
                {"$group": {"_id": None, "count": {"$sum": 1}}},
            ]
            has_favicon = list(self.databaseLib.aggregate(pipeline))

            main_embed.add_field(
                name="Has Favicon",
                value=self.textLib.percent_bar(has_favicon[0]["count"], total_servers),
                inline=True,
            )
            msg = await msg.edit(
                embed=main_embed,
            )

            # get the percentage of servers which have forge mods (hasForgeData == True)
            pipeline = [
                {"$match": {"hasForgeData": True}},
                {"$group": {"_id": None, "count": {"$sum": 1}}},
            ]
            has_forge_data = list(self.databaseLib.aggregate(pipeline))[0]["count"]

            main_embed.add_field(
                name="Has Forge Data",
                value=self.textLib.percent_bar(has_forge_data, total_servers),
                inline=True,
            )
            msg = await msg.edit(
                embed=main_embed,
            )

            # get the percentage of servers that are whitelisted
            pipeline = [
                {"$match": {"whitelist": {"$exists": True}}},
                {"$group": {"_id": None, "count": {"$sum": 1}}},
            ]
            have_whitelist = list(self.databaseLib.aggregate(pipeline))[0]["count"]

            pipeline = [
                {"$match": {"whitelist": True}},
                {"$group": {"_id": None, "count": {"$sum": 1}}},
            ]
            whitelist_enabled = list(self.databaseLib.aggregate(pipeline))[0]["count"]

            main_embed.add_field(
                name="Whitelisted",
                value=self.textLib.percent_bar(whitelist_enabled, have_whitelist),
                inline=True,
            )
            msg = await msg.edit(
                embed=main_embed,
            )

            if self.cstats not in ["", "...", None]:
                # add the custom text
                main_embed.add_field(
                    name="Custom Text",
                    value=self.cstats,
                    inline=False,
                )
                await msg.edit(
                    embed=main_embed,
                )
        except Exception as err:
            if "403|Forbidden" in str(err):
                await msg.delete(context=ctx)
                return

            self.logger.error(f"Error: {err}\nFull traceback: {traceback.format_exc()}")
            sentry_sdk.capture_exception(err)

            await ctx.send(
                embed=self.messageLib.standard_embed(
                    title="Error",
                    description="An error occurred while trying to get stats",
                    color=RED,
                ),
                ephemeral=True,
            )

    @slash_command(
        name="graph",
        description="Get the stats but as a graph",
    )
    async def graph(self, ctx: SlashContext):
        try:
            import pyutils.graph as graph

            await ctx.defer()
            embed = self.messageLib.standard_embed(
                title="Graph",
                description=f"Graphs of the database\n{self.cstats}",
                color=BLUE,
            )
            msg = await ctx.send(
                embed=embed,
            )

            # get the total number of servers
            total_servers = self.databaseLib.col.count_documents({})

            # get the top 20 versions
            pipeline = [
                {
                    "$match": {
                        "$and": [
                            {"players.online": {"$lt": 150000}},
                            {"players.online": {"$gt": 0}},
                            {"version.name": {"$nin": ["Unknown", "UNKNOWN", None]}},
                        ]
                    }
                },
                {
                    "$group": {
                        "_id": "$version.name",
                        "label": {"$first": "$version.name"},
                        "size": {"$sum": 1},
                    }
                },
                {"$sort": {"size": -1}},
                {"$limit": 20},
            ]
            versions = list(self.databaseLib.aggregate(pipeline))

            vers_fig = graph.draw_pie(versions, "Versions")
            self.logger.debug("Made version graph")

            # hide the labels before saving
            vers_fig.update_layout(
                showlegend=False,
            )
            vers_fig.write_image("assets/graphs/vers.png")
            # show the labels again
            vers_fig.update_layout(
                showlegend=True,
            )

            msg = await msg.edit(
                embed=embed,
                files=[File("assets/graphs/vers.png")],
            )

            # get the percentage of servers that are cracked
            pipeline = [
                {"$match": {"cracked": True}},
                {"$group": {"_id": None, "count": {"$sum": 1}}},
            ]
            cracked = (
                list(self.databaseLib.aggregate(pipeline))[0]["count"] / total_servers
            )

            # get the percentage of servers that have a favicon
            pipeline = [
                {"$match": {"hasFavicon": True}},
                {"$group": {"_id": None, "count": {"$sum": 1}}},
            ]
            has_favicon = (
                list(self.databaseLib.aggregate(pipeline))[0]["count"] / total_servers
            )

            # get the percentage of servers that have forge data
            pipeline = [
                {"$match": {"hasForgeData": True}},
                {"$group": {"_id": None, "count": {"$sum": 1}}},
            ]
            has_forge_data = (
                list(self.databaseLib.aggregate(pipeline))[0]["count"] / total_servers
            )

            # get the percentage of servers that are whitelisted
            pipeline = [
                {"$match": {"whitelist": True}},
                {"$group": {"_id": None, "count": {"$sum": 1}}},
            ]
            is_whitelist = (
                list(self.databaseLib.aggregate(pipeline))[0]["count"] / total_servers
            )

            # get the percentage of servers that enforce secure chat
            pipeline = [
                {"$match": {"enforcesSecureChat": True}},
                {"$group": {"_id": None, "count": {"$sum": 1}}},
            ]
            enforces_secure_chat = (
                list(self.databaseLib.aggregate(pipeline))[0]["count"] / total_servers
            )

            data = [
                {"label": "Cracked", "size": cracked * 100},
                {"label": "Has Favicon", "size": has_favicon * 100},
                {"label": "Has Forge Data", "size": has_forge_data * 100},
                {"label": "Whitelisted", "size": is_whitelist * 100},
                {"label": "Enforces Secure Chat", "size": enforces_secure_chat * 100},
            ]
            # sort data
            data = sorted(data, key=lambda pnt: pnt["size"], reverse=True)
            misc_fig = graph.draw_bar(data, "Misc")
            self.logger.debug("Made misc graph")
            misc_fig.write_image("assets/graphs/misc.png")
            msg = await msg.edit(
                embed=embed,
                files=[File("assets/graphs/vers.png"), File("assets/graphs/misc.png")],
            )

            # get the top 2000 servers based on players.online
            pipeline = [
                {
                    "$match": {
                        "$and": [
                            {"players.online": {"$lt": 150000}},
                            {"players.online": {"$gt": 0}},
                            {"version.name": {"$nin": ["Unknown", "UNKNOWN", None]}},
                            {"geo.lat": {"$exists": True}},
                            {"geo.lon": {"$exists": True}},
                        ]
                    }
                },
                {"$sort": {"players.online": -1}},
                {"$limit": 2000},
                {
                    "$group": {
                        "_id": "$ip",
                        "label": {"$first": "$ip"},
                        "size": {"$first": "$players.online"},
                        "lat": {"$first": "$geo.lat"},
                        "lon": {"$first": "$geo.lon"},
                        "x": {"$max": "$players.max"},
                        "y": {"$sum": "$players.online"},
                    }
                },
            ]
            top_servers = list(self.databaseLib.aggregate(pipeline))

            map_fig = graph.draw_geoheatmap(top_servers, "Top Servers")
            self.logger.debug("Made map graph")
            map_fig.write_image("assets/graphs/map.png")
            msg = await msg.edit(
                embed=embed,
                files=[
                    File("assets/graphs/vers.png"),
                    File("assets/graphs/misc.png"),
                    File("assets/graphs/map.png"),
                ],
            )

            # get the sum of all the server's players.online for each country
            pipeline = [
                {
                    "$match": {
                        "$and": [
                            {"players.online": {"$lt": 150000}},
                            {"players.online": {"$gt": 0}},
                            {"version.name": {"$nin": ["Unknown", "UNKNOWN", None]}},
                            {"geo.country": {"$exists": True}},
                        ]
                    }
                },
                {
                    "$group": {
                        "_id": "$geo.country",
                        "count": {"$sum": "$players.online"},
                    }
                },
            ]
            country_players = list(self.databaseLib.aggregate(pipeline))

            for i, country in enumerate(country_players):
                country_players[i]["label"] = country["_id"]
                country_players[i]["size"] = country["count"]
                country_players[i]["ISO-3"] = country_converter.convert(
                    names=country["_id"],
                    to="ISO3",
                )

            world_fig = graph.draw_choropleth(country_players, "Players Per Country")

            world_fig.write_image("assets/graphs/world.png")
            msg = await msg.edit(
                embed=embed,
                files=[
                    File("assets/graphs/vers.png"),
                    File("assets/graphs/misc.png"),
                    File("assets/graphs/map.png"),
                    File("assets/graphs/world.png"),
                ],
            )

            # get the top 2000 servers based on players.online# get the top 2000 servers based on players.online
            pipeline = [
                {
                    "$match": {
                        "$and": [
                            {"players.online": {"$lt": 150000}},
                            {"players.online": {"$gt": 0}},
                            {"players.max": {"$gt": 0}},
                            {"players.max": {"$lt": 200000}},
                            {"version.name": {"$nin": ["Unknown", "UNKNOWN", None]}},
                            {"geo.lat": {"$exists": True}},
                            {"geo.lon": {"$exists": True}},
                        ]
                    }
                },
                {"$sort": {"players.online": -1}},
                {"$limit": 2000},
                {
                    "$group": {
                        "_id": "$ip",
                        "label": {"$first": "$ip"},
                        "size": {"$first": "$players.online"},
                        "lat": {"$first": "$geo.lat"},
                        "lon": {"$first": "$geo.lon"},
                        "x": {"$max": "$players.max"},
                        "y": {"$sum": "$players.online"},
                    }
                },
            ]
            top_servers = list(self.databaseLib.aggregate(pipeline))

            top_fig = graph.draw_scatter(top_servers, "Top Servers")
            top_fig.update_layout(
                xaxis_title="Max Players",
                yaxis_title="Online Players",
            )
            self.logger.debug("Made top graph")
            top_fig.write_image("assets/graphs/top.png")
            msg = await msg.edit(
                embed=embed,
                files=[
                    File("assets/graphs/vers.png"),
                    File("assets/graphs/misc.png"),
                    File("assets/graphs/map.png"),
                    File("assets/graphs/world.png"),
                    File("assets/graphs/top.png"),
                ],
            )

            # save the graphs to an html file
            graph.save_graphs_html(
                vers_fig, misc_fig, map_fig, world_fig, top_fig, filename="test.html"
            )
            self.logger.debug("Saved graphs to html file")

            if self.upload_serv is not None and self.upload_serv != "...":
                # upload the html file to a server
                with open("test.html", "r") as f:
                    html_string = f.read()
                    r = requests.post(
                        self.upload_serv,
                        files={"file": ("graph.html", html_string, "text/html")},
                    )
                    print(r.status_code)
        except Exception as err:
            if "403|Forbidden" in str(err):
                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="Error",
                        description="Wrong channel for this bot",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return

            self.logger.error(f"Error: {err}\nFull traceback: {traceback.format_exc()}")
            sentry_sdk.capture_exception(err)

            await ctx.send(
                embed=self.messageLib.standard_embed(
                    title="Error",
                    description="An error occurred while trying to get the graphs",
                    color=RED,
                ),
                ephemeral=True,
            )

    @slash_command(
        name="player",
        description="Get stats about a player",
        options=[
            SlashCommandOption(
                name="player",
                description="The player to get stats about (uuid or name)",
                type=OptionType.STRING,
                required=True,
            ),
        ],
    )
    async def player(self, ctx: SlashContext, player: str):
        """
        Returns all servers that have this player logged on it,
        provides the server ip, port, and last time the server and player were online
        """
        try:
            self.logger.debug(f"Getting player: {player}")
            if len(player) > 16:
                # player is a uuid
                uuid = player
            else:
                # player is a name
                uuid = await self.playerLib.async_get_uuid(player)

            await ctx.defer()

            # get the profile
            profile = await self.playerLib.async_get_profile(uuid)

            if not profile:
                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="Error",
                        description="Player not found",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return

            uuid = profile["id"].replace("-", "")
            uuid = f"{uuid[:8]}-{uuid[8:12]}-{uuid[12:16]}-{uuid[16:20]}-{uuid[20:]}"

            pipeline = [
                {
                    "$match": {
                        "players.sample.id": uuid,
                    }
                },
                {
                    "$project": {
                        "ip": 1,
                        "port": 1,
                        "lastSeen": 1,
                        "players": {
                            "$filter": {
                                "input": "$players.sample",
                                "as": "player",
                                "cond": {"$eq": ["$$player.id", uuid]},
                            }
                        },
                    }
                },
            ]

            # get the servers
            servers = list(self.databaseLib.aggregate(pipeline))

            if len(servers) == 0:
                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="Error",
                        description="No servers found",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return

            # sort the servers by lastSeen
            servers = sorted(servers, key=lambda serv: serv["lastSeen"], reverse=True)

            header = (
                "```\n|"
                + "Server:Port".center(22)
                + "|"
                + "Server Online".center(17)
                + "|"
                + "Player Online".center(17)
                + "|"
                + "\n|"
                + "-" * 22
                + "|"
                + "-" * 17
                + "|"
                + "-" * 17
                + "|"
            )
            footer = "\n```"

            server_list = []

            for i, server in enumerate(servers):
                ip = server["ip"]
                port = server["port"]
                player = server["players"][0]
                lastSeen_ply = player["lastSeen"]
                lastSeen_serv = server["lastSeen"]

                lastSeen_serv = datetime.fromtimestamp(
                    lastSeen_serv, tz=datetime.now().astimezone().tzinfo
                )
                lastSeen_serv = lastSeen_serv.strftime("%b %d %y %H:%M")

                lastSeen_ply = datetime.fromtimestamp(
                    lastSeen_ply, tz=datetime.now().astimezone().tzinfo
                )
                lastSeen_ply = lastSeen_ply.strftime("%b %d %y %H:%M")

                text = (
                    "|"
                    + f"{ip}:{port}".center(22)
                    + "|"
                    + lastSeen_serv.center(17)
                    + "|"
                    + lastSeen_ply.center(17)
                    + "|"
                )
                server_list.append(text)

            server_list = "\n".join(server_list)

            page = Paginator.create_from_string(
                ctx.bot, server_list, timeout=180, prefix=header, suffix=footer
            )

            await page.send(ctx)
        except Exception as err:
            if "403|Forbidden" in str(err):
                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="Error",
                        description="Wrong channel for this bot",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return

            self.logger.error(f"Error: {err}\nFull traceback: {traceback.format_exc()}")
            sentry_sdk.capture_exception(err)

            await ctx.send(
                embed=self.messageLib.standard_embed(
                    title="Error",
                    description="An error occurred while trying to get the player",
                    color=RED,
                ),
                ephemeral=True,
            )
            return
