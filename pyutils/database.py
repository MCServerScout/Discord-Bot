import time
import traceback
from typing import List, Optional, Any, Mapping

import pymongo
import sentry_sdk
from pymongo.command_cursor import CommandCursor
from pymongo.results import UpdateResult
# noinspection PyProtectedMember
from sentry_sdk import trace

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

    @trace
    def get_doc_at_index(
        self,
        pipeline: list,
        index: int = 0,
    ) -> Optional[dict]:
        try:
            tStart = time.time()
            new_pipeline = pipeline.copy()

            if type(new_pipeline) is dict:
                new_pipeline = [new_pipeline]

            new_pipeline.append({"$skip": index})
            new_pipeline.append({"$limit": 1})

            result = self.aggregate(new_pipeline, allowDiskUse=True).try_next()
            sentry_sdk.set_context("database", {"pipeline": pipeline, "index": index})

            sentry_sdk.set_measurement("duration", time.time() - tStart, "seconds")

            return result
        except StopIteration:
            self.logger.error(
                f"Error getting document at index: {pipeline}\n{traceback.format_exc()}"
            )

            return None

    @trace
    def aggregate(
        self,
        pipeline: list,
        allowDiskUse: bool = True,
    ) -> CommandCursor[Mapping[str, Any] | Any] | None:
        with sentry_sdk.start_transaction(op="database", name="aggregate"):
            sentry_sdk.set_context("database", {"pipeline": pipeline})
            try:
                return self.col.aggregate(pipeline, allowDiskUse=allowDiskUse)
            except StopIteration:
                self.logger.print(f"No matches for pipeline: {pipeline}")
                return None

    def find_one(
        self,
        query: dict,
    ) -> Optional[dict]:
        try:
            return self.col.find_one(query)
        except StopIteration:
            self.logger.print(f"No matches for query: {query}")
            return None

    def find(
        self,
        query: dict,
    ) -> Optional[List[dict]]:
        try:
            return list(self.col.find(query))
        except StopIteration:
            self.logger.print(f"No matches for query: {query}")
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
            self.logger.print(f"No matches for query: {query}")
            return None

    def update_many(
        self,
        query: dict,
        update: dict,
    ) -> Optional[UpdateResult]:
        try:
            return self.col.update_many(query, update)
        except StopIteration:
            self.logger.print(f"No matches for query: {query}")
            return None

    def count(
        self,
        pipeline: list,
    ):
        """Counts the number of documents in a pipeline"""
        new_pipeline = pipeline.copy()

        if type(new_pipeline) is dict:
            new_pipeline = [new_pipeline]

        new_pipeline.append({"$group": {"_id": None, "count": {"$sum": 1}}})

        result = self.col.aggregate(new_pipeline, allowDiskUse=True).try_next()
        if result is None:
            return 0
        return result["count"]
