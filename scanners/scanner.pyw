import ctypes
import datetime
import random
import socket
import sys
import time
import traceback
from multiprocessing.pool import ThreadPool
from threading import Thread

import numpy as np
import sentry_sdk
from netaddr import IPNetwork
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from sentry_sdk.integrations.aiohttp import AioHttpIntegration

from pyutils import Utils

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
    max_threads,
    max_pps,
) = ["..." for _ in range(15)]

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

# error tracking
sentry_sdk.init(
    dsn=SENTRY_URI,
    traces_sample_rate=1.0,
    profiles_sample_rate=0.6,
    integrations=[AioHttpIntegration()],
) if SENTRY_URI != "..." else None

# test the db connection
print("Connecting to database...")
try:
    client = MongoClient(MONGO_URL)
    db = client["MCSS" if db_name == "..." else db_name]
    col = db["scannedServers" if col_name == "..." else col_name]
except ServerSelectionTimeoutError:
    print("Error connecting to database")
    print(traceback.format_exc())
    sys.exit("Config error in privVars.py, please fix before rerunning")
else:
    print("Connected to database")

utils = Utils(
    col,
    debug=DEBUG,
    discord_webhook=DISCORD_WEBHOOK,
    client_id=client_id,
    client_secret=client_secret,
    info_token=IP_INFO_TOKEN,
    ssdk=((sentry_sdk,),),
)
logger = utils.logger
databaseLib = utils.database
playerLib = utils.player
messageLib = utils.message
twitchLib = utils.twitch
textLib = utils.text
serverLib = utils.server
mcLib = utils.mc

logger.print("Utils loaded")


class IPGenerator:
    def __init__(self, mask: str, port_range: tuple[int] = (25560, 25570)):
        self.num_ips = IPNetwork(mask).size

        # the ips are stored as integers for efficiency
        # they are a series of ints from net.first to net.first + net.size
        self.ips = np.arange(self.num_ips, dtype="uint32") + int(IPNetwork(mask).first)

        self.port_range = port_range

        # make the ips list duplicate for the number of ports
        self.ips = np.repeat(self.ips, len(range(*port_range)))
        self.ports = list(range(*port_range))
        random.shuffle(self.ports)
        np.random.shuffle(self.ips)

        self.used_addr = set()
        self.valid_addr = set()
        self.num_servers = 0
        self.num_mc_servers = 0

    def __iter__(self):
        return self

    def __next__(self):
        if len(self.ips) == 0:
            raise StopIteration
        ip: int = self.ips[0]
        self.ips = self.ips[1:]
        port = random.choice(self.ports)
        if ip is None:
            raise StopIteration

        ip = self.__int2ip(ip)

        if not self.__can_exclude(f"{ip}:{port}"):
            for port in self.ports:
                addr = f"{ip}:{port}"
                if self.__can_exclude(addr):
                    self.__exclude(addr)
                    return addr
            raise StopIteration
        else:
            addr = f"{ip}:{port}"
            self.__exclude(addr)
            return addr

    def __exclude(self, addr):
        # do some checks to ensure efficient exclusion
        assert self.__can_exclude(addr)
        self.used_addr.add(addr)

    def __can_exclude(self, addr):
        """
        This function checks if the address can be excluded from the generator
        """
        return addr not in self.used_addr

    def validate(self, addr: str | tuple[str, int]):
        """
        This function validates an address
        """
        if isinstance(addr, tuple):
            addr = f"{addr[0]}:{addr[1]}"

        self.valid_addr.add(addr)
        self.num_servers += 1

    def get_valid(self):
        """
        This function returns a valid address
        """
        return self.valid_addr.pop()

    def cancel(self):
        self.valid_addr.clear()
        self.used_addr.clear()
        self.ips = np.array([])

    @staticmethod
    def __ip2int(ip):
        """
        This function converts an ip to an integer

        :param ip: str
        :return: int
        """
        # ip -> hex -> bytes -> int
        return int(
            b"0x"
            + b"".join(
                bytes(f"{hex(i).split('x')[1]:<2}", "utf-8") for i in ip.split(".")
            ),
            0,
        )

    @staticmethod
    def __int2ip(ip):
        """
        This function converts an integer to an ip

        :param ip: int
        :return: str
        """
        # int -> bytes -> ip
        if isinstance(ip, np.uint32):
            ip = int(ip)

        return ".".join(tuple((str(int(ip.to_bytes(4, "big")[i])) for i in range(4))))


def scan_range(generator: IPGenerator, timeout: float = 0.2):
    """
    This function scans the network for devices

    :param generator: IPGenerator
    :param timeout: float
    """

    # test ips via tcp handshaking
    for addr in generator:
        ip, port = addr.split(":")
        port = int(port)

        if ip.endswith(".255"):
            continue

        s = socket.socket(socket.AF_INET)
        try:
            s.settimeout(timeout)
            s.connect((ip, port))
        except socket.timeout:
            logger.print(f"Timeout on {addr}{' ' * 8}\r", log=False, end="")
        except socket.error as e:
            logger.print(f"Error on {addr}: {e}")
            logger.print(traceback.format_exc())
        except Exception as e:
            logger.print(f"Error on {addr}: {e}")
            logger.print(traceback.format_exc())
        else:
            logger.print(f"Connected to {addr}")
            generator.validate(addr)
        finally:
            s.close()


def scan_valid(generator: IPGenerator):
    """
    Scans valid ips to test if they are a mc server

    :param generator: IPGenerator
    """

    while len(generator.ips) > 0 or len(generator.valid_addr) > 0:
        if len(generator.valid_addr) == 0:
            time.sleep(1)
            continue

        addr = generator.get_valid()
        ip, port = addr.split(":")
        port = int(port)

        if ip.endswith(".255"):
            continue
        print(f"Testing mc server at {ip}:{port}")

        try:
            status = serverLib.status(ip, port)
        except Exception as e:
            logger.print(f"Error getting status for {ip}")
            logger.print(e)
            sentry_sdk.capture_exception(e)
            continue

        if status is None:
            continue

        logger.print(f"Found mc server at {ip}:{port}")
        generator.num_mc_servers += 1
        serverLib.update(ip, port)


def main(mask: str = "5.78.0.0/16", timeout: float = 0.2, numThreads: int = 100):
    numThreads = min(numThreads, max(max_threads, 1))
    pps = numThreads / timeout
    if pps > max_pps:
        numThreads = int(max_pps * timeout)
        logger.print(f"Reducing threads to {numThreads} to keep pps under {max_pps}")

    generator = IPGenerator(mask, (25565, 25566))
    logger.print(
        f"Scan of {len(generator.ips)} ips started, sending at {numThreads / timeout} packets/s"
    )
    eta = len(generator.ips) * (timeout + 10 / 1000) / numThreads
    logger.print(
        f"ETA: {logger.auto_range_time(eta)} (+/- {logger.auto_range_time(eta * 0.1)})"
    )
    logger.print(
        f"Expected finish at {datetime.datetime.now() + datetime.timedelta(seconds=eta)}"
    )

    tStart = time.perf_counter()
    validate_thread = Thread(target=scan_valid, args=(generator,))
    validate_thread.start()

    pool = ThreadPool(numThreads)

    try:
        pool.map(scan_range, [generator] * numThreads)
    except KeyboardInterrupt:
        logger.print("Scan cancelled")
        generator.cancel()
        pool.terminate()
        pool.join()
        validate_thread.join()
        sys.exit(0)

    pool.close()
    pool.join()
    logger.print(
        f"Main scan finished in {time.perf_counter() - tStart:.2f}s ({(time.perf_counter() - tStart - eta) / eta * 100:.2f}% error), waiting for validation to finish"
    )

    validate_thread.join()
    tEnd = time.perf_counter()

    logger.print(
        f"Scan found {generator.num_mc_servers} mc servers ({(generator.num_mc_servers / generator.num_servers) * 100:.2f}% of online server and {generator.num_mc_servers / generator.num_ips * 100:.2f}% of scanned ips)"
    )
    logger.print(
        f"Scan took {(tEnd - tStart):.2f}s ({(tEnd - tStart - eta) / eta * 100:.2f}% error)"
    )


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


if __name__ == "__main__":
    # ensure running as root
    if not is_admin():
        logger.print("Please run as admin")
        sys.exit(1)
    else:
        logger.print("Running as admin")

    main()
