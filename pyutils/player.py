import asyncio
from typing import Optional

import aiohttp
import interactions

from .database import Database
from .logger import Logger
from .server import Server


class Player:
    """Class to hold all the player-related functions"""

    def __init__(self, logger: "Logger", server: "Server", db: "Database"):
        """Initializes the Players class

        Args:
            logger (Logger): The logger class
            server (Server): The server class
            db (Database): The database class
        """
        self.logger = logger
        self.server = server
        self.db = db

    async def async_crack_check_api(self, host: str, port: str = "25565") -> bool:
        """Checks if a server is cracked using the mcstatus.io API

        Args:
            host (str): the host of the server
            port (str, optional): port of the server.
            Default to "25565".

        Returns:
            bool: True if the server is cracked, False if not
        """
        url = "https://api.mcstatus.io/v2/status/java/" + host + ":" + str(port)

        async with aiohttp.ClientSession() as session, session.get(url) as resp:
            if resp.status == 200:
                self.logger.debug("Server is cracked")
                return (await resp.json())["eula_blocked"]
            else:
                return False

    async def async_player_head(self, name: str) -> Optional[interactions.File]:
        """Downloads a player head from minotar.net

        Args:
            name (str): player name

        Returns:
            interactions.file | None: file object of the player head
        """
        url = "https://minotar.net/avatar/" + name
        async with aiohttp.ClientSession() as session, session.get(url) as r:
            if r.status != 200:
                self.logger.print("Player head not found")
                return None
            with open("playerhead.png", "wb") as f:
                f.write(await r.read())
            self.logger.debug("Player head downloaded")
            return interactions.File(
                file_name="playerhead.png",
                file=open("playerhead.png", "rb"),
            )

    def get_uuid(self, name: str) -> str:
        return asyncio.run(self.async_get_uuid(name))

    @staticmethod
    async def async_get_uuid(name: str) -> str:
        """Get the UUID of a player

        Args:
            name (str): player name

        Returns:
            str: player UUID
        """
        url = "https://api.mojang.com/users/profiles/minecraft/" + name
        async with aiohttp.ClientSession() as session, session.get(url) as resp:
            if resp.status == 200:
                uuid = (await resp.json())["id"]
                return (
                    f"{uuid[:8]}-{uuid[8:12]}-{uuid[12:16]}-{uuid[16:20]}-{uuid[20:]}"
                )
            else:
                return ""

    @staticmethod
    async def async_get_profile(uuid: str) -> dict:
        """Get the profile of a player

        Args:
            uuid (str): player uuid

        Returns:
            dict: player profile
        """
        url = "https://sessionserver.mojang.com/session/minecraft/profile/" + uuid
        async with aiohttp.ClientSession() as session, session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                return {}

    async def async_player_list(
        self, ip: str, port: int = 25565
    ) -> Optional[list[dict]]:
        """Gets a list of players on a server

        Args:
            ip (str): server ip
            port (int, optional): server port. Default to 25565.

        Returns:
            str: list of players
        """
        data = self.server.update(host=ip, port=port, fast=True)

        if data is None:
            self.logger.print(f"Server {ip}:{port} not found in database")
            return None

        if "sample" not in data["players"]:
            self.logger.print(f"Server {ip}:{port} has no players")
            return None

        self.logger.print(
            f"Server {ip}:{port} has players: {data['players']['sample']}"
        )

        players = []
        for player in data["players"]["sample"]:
            if "lastSeen" not in player:
                player["lastSeen"] = 0
            players.append(self.server.Player(**player))

        if len(players) == 0:
            return None

        return players
