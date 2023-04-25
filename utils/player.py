from typing import Optional

import interactions
import requests

from .logger import Logger
from .server import Server
from .database import Database


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

    def crack_check_API(self, host: str, port: str = "25565") -> bool:
        """Checks if a server is cracked using the mcstatus.io API

        Args:
            host (str): the host of the server
            port (str, optional): port of the server.
            Default to "25565".

        Returns:
            bool: True if the server is cracked, False if not
        """
        url = "https://api.mcstatus.io/v2/status/java/" + host + ":" + str(port)

        resp = requests.get(url)
        if resp.status_code == 200:
            self.logger.debug("[player.crackCheckAPI] Server is cracked")
            return resp.json()["eula_blocked"]
        else:
            return False

    def playerHead(self, name: str) -> Optional[interactions.File]:
        """Downloads a player head from minotar.net

        Args:
            name (str): player name

        Returns:
            interactions.file | None: file object of the player head
        """
        url = "https://minotar.net/avatar/" + name
        r = requests.get(url)
        with open("playerhead.png", "wb") as f:
            f.write(r.content)
        self.logger.debug("[player.playerHead] Player head downloaded")
        return interactions.File(
            file_name="playerhead.png",
            file=open("playerhead.png", "rb"),
        )

    @staticmethod
    def getUUID(name: str) -> str:
        """Get the UUID of a player

        Args:
            name (str): player name

        Returns:
            str: player UUID
        """
        url = "https://api.mojang.com/users/profiles/minecraft/" + name
        res = requests.get(url)
        if "error" not in res.text.lower():
            return res.json()["id"]
        else:
            return "---n/a---"

    def playerList(self, host: dict) -> Optional[list[dict]]:
        """Gets a list of players on a server

        Args:
            host (dict): the host of the server {ip: str, hostname: str, port: str}

        Returns:
            str: list of players
        """
        data = self.db.find_one({"host": host})

        if data is None:
            return None

        if "sample" not in data:
            return None

        db_names = []
        for player in data["sample"]:
            db_names.append(player["name"])

        status = self.server.status(ip=host["ip"], port=host["port"])

        if status is None or "sample" not in status:
            return None

        status_names = []
        for player in status["sample"]:
            status_names.append(player["name"])

        players = []
        for name in db_names:
            player = {
                "name": name,
                "uuid": self.getUUID(name),
                "online": name in status_names
            }
            players.append(player)

        # double check to make sure that we aren't missing any players
        for player in status_names:
            if player not in db_names:
                player = {
                    "name": player,
                    "uuid": self.getUUID(player),
                    "online": True
                }
                players.append(player)

        return players
