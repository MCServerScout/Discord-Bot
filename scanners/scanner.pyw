# setup
import os
import sys
import traceback

from pymongo import MongoClient

try:
    import pyutils
except ImportError:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
finally:
    import pyutils
    from pyutils.scanner import Scanner

(
    DISCORD_WEBHOOK,
    MONGO_URL,
    db_name,
    col_name,
    client_id,
    client_secret,
    IP_INFO_TOKEN,
) = ("", "", "", "", "", "", "")
max_threads, max_pps = 5, 100
DEBUG = False
try:
    from privVars import *
except ImportError:
    MONGO_URL = ""

if MONGO_URL == "":
    print("Please add your mongo url to 'privVars.py'")
    sys.exit("Config error in privVars.py, please fix before rerunning")

# Setup
# ---------------------------------------------

# test the db connection
try:
    client = MongoClient(MONGO_URL)
    db = client["MCSS" if db_name == "" else db_name]
    col = db["scannedServers" if col_name == "" else col_name]

    col.count_documents({})
    print("Connected to database")
except Exception as e:
    print("Error connecting to database")
    print(traceback.format_exc())
    sys.exit("Config error in privVars.py, please fix before rerunning")

utils = pyutils.Utils(
    col,
    debug=DEBUG,
    discord_webhook=DISCORD_WEBHOOK,
    client_id=client_id,
    client_secret=client_secret,
    info_token=IP_INFO_TOKEN,
)
logger = utils.logger
serverLib = utils.server

logger.print("Setup complete")

# stop everything if the scanner is not being run on linux and not as root
if sys.platform != "linux":
    logger.error("Scanner must be run on linux as root")
    sys.exit("Scanner must be run on linux as root")


if __name__ == "__main__":
    scanner = Scanner(
        logger, max_thread_count=max_threads, max_ping_rate=max_pps, serverLib=serverLib
    )
    ips = "0.0.0.0/1"
    while True:
        scanner.start(ip_ranges=ips)
