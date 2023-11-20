"""Useful functions for sending messages to the user."""
import base64
import datetime
import io
import socket
import time
import traceback
from typing import List, Optional, Tuple

import aiohttp
import interactions
from bson import json_util
from interactions import ActionRow, ComponentContext, ContextMenuContext, File
# noinspection PyProtectedMember
from sentry_sdk import trace

from Extensions.Colors import *
from .database import Database
from .logger import Logger
from .server import Server
from .text import Text
from .twitch import Twitch


class Message:
    def __init__(
        self,
        logger: "Logger",
        db: "Database",
        text: "Text",
        server: "Server",
        twitch: "Twitch",
    ):
        self.logger = logger
        self.db = db
        self.text = text
        self.server = server
        self.twitch = twitch

    @staticmethod
    def buttons(*args: bool | str) -> List[ActionRow]:
        """Return disabled buttons (True = disabled)

        Args:
            *args (bool | str): The buttons to disable and the link to MCStatus.io
                order: next, previous, jump, update, players, sort, join

        Returns:
            [
                interactions.ActionRow(): Next, Previous, Jump to, Update
                interactions.ActionRow(): Show Players
                interactions.StringSelectMenu(): Sort
                interactions.Button(): Mods
            ]
        """
        if len(args) != 9:
            disabled = list([True] * 9)
        else:
            disabled = list(args)

        # button: Next, Previous, Show Players
        rows = [
            interactions.ActionRow(
                interactions.Button(
                    style=interactions.ButtonStyle.PRIMARY,
                    emoji="⬅️",
                    custom_id="previous",
                    disabled=disabled[1],
                ),
                interactions.Button(
                    style=interactions.ButtonStyle.PRIMARY,
                    emoji="➡️",
                    custom_id="next",
                    disabled=disabled[0],
                ),
                interactions.Button(
                    style=interactions.ButtonStyle.PRIMARY,
                    label="Jump",
                    custom_id="jump",
                    disabled=disabled[2],
                ),
            ),
            interactions.ActionRow(
                interactions.Button(
                    style=interactions.ButtonStyle.SECONDARY,
                    label="Players",
                    custom_id="players",
                    disabled=disabled[4],
                ),
                interactions.Button(
                    style=interactions.ButtonStyle.SECONDARY,
                    emoji="🔄",
                    custom_id="update",
                    disabled=disabled[3],
                ),
                interactions.Button(
                    style=interactions.ButtonStyle.DANGER,
                    label="Sort",
                    custom_id="sort",
                    disabled=disabled[5],
                ),
            ),
            interactions.ActionRow(
                interactions.Button(
                    style=interactions.ButtonStyle.SECONDARY,
                    label="Mods",
                    custom_id="mods",
                    disabled=disabled[6],
                ),
                interactions.Button(
                    style=interactions.ButtonStyle.DANGER,
                    label="Join",
                    custom_id="join",
                    disabled=disabled[7],
                ),
                interactions.Button(
                    style=interactions.ButtonStyle.SECONDARY,
                    label="Streams",
                    custom_id="streams",
                    disabled=disabled[8],
                ),
            ),
        ]

        return rows

    async def async_embed(
        self,
        pipeline: list | dict,
        index: int,
        fast=True,
    ) -> Optional[dict]:
        """Return an embed

        Args:
            pipeline (list): The pipeline to use, or the server data
            index (int): The index of the embed
            fast (bool): Whether to return just the database values

        Returns:
            {
                "embed": interactions.Embed, # The embed
                "components": [interactions.ActionRow], # The buttons
            }
        """
        start = time.perf_counter()

        data = {"ip": "n/a", "description": {"text": "n/a"}}
        try:
            if isinstance(pipeline, dict):
                self.logger.print("Server data provided")
                # server is not in db, and we got the server data
                data = self.text.update_dict(data, pipeline)
                pipeline = {
                    "your mother": "large",
                }
                total_servers = 1

                if data is None or data == {}:
                    return {
                        "embed": self.standard_embed(
                            title="Error",
                            description="No server found",
                            color=YELLOW,
                        ),
                        "components": self.buttons(),
                    }
            else:
                # server is in db
                total_servers = self.logger.timer(self.db.count, pipeline)

                if total_servers == 0:
                    self.logger.print("No servers found")
                    return {
                        "embed": self.standard_embed(
                            title="Error",
                            description="No servers found",
                            color=YELLOW,
                        ),
                        "components": self.buttons(),
                    }

                if index >= total_servers:
                    index = 0

                doc = self.logger.timer(self.db.get_doc_at_index, pipeline, index)

                data = self.text.update_dict(
                    data,
                    doc,
                )

                if data is None:
                    self.logger.print("No server found in db")
                    return {
                        "embed": self.standard_embed(
                            title="Error",
                            description="No server found",
                            color=YELLOW,
                        ),
                        "components": self.buttons(),
                    }

            # get the server status
            is_online = "🔴"
            data["cracked"] = None
            # if we just have server info and we want a quick response
            if type(pipeline) is dict and fast:
                # set all values to default
                data["description"] = {"text": "..."}
                data["players"] = {"online": 0, "max": 0}
                data["version"] = {"name": "...", "protocol": 0}
                data["favicon"] = None
                data["cracked"] = None
                data["hasForgeData"] = False
                data["lastSeen"] = 0
            # if we have server ip and we want a quick response
            elif not fast:
                try:
                    status = self.logger.timer(
                        self.server.update, host=data["ip"], port=data["port"]
                    )

                    if status is None:
                        # server is offline
                        data["cracked"] = None
                        data["description"] = self.text.motd_parse(data["description"])
                        self.logger.debug("Server is offline")
                    else:
                        self.logger.debug("Server is online")
                        # server is online
                        data.update(status)
                        self.logger.info(f"Got status {data}")

                    # mark online if the server was lastSeen within 5 minutes
                    if data["lastSeen"] > time.time() - 300:
                        is_online = "🟢"

                    # get the domain name of the ip
                    try:
                        domain = socket.gethostbyaddr(data["ip"])[0]
                        if domain != data["ip"] and data["ip"] not in domain:
                            data["hostname"] = domain
                    except socket.herror:
                        pass
                except Exception as e:
                    self.logger.print(f"Full traceback: {traceback.format_exc()}")
                    self.logger.error("Error: " + str(e))
            # if we have server ip and we want a full response
            else:
                # isonline is yellow
                is_online = "🟡"
                if "description" in data.keys():
                    data["description"] = self.text.motd_parse(data["description"])
                else:
                    data["description"] = {"text": "n/a"}

            # get the server icon
            if is_online == "🟢" and "favicon" in data.keys():
                self.logger.debug("Adding favicon")
                bits = (
                    data["favicon"].split(",")[1]
                    if "," in data["favicon"]
                    else data["favicon"]
                )
                with open("assets/favicon.png", "wb") as f:
                    f.write(base64.b64decode(bits))
            else:
                self.logger.debug("Adding default favicon")
                # copy the bytes from 'DefFavicon.png' to 'favicon.png'
                with open("assets/DefFavicon.png", "rb") as f, open(
                    "assets/favicon.png", "wb"
                ) as f2:
                    f2.write(f.read())

            # create the embed
            self.logger.debug("Creating embed")
            data["description"] = self.text.motd_parse(data["description"])
            domain = ""
            if "hostname" in data:
                domain = f"**Hostname:** `{data['hostname']}`\n"
            embed = self.standard_embed(
                title=f"{is_online} {data['ip']}:{data['port']}",
                description=f"{domain}\n```ansi\n{self.text.color_ansi(str(data['description']['text']))}\n```",
                color=(GREEN if is_online == "🟢" else PINK)
                if is_online != "🟡"
                else None,
            ).set_image(url="attachment://favicon.png")

            # set the footer to say the index, pipeline, and total servers
            embed.set_footer(
                f"Showing {index + 1} of {total_servers} servers",
            )
            embed.timestamp = self.text.time_now()
            with open("pipeline.ason", "w") as f:
                f.write(json_util.dumps(pipeline))

            # add the version
            embed.add_field(
                name="Version",
                value=f"{self.text.c_filter(data['version']['name'])} ({data['version']['protocol']})",
                inline=True,
            )

            # add the player count
            embed.add_field(
                name="Players",
                value=f"{data['players']['online']}/{data['players']['max']} ({len(data['players']['sample']) if 'sample' in data['players'] else '-'})",
                inline=True,
            )

            # is cracked
            embed.add_field(
                name="Cracked",
                value="Yes" if data["cracked"] else "No",
                inline=True,
            )

            # is modded
            embed.add_field(
                name="Modded",
                value=(
                    "Yes"
                    if data["hasForgeData"] or "modpackData" in data.keys()
                    else "No"
                ),
                inline=True,
            )

            # hostname/org
            if "geo" in data.keys() and "hostname" in data["geo"].keys():
                embed.add_field(
                    name="Hostname",
                    value=data["hostname"],
                    inline=True,
                )
            if "org" in data.keys():
                embed.add_field(
                    name="Organisation",
                    value=data["org"],
                    inline=True,
                )

            # last online
            stamp: datetime.datetime = datetime.datetime.utcfromtimestamp(
                data["lastSeen"]
            )
            embed.add_field(
                name="Time since last scan",
                value=self.text.time_ago(stamp),
                inline=True,
            )

            # geolocation
            if "geo" in data.keys():
                city = (
                    data["geo"]["city"] if "city" in data["geo"].keys() else "Unknown"
                )
                embed.add_field(
                    name="Location",
                    value=f":flag_{data['geo']['country'].lower()}: {city}",
                    inline=True,
                )

            # add whitelist
            if "whitelist" in data.keys():
                is_w = "Yes" if data["whitelist"] else "No"
                if is_w == "Yes":
                    embed.color = PINK
                    embed.title = embed.title + " (Whitelisted)"
                embed.add_field(
                    name="Whitelisted",
                    value=is_w,
                    inline=True,
                )

            # add possible streams
            twitch_count = 0
            if "sample" in data["players"]:
                # loop through and count how many usernames have twitch accounts
                names = []
                for player in data["players"]["sample"]:
                    names.append(player["name"])

                twitch_count = sum(await self.twitch.is_twitch_user(*names))

                if twitch_count > 0:
                    embed.add_field(
                        name="Possible Streams",
                        value=f"{twitch_count} streams",
                        inline=True,
                    )

            return {
                "embed": embed,
                "components": self.buttons(  # These are whether the buttons are disabled
                    index + 1 >= total_servers,  # next
                    index <= 0,  # previous
                    total_servers <= 1,  # jump
                    type(pipeline) is dict,  # update
                    "sample" not in data["players"]
                    or type(pipeline) is dict
                    or len(data["players"]["sample"]) == 0,  # players
                    total_servers <= 1,  # sort
                    not data["hasForgeData"],  # mods
                    data["lastSeen"] <= time.time() - 300,  # join
                    twitch_count <= 0,  # streams
                )
                if not fast
                else self.buttons(),
                "files": [
                    interactions.File("assets/favicon.png"),
                    interactions.File(
                        file_name="pipeline.ason",
                        file=io.BytesIO(
                            json_util.dumps(pipeline, indent=4).encode("utf-8")
                        ),
                    ),
                ],
            }
        except KeyError as e:
            self.logger.print(f"Full traceback: {traceback.format_exc()}")
            self.logger.error(f"KeyError: {e}, IP: {data['ip']}, data: {data}")
            return None
        except Exception as e:
            self.logger.print(f"Full traceback: {traceback.format_exc()}")
            self.logger.error(f"{e}, IP: {data['ip']}")
            with open("pipeline.ason", "w") as f:
                f.write(json_util.dumps(pipeline, indent=4))
            self.logger.error(f"Pipeline saved to `pipeline.ason`")
            return None

    def standard_embed(
        self,
        title: str,
        description: str,
        color: int,
    ) -> interactions.Embed:
        """Return a standard embed

        Args:
            title (str): The title of the embed
            description (str): The description of the embed
            color (int): The color of the embed(
                RED: error
                GREEN: success
                YELLOW: warning
                BLUE: info
                PINK: offline
            )

        Returns:
            interactions.Embed: The embed
        """
        try:
            return interactions.Embed(
                title=title,
                description=description,
                color=color,
                timestamp=self.text.time_now(),
            )
        except Exception as e:
            self.logger.print(f"Full traceback: {traceback.format_exc()}")
            self.logger.error(e)
            return interactions.Embed(
                title=title,
                description=description,
                timestamp=self.text.time_now(),
            )

    async def async_load_server(
        self,
        index: int,
        pipeline: dict | list,
        msg: interactions.Message,
    ) -> None:
        # first call the asyncEmbed function with fast
        stuff = await self.logger.async_timer(
            self.async_embed, pipeline=pipeline, index=index, fast=True
        )

        if stuff is None:
            await msg.edit(
                embed=self.standard_embed(
                    title="Error",
                    description="There was an error loading the server",
                    color=RED,
                ),
                file=None,
            )
            return

        # then send the embed
        await msg.edit(
            **stuff,
        )

        # then call the asyncEmbed function again with slow
        stuff = await self.logger.async_timer(
            self.async_embed, pipeline=pipeline, index=index, fast=False
        )

        if stuff is None:
            await msg.edit(
                embed=self.standard_embed(
                    title="Error",
                    description="There was an error loading the server",
                    color=RED,
                ),
                file=None,
            )
            return

        # then send the embed
        await msg.edit(**stuff)

    @staticmethod
    async def get_pipe(msg: interactions.Message) -> Optional[Tuple[int, dict]]:
        # make sure it has an embed with at least one attachment and a footer
        if (
            len(msg.embeds) == 0
            or len(msg.attachments) == 0
            or msg.embeds[0].footer is None
        ):
            return None

        # grab the index
        index = int(msg.embeds[0].footer.text.split("Showing ")[1].split(" of ")[0]) - 1

        # grab the attachment
        for file in msg.attachments:
            if file.filename == "pipeline.ason":
                async with aiohttp.ClientSession() as session, session.get(
                    file.url
                ) as resp:
                    pipeline = await resp.text()

                return index, (
                    json_util.loads(pipeline) if pipeline is not None else None
                )

        return None

    @trace
    async def update(self, ctx: ComponentContext | ContextMenuContext):
        try:
            org = ctx.message if type(ctx) is ComponentContext else ctx.target

            self.logger.print(f"update page called for {org.id}")
            index, pipeline = await self.get_pipe(org)

            msg = await org.edit(
                embed=self.standard_embed(
                    title="Loading...",
                    description="Loading...",
                    color=BLUE,
                ),
                components=self.buttons(),
                file=File(file="assets/loading.png", file_name="favicon.png"),
            )

            # get the pipeline and index from the message
            total = self.db.count(pipeline)

            msg = await msg.edit(
                embed=self.standard_embed(
                    title="Loading...",
                    description=f"Loading server {index + 1} of {total}",
                    color=BLUE,
                ),
                components=self.buttons(),
            )

            # load the server
            await self.async_load_server(
                index=index,
                pipeline=pipeline,
                msg=msg,
            )
        except Exception as err:
            if "403|Forbidden" in str(err):
                await ctx.send(
                    embed=self.standard_embed(
                        title="An error occurred",
                        description="Wrong channel for this bot",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return

            self.logger.print(f"Full traceback: {traceback.format_exc()}")
            self.logger.error(err)

            await ctx.send(
                embed=self.standard_embed(
                    title="Error",
                    description="An error occurred while trying to update the message",
                    color=RED,
                ),
                ephemeral=True,
            )
