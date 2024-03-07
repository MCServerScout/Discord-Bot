import asyncio
import ctypes
import datetime
import itertools
import socket
import struct
import sys
import time
import traceback
from threading import Thread
from typing import Iterator

import numpy as np
import sentry_sdk
from netaddr import IPNetwork
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from sentry_sdk.integrations.aiohttp import AioHttpIntegration

from pyutils import Utils
from pyutils.pycraft2.connector import MCSocket

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
serverLib = utils.server

logger.print("Utils loaded")

# Helpers


def grouper(iterator: Iterator, n: int) -> Iterator[list]:
    while chunk := list(itertools.islice(iterator, n)):
        yield chunk


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


class IPGenerator:
    def __init__(self, mask: str, port_range: tuple[int] = (25560, 25570)):
        self.num_ips = IPNetwork(mask).size * (port_range[1] - port_range[0])
        self.num_ports = port_range[1] - port_range[0]

        # the ips are stored as integers for efficiency
        # they are a series of ints from net.first to net.first + net.size
        self.addrs = np.arange(self.num_ips, dtype=np.uint64) + int(
            IPNetwork(mask).first
        )

        self.port_range = port_range

        # make the ips list duplicate for the number of ports
        self.addrs = np.repeat(self.addrs, self.num_ports) * 100_000
        self.ports = np.arange(*port_range, dtype=np.uint64)
        self.ports = np.tile(self.ports, self.num_ips)
        self.addrs = self.addrs.astype(np.uint64)
        self.addrs += self.ports
        np.random.shuffle(self.addrs)

        self.valid_addr = np.array([], dtype=np.uint64)
        self.num_servers = 0
        self.num_mc_servers = 0
        self.scan_complete = False

    def __iter__(self):
        return self

    def __next__(self):
        if len(self.addrs) == 0:
            raise StopIteration

        addr = self.addrs[0]
        self.addrs = self.addrs[1:]

        return self.int2addr(addr)

    def __getitem__(self, index):
        return self.int2addr(self.addrs[index])

    def validate(self, addr: str | tuple[str, int]):
        """
        This function validates an address
        """
        if isinstance(addr, tuple):
            addr = f"{addr[0]}:{addr[1]}"

        self.num_servers += 1

        _addr = self.__addr2int(addr)

        self.valid_addr = np.append(self.valid_addr, _addr)

    def get_valid(self):
        """
        This function returns a valid address
        """
        if self.valid_addr.size == 0:
            return None

        addr = self.valid_addr[0]
        self.valid_addr = self.valid_addr[1:]
        return self.int2addr(addr)

    def cancel(self):
        self.valid_addr = np.array([], dtype=np.uint64)
        self.addrs = np.array([], dtype=np.uint64)

    @staticmethod
    def __ip2int(ip):
        """
        This function converts an ip to an integer

        :param ip: str
        :return: int
        """
        # ip -> hex -> bytes -> int
        return struct.unpack("!L", socket.inet_aton(ip))[0]

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

        return socket.inet_ntoa(struct.pack("!L", ip))

    def __addr2int(self, addr: str):
        """
        This function converts an address to an integer

        :param addr: str
        :return: int
        """
        ip, port = addr.split(":")
        ip = self.__ip2int(ip)
        port = int(port)

        return ip * 100_000 + port

    def int2addr(self, addr: int):
        """
        This function converts an integer to an address

        :param addr: int
        :return: str
        """
        if (
            isinstance(addr, np.uint64)
            or isinstance(addr, np.uint32)
            or isinstance(addr, np.float64)
        ):
            addr = int(addr)

        ip = int(addr / 100_000)
        port = addr - ip * 100_000

        ip = self.__int2ip(ip)

        return f"{ip}:{port}"


# Pingers


async def ping(addr: tuple[str, int], timeout: float = 1):
    """
    This function pings a server

    :param addr: tuple[str, int] The address to ping
    :param timeout: float The timeout for the ping
    :return: dict
    """
    if isinstance(addr, str):
        addr = addr.split(":")
        addr[1] = int(addr[1])

    ip, port = addr

    if ip.split(".")[-1] in ("0", "255"):
        return False

    try:
        await asyncio.wait_for(asyncio.open_connection(ip, port), timeout)
        logger.print(f"Connected to {ip}:{port}{' ' * 10}")
        return True
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
        return False


async def mcping(addr: tuple[str, int]):
    """
    This function pings a server

    :param addr: tuple[str, int] The address to ping
    :return: dict
    """
    if isinstance(addr, str):
        addr = addr.split(":")
        addr[1] = int(addr[1])

    ip, port = addr

    if ip.split(".")[-1] in ("0", "255"):
        return False

    try:
        p = await MCSocket(ip, port)

        await p.handshake_status()
        await p.status_request()

        return True
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
        traceback.print_exc()

        return False


# Scanners


async def async_scan_range(generator: IPGenerator, timeout: float = 1):
    """
    This function scans the network for devices

    :param generator: IPGenerator
    :param timeout: float
    """
    # assuming the slowest scan speeds, lets get the number of sockets per second this thread can handle
    maxSockets = int(max_pps * timeout)
    last_ETA = 0

    try:
        for addr_group in grouper(iter(generator), maxSockets):
            addrs = {}

            tStart = time.perf_counter()
            async with asyncio.TaskGroup() as tg:
                for addr in addr_group:
                    addrs[addr] = tg.create_task(ping(addr, timeout=timeout))
            tEnd = time.perf_counter()

            ETA = datetime.datetime.now().timestamp() + (
                generator.addrs.size / len(addrs)
            ) * (tEnd - tStart)

            if last_ETA == 0:
                last_ETA = ETA
            else:
                last_ETA = (last_ETA + ETA) / 2

            logger.print(
                f"{round(len(addrs) / (tEnd - tStart), 2)}pps ({round((len(addrs) / (tEnd - tStart)) / max_pps * 100, 2)}% of max), "
                f"{round((generator.num_ips - generator.addrs.size) / generator.num_ips * 100, 2)}% done, "
                f"ETA: {datetime.datetime.fromtimestamp(ETA).strftime('%H:%M:%S')}"
                f"{' ' * 20}",
                end="\r",
            )

            for addr, status in addrs.items():
                if status.result():
                    generator.validate(addr)
                    logger.print(
                        f"Validated {addr} with {generator.valid_addr.size} valid addresses"
                    )

        generator.scan_complete = True
    except Exception as e:
        logger.print(f"Error scanning range")
        logger.print(traceback.format_exc())
        sentry_sdk.capture_exception(e)

        # cancel the scan
        generator.cancel()


def scan_range(generator: IPGenerator, timeout: float = 1):
    """
    This function scans the network for devices

    :param generator: IPGenerator
    :param timeout: float
    """
    asyncio.run(async_scan_range(generator, timeout=timeout))


# Validators


def scan_valid(generator: IPGenerator):
    asyncio.run(async_scan_valid(generator))


async def async_scan_valid(generator: IPGenerator):
    """
    Tests if valid ips respond to status requests

    :param generator: IPGenerator
    """
    while generator.scan_complete is False or generator.valid_addr.size > 0:
        if generator.valid_addr.size == 0:
            await asyncio.sleep(1)
            continue

        tasks = []

        async with asyncio.TaskGroup() as tg:
            for _ in range(min(generator.valid_addr.size, 5)):
                addr = generator.get_valid()
                if addr is None:
                    continue

                ip, port = addr.split(":")
                port = int(port)
                logger.print(f"Testing mc server at {ip}:{port}")

                tasks.append(tg.create_task(mcping((ip, port))))

        for task in tasks:
            if task.result():
                generator.num_mc_servers += 1
                logger.print(f"Found mc server at {ip}:{port}")
                serverLib.update(ip, port)
    else:
        logger.print("No servers remaining to validate")


def main(mask: str = "10.0.0.0/24", timeout: float = 1):
    generator = IPGenerator(mask, (25565, 25566))

    pps = generator.addrs.size / timeout
    pps = min(pps, max_pps)

    logger.print(
        f"Scan of {len(generator.addrs)} ips started, sending at {pps} packets/s"
    )
    eta = len(generator.addrs) / pps * timeout
    logger.print(
        f"ETA: {logger.auto_range_time(eta)} (+/- {logger.auto_range_time(eta * 0.1)})"
    )
    logger.print(
        f"Expected finish at {datetime.datetime.now() + datetime.timedelta(seconds=eta)}"
    )

    tStart = time.perf_counter()
    validate_thread = Thread(target=scan_valid, args=(generator,))
    validate_thread.start()

    scan_range(generator, timeout=timeout)

    logger.print(
        f"Main scan finished in {logger.auto_range_time(time.perf_counter() - tStart)} ({(time.perf_counter() - tStart - eta) / eta * 100:.2f}% error), {generator.num_servers} online servers found, waiting for validation to finish"
    )

    validate_thread.join()
    tEnd = time.perf_counter()

    logger.print(
        f"Scan found {generator.num_mc_servers} mc servers ({(generator.num_mc_servers / (generator.num_servers + 1e-100)) * 100:.2f}% of online server and {generator.num_mc_servers / generator.num_ips * 100:.2f}% of scanned ips)"
    )
    logger.print(
        f"Scan took {(tEnd - tStart):.2f}s ({(tEnd - tStart - eta) / eta * 100:.2f}% error)"
    )


if __name__ == "__main__":
    # ensure running as root
    if not is_admin():
        logger.error("Please run as admin")
        sys.exit(1)
    else:
        logger.print("Running as admin")

    main()
