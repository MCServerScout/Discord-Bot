# setup
import json
import random
import sys
import threading
import time
import traceback
from multiprocessing.pool import ThreadPool

import masscan
from pymongo import MongoClient

import utils

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

utils = utils.Utils(
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

STOP = False

logger.print("Setup complete")

# stop everything if the scanner is not being run on linux and not as root
if sys.platform != "linux":
    logger.error("Scanner must be run on linux as root")
    sys.exit("Scanner must be run on linux as root")

# Create the x.x.0.0/16 list
ips = []
for i in range(0, 256):
    for j in range(0, 256):
        ips.append(f"{i}.{j}.0.0/16")
random.shuffle(ips)

# ips = ips[:10]
# ips[0] = "5.9.177.0/24"

logger.print("IP list created:", len(ips))

# TODO
# * Make an async gen: https://stackoverflow.com/questions/41359350/how-to-create-an-async-generator-in-python

que = []


# func that will use masscan to add any servers that are online, respond to a port within 25560-25575 and are minecraft servers
def scan_range(ip_range):
    global que, logger
    try:
        # step one, get a range of online ips
        logger.print(f"Scanning {ip_range}")
        scanner = masscan.PortScanner()
        scanner.scan(ip_range, ports="25560-25575", arguments="--rate=" + str(max_pps // max_threads))

        hosts = json.loads(scanner.scan_result)["scan"]
        logger.print(f"Scan complete for {ip_range}")
        host_ips = hosts.keys()
        logger.print(f"Found {len(host_ips)} ips in {ip_range}")
        for ip in host_ips:
            host = hosts[ip]
            for port in host:
                if port['status'] == "open":
                    logger.print(f"Found open port {port['port']} on {ip}")
                    que.append(ip + ":" + str(port['port']))
        logger.print(f"Que length: {len(que)}: {que}")
    except Exception as err:
        logger.error(f"Error scanning {ip_range}: {err}")
        logger.print(traceback.format_exc())


def scan_starter(ip_list):
    logger.print("Starting scans")
    # creates all the threads that run the scan_range function
    pool = ThreadPool(processes=10)
    pool.map(scan_range, ip_list)


def test_server(ip: str, port: int):
    serverLib.update(host=ip, port=port, fast=False)


def test_starter(logger_func):
    logger_func.print("Starting tests")
    global STOP, que
    while not STOP:
        if len(que) > 0:
            ip = que.pop(0)
            logger_func.print(f"Testing {ip}")
            test_server(ip, 25565)
        else:
            logger.warning("No ips in que, sleeping")
            time.sleep(30)


if __name__ == "__main__":
    threading.Thread(target=test_starter, args=(logger,)).start()
    scan_starter(ips)
