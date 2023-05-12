import pymongo

from .database import Database
from .logger import Logger
from .message import Message
from .player import Player
from .server import Server
from .text import Text
from .twitch import Twitch


class Utils:
    """A class to hold all the utils classes"""

    def __init__(
        self,
        col: pymongo.collection.Collection,
        discord_webhook: str,
        log: Logger = None,
        debug=True,
        level: int = 20,
    ):
        """Initializes the utils class

        Args:
            col (pymongo.collection.Collection): The collection to use
            discord_webhook (str): The discord webhook to use
            log (Logger, optional): The logger to use. Defaults to None.
            debug (bool, optional): Whether to use debug mode. Defaults to True.
            level (int, optional): The logging level to use. Defaults to 20.
        """
        self.col = col
        self.logLevel = level
        if log is None:
            self.logger = Logger(
                debug=debug, level=self.logLevel, discord_webhook=discord_webhook
            )
        else:
            self.logger = log

        self.logger.clear()

        self.database = Database(self.col, self.logger)

        self.text = Text(logger=self.logger)
        self.twitch = Twitch(logger=self.logger)

        self.server = Server(
            db=self.database, logger=self.logger, text=self.text)

        self.player = Player(logger=self.logger,
                             server=self.server, db=self.database)
        self.message = Message(
            logger=self.logger, db=self.database, text=self.text, server=self.server
        )
