"""Useful functions for sending messages to the user."""

from typing import Optional

import base64
import interactions
import mcstatus

from .database import Database
from .logger import Logger
from .text import Text


class Message:
    def __init__(
        self,
        logger: "Logger",
        db: "Database",
        text: "Text",
    ):
        self.logger = logger
        self.db = db
        self.text = text
        
        self.RED = 0xFF0000  # error
        self.GREEN = 0x00FF00  # success
        self.YELLOW = 0xFFFF00  # warning
        self.BLUE = 0x0000FF  # info
        self.PINK = 0xFFC0CB  # offline

    def buttons(self, *args) -> interactions.ActionRow:
        """Return disabled buttons

        Args:
            *args (bool): The buttons to disable, len must be 3

        Returns:
            [
                interactions.ActionRow(): Next, Previous
                interactions.ActionRow(): Show Players
            ]
        """
        disabled = list(*args) if len(args) == 3 else [False, False, False]

        # buttone: Next, Previous, Show Players
        rows = [
            interactions.ActionRow(
                interactions.Button(
                    label="Next",
                    style=interactions.ButtonStyle.PRIMARY,
                    custom_id="next",
                    disabled=disabled[0],
                ),
                interactions.Button(
                    label="Previous",
                    style=interactions.ButtonStyle.PRIMARY,
                    custom_id="previous",
                    disabled=disabled[1],
                ),
            ),
            interactions.ActionRow(
                interactions.Button(
                    label="Show Players",
                    style=interactions.ButtonStyle.PRIMARY,
                    custom_id="players",
                    disabled=disabled[2],
                ),
            ),
        ]

        return rows

    def embed(
        self,
        pipeline: list,
        index: int,
    ) -> dict:
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

        totalServers = self.db.countPipeline(pipeline)
        
        if totalServers == 0:
            return None
        
        if index >= totalServers:
            index = 0
        
        data = self.db.get_doc_at_index(pipeline, index)
        
        if data is None:
            return {
                "embed": self.standardEmbed(
                    title="Error",
                    description="No server found",
                    color=self.YELLOW,
                ),
                "components": self.buttons(True, True, True),
            }
        
        isOnline = "🔴"
        try:
            mcstatus.JavaServer(data["host"]["ip"], data["host"]["port"]).ping()
            isOnline = "🟢"
            self.logger.debug("[message.embed] Server is online")
        except:
            pass
        
        embed = self.standardEmbed(
            title=f"{isOnline} {data['host']['hostname']}",
            description=self.text.colorAnsi(data["description"]["text"]),
            color=self.GREEN if isOnline == "🟢" else self.RED,
        )
        
        # set the footer to say the index, pipeline, and total servers
        embed.set_footer(
            f"Showing {index + 1} of {totalServers} servers in: {pipeline[0]}",
        )
        embed.timestamp = self.text.timeNow()
        
        # get the server icon
        if "favicon" in data and isOnline == "🟢":
            bits = data["favicon"].split(",")[1]
            with open("favicon.png", "wb") as f:
                f.write(base64.b64decode(bits))
            _file = interactions.File(file_name="favicon.png",)
        else:
            _file = None
        
        if _file is not None:
            embed.set_thumbnail(url="attachment://favicon.png")
            self.logger.debug("[message.embed] Server has an icon")
        
        return {
            "embed": embed,
            "components": self.buttons(
                totalServers > 1,
                index > 0,
                "sample" in data,
            ),
        }
        
        
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
            color (int): The color of the embed (
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
        )
