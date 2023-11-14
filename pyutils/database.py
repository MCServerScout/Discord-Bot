import time
import traceback
from typing import List, Optional

import pymongo
import sentry_sdk
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
            tStart = time.perf_counter()
            new_pipeline = pipeline.copy()

            if isinstance(new_pipeline, dict):
                new_pipeline = [new_pipeline]

            for i, stage in enumerate(new_pipeline):
                if "$limit" in stage:
                    del new_pipeline[i]
                if "$skip" in stage:
                    del new_pipeline[i]
                if "$sample" in stage:
                    del new_pipeline[i]
                    new_pipeline.insert(i, {"$sample": {"size": 1}})

            if index > 0:
                new_pipeline.append({"$limit": index + 1})
                new_pipeline.append({"$skip": index})
            else:
                new_pipeline.append({"$limit": 1})

            result = self.logger.timer(
                self.col.aggregate, new_pipeline, allowDiskUse=True
            ).try_next()

            sentry_sdk.set_measurement(
                "duration", time.perf_counter() - tStart, "seconds"
            )
            sentry_sdk.set_context(
                "database", {"pipeline": new_pipeline, "index": index}
            )

            return result
        except StopIteration:
            self.logger.error(
                f"Error getting document at index: {pipeline}\n{traceback.format_exc()}"
            )

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

        match = {}
        limit = {"$limit": 10**9}
        for stage in new_pipeline:
            if "$match" in stage:
                match = stage
            if "$limit" in stage:
                limit = stage
            if "$sample" in stage:
                limit = {"$limit": stage["$sample"]["size"]}

        new_pipeline = [
            match,
            limit,
            {"$group": {"_id": None, "count": {"$sum": 1}}},
            {"$project": {"_id": 0, "count": 1}},
        ]

        result = self.col.aggregate(new_pipeline, allowDiskUse=True).try_next()
        if result is None:
            return 0
        return result["count"]

    def aggregate(self, pipeline: list, **kwargs):
        return self.col.aggregate(pipeline, **kwargs)

    def hash_dict(self, d: dict) -> tuple:
        """Returns a hash of a dict

        Args:
            d (dict): The dict to hash

        Returns:
            tuple: the hashable object
        """
        out = tuple()
        for k, v in d.items():
            if type(v) is dict:
                out += (k, self.hash_dict(v))
            elif type(v) is list:
                out += (k, self.hash_list(v))
            else:
                out += (k, v)

        return out

    def hash_list(self, l: list) -> tuple:
        """Returns a hash of a list

        Args:
            l (list): The list to hash

        Returns:
            tuple: the hashable object
        """
        out = tuple()
        for v in l:
            if type(v) is dict:
                out += (self.hash_dict(v),)
            elif type(v) is list:
                out += (self.hash_list(v),)
            else:
                out += (v,)

        return out

    def hash_pipeline(self, pipe: list) -> tuple:
        """Returns a hash of a pipeline

        Args:
            pipe (list[dict]): The pipeline to hash

        Returns:
            tuple: the hashable object
        """
        out = tuple()
        for stage in pipe:
            for k, v in stage.items():
                if type(v) is dict:
                    out += (k, self.hash_dict(v))
                else:
                    out += (k, v)

        return out
