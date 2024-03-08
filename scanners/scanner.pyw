import asyncio
import ctypes
import datetime
import itertools
import os.path
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
from sentry_sdk import metrics
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
    correction_factor,
) = ["..." for _ in range(16)]

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

        self.addrs = tuple(self.addrs)
        self.valid_addr = ()

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

        self.valid_addr += (_addr,)

    def get_valid(self):
        """
        This function returns a valid address
        """
        if len(self.valid_addr) == 0:
            return None

        addr = self.valid_addr[0]
        self.valid_addr = self.valid_addr[1:]
        return self.int2addr(addr)

    def cancel(self):
        self.valid_addr = ()
        self.addrs = ()
        self.scan_complete = True

    @staticmethod
    def __ip2int(ip):
        """
        This function converts an ip to an integer

        :param ip: str
        :return: int
        """
        # ip -> hex -> bytes -> int
        return int.from_bytes(
            b"".join(map(lambda x: bytes([int(x)]), ip.split("."))), "big"
        )

    @staticmethod
    def __int2ip(ip):
        """
        This function converts an integer to an ip

        :param ip: int
        :return: str
        """
        # int -> bytes -> ip
        return ".".join(map(str, ip.to_bytes(4, "big")))

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
        ip = int(addr / 100_000)
        port = int(addr - ip * 100_000)

        ip = self.__int2ip(ip)

        return f"{ip}:{port}"


# Pingers


@metrics.timing("ping")
async def ping(generator: IPGenerator, timeout: float = 1):
    """
    This function pings a server

    :param generator: IPGenerator The generator to get the next address from
    :param timeout: float The timeout for the ping
    :return: dict
    """
    with sentry_sdk.start_span(description=f"Ping", op="ping", sampled=True) as span:
        addr = generator.__next__()
        ip, port = addr.split(":")
        port = int(port)

        span.set_data("addr", {"ip": ip, "port": port})

        if ip.split(".")[-1] in ("0", "255"):
            return False

        try:
            await asyncio.wait_for(asyncio.open_connection(ip, port), timeout)
            logger.print(f"Connected to {ip}:{port}{' ' * 10}")
            generator.validate(addr)
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
        p = await MCSocket(ip, port, logger=logger)

        await p.handshake_status()
        await p.status_request()

        return True
    except (
        asyncio.TimeoutError,
        ConnectionRefusedError,
        OSError,
        AssertionError,
        EOFError,
    ):
        return False


# Scanners


async def async_scan_range(generator: IPGenerator, timeout: float = 1):
    """
    This function scans the network for devices

    :param generator: IPGenerator
    :param timeout: float
    """
    # assuming the slowest scan speeds, let's get the number of sockets per second this thread can handle
    maxSockets = int(max_pps * timeout * correction_factor)
    logger.debug(f"maxSockets: {maxSockets}")
    last_ETA = 0
    perc_of_max_pps = []

    try:
        for _ in range(0, len(generator.addrs), maxSockets):
            with sentry_sdk.start_transaction(op="scan_range", name="scan_range"):
                tStart = time.perf_counter()
                tasks = [
                    ping(generator, timeout=timeout)
                    for _ in range(min(maxSockets, len(generator.addrs)))
                ]
                await asyncio.gather(*tasks)
                tEnd = time.perf_counter()
                tasks = len(tasks)

                sentry_sdk.set_context("timing", {"duration": tEnd - tStart})
                sentry_sdk.set_context("tasks", {"count": tasks})

                ETA = datetime.datetime.now().timestamp() + (
                    len(generator.addrs) / tasks
                ) * (tEnd - tStart)

                if last_ETA == 0:
                    last_ETA = ETA
                else:
                    last_ETA = (last_ETA + ETA) / 2

                perc_of_max_pps.append(tasks / (tEnd - tStart) / max_pps * 100)

                logger.print(
                    f"{round(tasks / (tEnd - tStart), 2)}pps ({round((tasks / (tEnd - tStart)) / max_pps * 100, 2)}% of max), "
                    f"{round((generator.num_ips - len(generator.addrs)) / generator.num_ips * 100, 2)}% done, "
                    f"ETA: {datetime.datetime.fromtimestamp(ETA).strftime('%H:%M:%S')} (dur of {logger.auto_range_time(tEnd - tStart, 2)})"
                    f"{' ' * 20}",
                    end="\r",
                )

        generator.scan_complete = True
        new_cor = correction_factor * (2 - np.mean(perc_of_max_pps) / 100)
        logger.print(
            f"Scan speed: {round(np.mean(perc_of_max_pps), 2)}% of max pps, "
            f"new correction factor: {new_cor:.2f}"
        )
        with open(
            os.path.join(
                os.path.split(os.path.split(os.path.abspath(__file__))[0])[0],
                "privVars.py",
            ),
            "r+",
        ) as f:
            lines = f.readlines()
            for i, line in enumerate(lines):
                if "correction_factor =" in line:
                    lines[i] = f"correction_factor = {new_cor}\n"
                    break
            else:
                lines.append(f"correction_factor = {new_cor}\n")
            f.seek(0)
            f.writelines(lines)
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
    try:
        asyncio.run(async_scan_range(generator, timeout=timeout))
    except KeyboardInterrupt:
        generator.cancel()
        logger.print("Scan cancelled")


# Validators


def scan_valid(generator: IPGenerator):
    asyncio.run(async_scan_valid(generator))


async def async_scan_valid(generator: IPGenerator):
    """
    Tests if valid ips respond to status requests

    :param generator: IPGenerator
    """
    while not generator.scan_complete or len(generator.valid_addr) > 0:
        if len(generator.valid_addr) == 0:
            await asyncio.sleep(0.5)
            continue

        tasks = []

        tStart = time.perf_counter()
        async with asyncio.TaskGroup() as tg:
            for _ in range(min(len(generator.valid_addr), 5)):
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

        tEnd = time.perf_counter()
        logger.print(
            f"Validated {len(tasks)} servers in {tEnd - tStart:.2f}s, (avg of {len(tasks) / (tEnd - tStart):.2f}pps)"
        )
    else:
        logger.print("No servers remaining to validate")


def main(mask: str = "5.9.0.0/15", timeout: float = 0.2):
    generator = IPGenerator(mask, (25565, 25566))

    pps = len(generator.addrs) / timeout
    pps = min(pps, max_pps)

    logger.print(
        f"Scan of {len(generator.addrs)} ips started, sending at {pps} packets/s"
    )
    eta = len(generator.addrs) / pps
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
