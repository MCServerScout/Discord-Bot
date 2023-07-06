import traceback
from typing import List, Optional

import pymongo
from pymongo.results import UpdateResult

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
            pipeline: list,
            index: int = 0,
    ) -> Optional[dict]:
        try:
            new_pipeline = pipeline.copy()

            if type(new_pipeline) is dict:
                new_pipeline = [new_pipeline]

            new_pipeline.append({"$skip": index})
            new_pipeline.append({"$limit": 1})
            new_pipeline.append({"$project": {"_id": 1}})
            new_pipeline.append({"$limit": 1})
            new_pipeline.append({"$addFields": {"doc": "$$ROOT"}})
            new_pipeline.append({"$project": {"_id": 0, "doc": 1}})

            result = self.col.aggregate(new_pipeline, allowDiskUse=True)
            try:
                return self.col.find_one(next(result)["doc"])
            except StopIteration:
                self.logger.error(
                    "Index out of range")
                return None
        except StopIteration:
            self.logger.error(traceback.format_exc())
            self.logger.error(
                f"Error getting document at index: {pipeline}"
            )

            return None

    def aggregate(
            self,
            pipeline: list,
            allow_disk_use: bool = True,
    ) -> Optional[List[dict]]:
        try:
            return list(self.col.aggregate(pipeline, allowDiskUse=allow_disk_use))
        except StopIteration:
            self.logger.error(traceback.format_exc())
            self.logger.error(
                f"Error aggregating: {pipeline}")
            return None

    def find_one(
            self,
            query: dict,
    ) -> Optional[dict]:
        try:
            return self.col.find_one(query)
        except StopIteration:
            self.logger.error(traceback.format_exc())
            self.logger.error(
                f"Error finding one: {query}")
            return None

    def find(
            self,
            query: dict,
    ) -> Optional[List[dict]]:
        try:
            return list(self.col.find(query))
        except StopIteration:
            self.logger.error(traceback.format_exc())
            self.logger.error(f"Error finding: {query}")
            return None

    def update_one(
            self,
            query: dict,
            update: dict,
            **kwargs,
    ) -> Optional[UpdateResult]:
        try:
            return self.col.update_one(query, update, **kwargs)
        except StopIteration:
            self.logger.error(traceback.format_exc())
            self.logger.error(
                f"Error updating one: {query}")
            return None

    def update_many(
            self,
            query: dict,
            update: dict,
    ) -> Optional[UpdateResult]:
        try:
            return self.col.update_many(query, update)
        except StopIteration:
            self.logger.error(traceback.format_exc())
            self.logger.error(
                f"Error updating many: {query}")
            return None

    def count(
            self,
            pipeline: list,
    ):
        """Counts the number of documents in a pipeline"""
        try:
            new_pipeline = pipeline.copy()

            if type(new_pipeline) is dict:
                new_pipeline = [new_pipeline]

            new_pipeline.append({"$count": "count"})

            result = self.col.aggregate(new_pipeline, allowDiskUse=True)
            try:
                return next(result)["count"]
            except StopIteration:
                return 0
        except StopIteration:
            self.logger.error(traceback.format_exc())
            self.logger.error(
                f"Error counting pipeline: {pipeline}"
            )
            return 0
