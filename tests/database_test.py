import os
import sys
import traceback

from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

try:
    import pyutils
except ImportError:
    # get the path of the parent directory
    current = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(current)

    # add the parent directory to the path
    sys.path.append(parent)

    # try importing again
    import pyutils

(
    DISCORD_WEBHOOK,
    DISCORD_TOKEN,
    MONGO_URL,
    db_name,
    col_name,
    client_id,
    client_secret,
    IP_INFO_TOKEN,
    cstats,
    azure_client_id,
    azure_redirect_uri,
    SENTRY_TOKEN,
    SENTRY_URI,
) = ["..." for _ in range(13)]

DEBUG = False
try:
    from privVars import *
except ImportError:
    MONGO_URL = ""
    TOKEN = "..."

if MONGO_URL == "...":
    print("Please add your mongo url to 'privVars.py'")
    sys.exit("Config error in privVars.py, please fix before rerunning")
if DISCORD_TOKEN == "...":
    print("Please add your bot token to 'privVars.py'")
    sys.exit("Config error in privVars.py, please fix before rerunning")

# Setup
# ---------------------------------------------

# test the db connection
print("Connecting to database...")
try:
    client = MongoClient(MONGO_URL)
    db = client["MCSS" if db_name == "..." else db_name]
    col = db["scannedServers" if col_name == "..." else col_name]

    logger = pyutils.logger.Logger()
    pyDB = pyutils.database.Database(col, logger)
except ServerSelectionTimeoutError:
    print("Error connecting to database")
    print(traceback.format_exc())
    sys.exit("Config error in privVars.py, please fix before rerunning")
else:
    print("Connected to database")


# Tests
# ---------------------------------------------


def test_db():
    """Test the database connection"""

    try:
        col.count_documents({})
    except Exception:
        print("Error testing database")
        print(traceback.format_exc())
        sys.exit("Config error in privVars.py, please fix before rerunning")


def test_indexed_doc():
    """Test getting a doc at an index"""

    try:
        doc = pyDB.get_doc_at_index([{"$match": {}}])
    except Exception:
        print("Error getting doc at index")
        print(traceback.format_exc())
        sys.exit("Config error in privVars.py, please fix before rerunning")

    assert doc is not None, "Doc is None"
    assert isinstance(doc, dict), "Doc is not a dict"
    assert "_id" in doc, "Doc does not have an _id field"


def test_count():
    """Test counting the number of documents in a pipeline"""

    try:
        count = pyDB.count([{"$match": {}}])
    except Exception:
        print("Error counting documents")
        print(traceback.format_exc())
        sys.exit("Config error in privVars.py, please fix before rerunning")

    assert isinstance(count, int), "Count is not an int"


def test_pipe_hash():
    """Test getting the hash of a pipeline"""

    try:
        pipe = [{"$match": {}}]
        pipe_hash = pyDB.hashable_pipeline(pipe)
        pipe_unhash = pyDB.unhash_pipeline(pipe_hash)
    except Exception:
        print("Error getting pipeline hash")
        print(traceback.format_exc())
        sys.exit("Config error in privVars.py, please fix before rerunning")

    assert len(pipe_hash) > 0, "Pipe hash is empty"
    assert pipe == pipe_unhash, "Pipe unhash is incorrect"
