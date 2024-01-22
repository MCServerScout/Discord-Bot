import pymongo
import sentry_sdk

from .database import Database
from .logger import Logger
from .message import Message
from .minecraft import Minecraft
from .player import Player
from .server import Server
from .text import Text
from .twitch import Twitch


class Utils:
    """A class to hold all the pyutils classes"""

    def __init__(
        self,
        col: pymongo.collection.Collection,
        discord_webhook: str,
        log: Logger = None,
        debug: bool = True,
        level: int = 20,
        client_id: str = None,
        client_secret: str = None,
        info_token: str = None,
        sentry_dsn: str = None,
        ssdk: "sentry_sdk" = None,
    ):
        """Initializes the pyutils class

        Args:
            col (pymongo.collection.Collection): The collection to use
            discord_webhook (str): The discord webhook to use
            log (Logger, optional): The logger to use. Default to None
            debug (bool, optional): Whether to use debug mode. Default to True
            level (int, optional): The logging level to use. Default to 20
            client_id (str, optional): The twitch client id to use. Default to None
            client_secret (str, optional): The twitch client secret to use. Default to None
            info_token (str, optional): The ipinfo token to use. Default to None
            sentry_dsn (str, optional): The sentry dsn to use. Default to None
            ssdk (sentry_sdk, optional): The sentry_sdk to use. Default to None
        """
        self.col = col
        self.logLevel = level
        if log is None:
            self.logger = Logger(
                debug=debug,
                level=self.logLevel,
                discord_webhook=discord_webhook,
                sentry_dsn=sentry_dsn,
                ssdk=ssdk,
            )
        else:
            self.logger = log

        self.logger.clear()

        self.database = Database(self.col, self.logger)

        self.text = Text(logger=self.logger)
        self.twitch = Twitch(
            logger=self.logger, client_id=client_id, client_secret=client_secret
        )

        self.server = Server(
            db=self.database,
            logger=self.logger,
            text=self.text,
            ipinfo_token=info_token,
        )

        self.player = Player(logger=self.logger,
                             server=self.server, db=self.database)
        self.message = Message(
            logger=self.logger,
            db=self.database,
            text=self.text,
            server=self.server,
            twitch=self.twitch,
        )

        self.mc = Minecraft(
            logger=self.logger,
            player=self.player,
            server=self.server,
            text=self.text,
        )
