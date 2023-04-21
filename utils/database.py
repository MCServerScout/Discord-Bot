from typing import Dict, List, Optional
import traceback
import pymongo

from .logger import Logger


class Database:
    """A class to hold all the database functions and api calls"""

    def __init__(
        self,
        col: pymongo.collection.Collection,
        logger: "Logger",
    ):
        self.col = col
        self.logger = logger

    def get_doc_at_index(
        self,
        col: pymongo.collection.Collection,
        pipeline: list,
        index: int = 0,
    ) -> Optional[dict]:
        try:
            newPipeline = pipeline.copy()

            if type(newPipeline) is dict:
                newPipeline = [newPipeline]

            newPipeline.append({"$skip": index})
            newPipeline.append({"$limit": 1})
            newPipeline.append({"$project": {"_id": 1}})
            newPipeline.append({"$limit": 1})
            newPipeline.append({"$addFields": {"doc": "$$ROOT"}})
            newPipeline.append({"$project": {"_id": 0, "doc": 1}})

            result = col.aggregate(newPipeline, allowDiskUse=True)
            try:
                return col.find_one(next(result)["doc"])
            except StopIteration:
                self.logger.error("Index out of range")
                return None
        except:
            self.logger.error(traceback.format_exc())
            self.logger.error("Error getting document at index: {}".format(pipeline))
            return None
