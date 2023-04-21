import pymongo

from .logger import Logger
from .database import Database

class utils:
    """A class to hold all the utils classes"""

    def __init__(
        self,
        col: pymongo.collection.Collection,
        logger: Logger = None,
        debug=True,
        allowJoin=False,
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
        self.logger = (
            logger
            if logger
            else Logger(debug, level=self.logLevel, allowJoin=allowJoin)
        )
        self.logger.clear()
        
        self.database = Database(self.col, self.logger)