# setup
import random
import sys
import traceback

from pymongo import MongoClient

import pyutils
from pyutils.scanner import Scanner

DISCORD_WEBHOOK, MONGO_URL, db_name, col_name, client_id, client_secret, IP_INFO_TOKEN = "", "", "", "", "", "", ""
max_threads, max_pps = 10, 1000
DEBUG = False
try:
    from privVars import *
except ImportError:
    MONGO_URL = ""
    TOKEN = "..."

if MONGO_URL == "":
    print("Please add your mongo url to 'privVars.py'")
    sys.exit("Config error in privVars.py, please fix before rerunning")

# Setup
# ---------------------------------------------

# test the db connection
try:
    client = MongoClient(MONGO_URL)
    db = client['MCSS' if db_name == "" else db_name]
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
databaseLib = utils.database
playerLib = utils.player
messageLib = utils.message
twitchLib = utils.twitch
textLib = utils.text
serverLib = utils.server

logger.print("Setup complete")

# stop everything if the scanner is not being run on linux and not as root
if sys.platform != "linux":
    logger.error("Scanner must be run on linux as root")
    sys.exit("Scanner must be run on linux as root")

# Create the x.x.0.0/16 list
ips = []
for i in range(0, 256):
    for j in range(0, 256):
        for k in range(0, 256):
            ips.append(f"{i}.{j}.{k}.0/24")
random.shuffle(ips)

# ips = ["5.9.177.0/24", "5.9.83.0/24"]  # test ips

logger.print("IP list created:", len(ips))

if __name__ == "__main__":
    scanner = Scanner(logger, max_thread_count=max_threads, max_ping_rate=max_pps, serverLib=serverLib)
    # ips = ["0.0.0.0/1"]
    scanner.start(ips)
