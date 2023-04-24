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
                self.logger.error("[database.get_doc_at_index] Index out of range")
                return None
        except:
            self.logger.error("[database.get_doc_at_index] " + traceback.format_exc())
            self.logger.error(
                "[database.get_doc_at_index] Error getting document at index: {}".format(
                    pipeline
                )
            )
            return None

    def aggregate(
        self,
        pipeline: list,
        allowDiskUse: bool = True,
    ) -> Optional[List[dict]]:
        try:
            return list(self.col.aggregate(pipeline, allowDiskUse=allowDiskUse))
        except:
            self.logger.error("[database.aggregate] " + traceback.format_exc())
            self.logger.error(
                "[database.aggregate] Error aggregating: {}".format(pipeline)
            )
            return None

    def find_one(
        self,
        query: dict,
    ) -> Optional[dict]:
        try:
            return self.col.find_one(query)
        except:
            self.logger.error("[database.find_one] " + traceback.format_exc())
            self.logger.error("[database.find_one] Error finding one: {}".format(query))
            return None

    def find(
        self,
        query: dict,
    ) -> Optional[List[dict]]:
        try:
            return list(self.col.find(query))
        except:
            self.logger.error("[database.find] " + traceback.format_exc())
            self.logger.error("[database.find] Error finding: {}".format(query))
            return None

    def update_one(
        self,
        query: dict,
        update: dict,
        **kwargs,
    ) -> Optional[dict]:
        try:
            return self.col.update_one(query, update, **kwargs)
        except:
            self.logger.error("[database.update_one] " + traceback.format_exc())
            self.logger.error(
                "[database.update_one] Error updating one: {}".format(query)
            )
            return None

    def update_many(
        self,
        query: dict,
        update: dict,
    ) -> Optional[dict]:
        try:
            return self.col.update_many(query, update)
        except:
            self.logger.error("[database.update_many] " + traceback.format_exc())
            self.logger.error(
                "[database.update_many] Error updating many: {}".format(query)
            )
            return None

    def countPipeline(
        self,
        pipeline: list,
    ):
        try:
            newPipeline = pipeline.copy()

            if type(newPipeline) is dict:
                newPipeline = [newPipeline]

            newPipeline.append({"$count": "count"})

            result = self.col.aggregate(newPipeline, allowDiskUse=True)
            try:
                return next(result)["count"]
            except StopIteration:
                return 0
        except:
            self.logger.error("[database.countPipeline] " + traceback.format_exc())
            self.logger.error(
                "[database.countPipeline] Error counting pipeline: {}".format(pipeline)
            )
            return 0
