import pymongo

from .database import Database
from .logger import Logger
from .player import Player
from .server import Server
from .message import Message
from .text import Text


class utils:
    """A class to hold all the utils classes"""

    def __init__(
        self,
        col: pymongo.collection.Collection,
        logger: Logger = None,
        debug=True,
        level: int = 20,
    ):
        """Initializes the utils class

        Args:
            logger (Logger): The logger class
            col (pymongo.collection.Collection): The database collection
            debug (bool, optional): Show debugging. Defaults to True.
            level (int, optional): The logging level. Defaults to 20 (INFO).
        """
        self.col = col
        self.logLevel = level
        self.logger = logger if logger else Logger(debug, level=self.logLevel)
        self.logger.clear()

        self.database = Database(self.col, self.logger)
        
        self.player = Player(logger=self.logger)
        self.server = Server(db=self.database, logger=self.logger)
        self.message = Message(logger=self.logger, db=self.database)
        self.text = Text(logger=self.logger)
