import time
import traceback
from typing import Dict, List, Optional, Union

import interactions
import mcstatus
import pymongo
import requests


class Player:
    """Class to hold all the player related functions"""

    def __init__(self, logger):
        """Initializes the Players class

        Args:
            logger (Logger): The logger class
        """
        self.logger = logger

    def crackCheckAPI(self, host: str, port: str = "25565") -> bool:
        """Checks if a server is cracked using the mcstatus.io API

        Args:
            host (str): the host of the server
            port (str, optional): port of the server. Defaults to "25565".

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

    def getUUID(self, name: str) -> str:
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
