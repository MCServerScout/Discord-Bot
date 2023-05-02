"""Useful functions for sending messages to the user."""

import base64
import datetime
import traceback
from typing import List, Optional

import interactions
from interactions import ActionRow

from .database import Database
from .logger import Logger
from .server import Server
from .text import Text


class Message:
    def __init__(
            self,
            logger: "Logger",
            db: "Database",
            text: "Text",
            server: "Server",
    ):
        self.logger = logger
        self.db = db
        self.text = text
        self.server = server

        self.RED = 0xFF0000  # error
        self.GREEN = 0x00FF00  # success
        self.YELLOW = 0xFFFF00  # warning
        self.BLUE = 0x0000FF  # info
        self.PINK = 0xFFC0CB  # offline

    def buttons(self, *args: bool | str) -> List[ActionRow]:
        """Return disabled buttons (True = disabled)

        Args:
            *args (bool | str): The buttons to disable and the link to MCStatus.io

        Returns:
            [
                interactions.ActionRow(): Next, Previous, Jump to
                interactions.ActionRow(): Show Players
                interactions.StringSelectMenu(): Sort
            ]
        """
        if len(args) != 6:
            disabled = [True, True, True, True, True, None, ]
        else:
            disabled = list(args)

        # button: Next, Previous, Show Players
        rows = [
            interactions.ActionRow(
                interactions.Button(
                    label="Previous",
                    style=interactions.ButtonStyle.PRIMARY,
                    custom_id="previous",
                    disabled=disabled[1],
                ),
                interactions.Button(
                    label="Next",
                    style=interactions.ButtonStyle.PRIMARY,
                    custom_id="next",
                    disabled=disabled[0],
                ),
                interactions.Button(
                    label="Jump to",
                    style=interactions.ButtonStyle.SUCCESS,
                    custom_id="jump",
                    disabled=disabled[2],
                )
            ),
            interactions.ActionRow(
                interactions.Button(
                    label="Show Players",
                    style=interactions.ButtonStyle.SECONDARY,
                    custom_id="players",
                    disabled=disabled[3],
                ),
                interactions.Button(
                    label="Change Sort",
                    style=interactions.ButtonStyle.SECONDARY,
                    custom_id="sort",
                    disabled=disabled[4],
                ),
                interactions.Button(
                    label="MCStatus.io",
                    style=interactions.ButtonStyle.LINK,
                    url=disabled[5] if disabled[5] is not None else "https://mcstatus.io/",
                    disabled=disabled[5] is None,
                ),
            ),
        ]

        return rows

    def embed(
            self,
            pipeline: list,
            index: int,
    ) -> Optional[dict]:
        """Return an embed

        Args:
            pipeline (list): The pipeline to use
            index (int): The index of the embed

        Returns:
            {
                "embed": interactions.Embed, # The embed
                "components": [interactions.ActionRow], # The buttons
            }
        """
        try:
            total_servers = self.db.count(pipeline)

            if total_servers == 0:
                return {
                    "embed": self.standardEmbed(
                        title="Error",
                        description="No servers found",
                        color=self.YELLOW,
                    ),
                    "components": self.buttons(),
                }

            if index >= total_servers:
                index = 0

            data = self.db.get_doc_at_index(pipeline, index)

            if data is None:
                return {
                    "embed": self.standardEmbed(
                        title="Error",
                        description="No server found",
                        color=self.YELLOW,
                    ),
                    "components": self.buttons(),
                }

            # get the server status
            isOnline = "🔴"
            data["cracked"] = None
            try:
                status = self.server.status(ip=data["ip"], port=data["port"])
                if status is not None:
                    # update the data
                    data["players"]["max"] = status["players"]["max"]
                    data["players"]["online"] = status["players"]["online"]
                    desc = status["description"]
                    if "extra" in desc and "text" in desc:
                        self.logger.print("[message.embed] Server has a color and text: " + desc["text"])
                        desc = ""

                        # example: {"extra": [{"color": "dark_purple", "text": "A Minecraft Server"}], "text": ""}
                        for extra in status["description"]["extra"]:
                            if "color" in extra and "text" in extra:
                                desc += self.text.colorMine(extra["color"]) + self.text.cFilter(extra["text"])
                            elif "text" in extra:
                                desc += self.text.cFilter(extra["text"])
                            else:
                                desc += self.text.cFilter(extra)
                    elif "text" in desc:
                        desc = desc["text"]
                    else:
                        desc = desc

                    if "text" in data["description"]:
                        data["description"]["text"] = self.text.cFilter(desc)
                    else:
                        data["description"] = {"text": self.text.cFilter(desc)}

                # detect if the server is cracked
                joined = self.server.join(ip=data["ip"], port=data["port"])
                data["cracked"] = joined.getType() == "CRACKED"
                data["hasForgeData"] = joined.getType() == "MODDED"

                isOnline = "🟢"
                self.logger.print("[message.embed] Server is online: " + isOnline)
            except Exception as e:
                self.logger.error("[message.embed] Error: " + str(e))
                self.logger.print(f"[message.embed] Full traceback: {traceback.format_exc()}")

            # create the embed
            embed = self.standardEmbed(
                title=f"{isOnline} {data['ip']}",
                description=f"```ansi\n{self.text.colorAnsi(str(data['description']['text']))}\n```",
                color=self.GREEN if isOnline == "🟢" else self.PINK,
            )

            # set the footer to say the index, pipeline, and total servers
            embed.set_footer(
                f"Showing {index + 1} of {total_servers} servers in: {str(pipeline).replace('True', 'true').replace('False', 'false')}",
            )
            embed.timestamp = self.text.timeNow()

            # get the server icon
            if "favicon" in data and isOnline == "🟢":
                bits = data["favicon"].split(",")[1]
                with open("favicon.png", "wb") as f:
                    f.write(base64.b64decode(bits))
                _file = interactions.File(
                    file_name="favicon.png",
                    file="favicon.png",
                )
            else:
                _file = None

            if _file is not None:
                embed.set_thumbnail(url="attachment://favicon.png")
                self.logger.debug("[message.embed] Server has an icon")

            # add the version
            embed.add_field(
                name="Version",
                value=f"{self.text.cFilter(data['version']['name'])} ({data['version']['protocol']})",
                inline=True,
            )

            # add the player count
            embed.add_field(
                name="Players",
                value=f"{data['players']['online']}/{data['players']['max']}",
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
                value="Yes" if data["hasForgeData"] else "No",
                inline=True,
            )

            # last online
            stamp: datetime.datetime = datetime.datetime.utcfromtimestamp(data["lastSeen"])
            embed.add_field(
                name="Time since last scan",
                value=self.text.timeAgo(stamp),
                inline=True,
            )

            return {
                "embed": embed,
                "components": self.buttons(
                    index + 1 >= total_servers,
                    index <= 0,
                    total_servers <= 1,
                    "sample" not in data["players"],
                    total_servers <= 1,
                    "https://mcstatus.io/status/java/" + str(data["ip"]) + ":" + str(data["port"]),
                ),
            }
        except Exception as e:
            self.logger.error(f"[message.embed] {e}")
            self.logger.print(f"[message.embed] Full traceback: {traceback.format_exc()}")
            return None

    def standardEmbed(
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
        return interactions.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=self.text.timeNow(),
        )
