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
        url = "https://api.mcstatus.io/v2/status/java/" + \
            host + ":" + str(port)

        async with aiohttp.ClientSession() as session, session.get(url) as resp:
            if resp.status == 200:
                self.logger.debug("[player.crackCheckAPI] Server is cracked")
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
                self.logger.error("[player.playerHead] Player head not found")
                return None
            with open("playerhead.png", "wb") as f:
                f.write(await r.read())
            self.logger.debug("[player.playerHead] Player head downloaded")
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
                return (await resp.json())["id"]
            else:
                return ""

    async def asyncPlayerList(self, ip: str, port: int = 25565) -> Optional[list[dict]]:
        """Gets a list of players on a server

        Args:
            ip (str): server ip
            port (int, optional): server port. Defaults to 25565.

        Returns:
            str: list of players
        """
        data = self.db.find_one({"ip": ip, "port": port})

        if data is None:
            self.logger.print(
                f"[player.playerList] Server {ip}:{port} not found in database"
            )
            return None

        if "sample" not in data["players"]:
            self.logger.print(
                f"[player.playerList] Server {ip}:{port} has no players")
            return None

        db_names = []
        for player in data["players"]["sample"]:
            db_names.append(player["name"])

        status = self.server.status(ip=ip, port=port)

        status_names = []
        if status is not None and "sample" in status["players"]:
            for player in status["players"]["sample"]:
                status_names.append(player["name"])

        players = []
        for name in db_names:
            player = {
                "name": name,
                "id": await self.async_get_uuid(name),
                "online": name in status_names,
            }
            players.append(player)

        # double check to make sure that we aren't missing any players
        for player in status_names:
            if player not in db_names:
                player = {
                    "name": player,
                    "id": await self.async_get_uuid(player),
                    "online": True,
                }
                players.append(player)

        return players
