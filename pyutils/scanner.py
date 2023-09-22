import json
import queue
import random
import threading
import time
import traceback
from multiprocessing.pool import ThreadPool

import masscan
from netaddr import IPNetwork


class Scanner:
    def __init__(self, logger_func, serverLib, max_thread_count=10, max_ping_rate=1000):
        self.STOP = False
        self.logger = logger_func
        self.que = queue.Queue()
        self.max_threads = max_thread_count
        self.max_pps = max_ping_rate
        self.serverLib = serverLib
        self.counts = [0]

    def stop(self):
        self.STOP = True

    def start(self, *, ip_ranges: list[str] | str = None):
        if not ip_ranges:
            self.logger.error("No ip ranges provided")
            return
        else:
            rngs = []
            if type(ip_ranges) == str:
                rng = IPNetwork(ip_ranges)
                rngs.extend([str(i).split("(")[0] for i in rng.subnet(24)])
            elif type(ip_ranges) == list:
                for rng in ip_ranges:
                    rng = IPNetwork(rng)
                    rngs.extend([str(i).split("(")[0] for i in rng.subnet(24)])
            else:
                self.logger.error("Invalid ip range type")
                return

            ip_ranges = rngs
            random.shuffle(ip_ranges)

        threading.Thread(target=self.stats).start()
        threading.Thread(target=self.test_starter, args=(self.logger,)).start()
        self.scan_starter(ip_ranges)

    def scan_range(self, ip_range):
        try:
            # step one, get a range of online ips
            scanner = masscan.PortScanner()
            scanner.scan(
                ip_range,
                ports="25560-25575",
                arguments="--rate=" + str(self.max_pps // self.max_threads),
            )

            hosts = json.loads(scanner.scan_result)["scan"]
            host_ips = hosts.keys()
            self.logger.debug(f"Found {len(host_ips)} hosts in {ip_range}") if len(
                host_ips
            ) > 0 else None

            for ip in host_ips:
                host = hosts[ip]
                for port in host:
                    if port["status"] == "open":
                        self.logger.debug(f"Found open port {port['port']} on {ip}")
                        self.que.put(ip + ":" + str(port["port"]))
                        self.counts[-1] += 1
        except Exception as err:
            self.logger.error(f"Error scanning {ip_range}: {err}")
            self.logger.print(traceback.format_exc())
            raise err

    def scan_starter(self, ip_list):
        self.logger.debug("Starting scans")
        # creates all the threads that run the scan_range function
        pool = ThreadPool(processes=self.max_threads)
        pool.map(self.scan_range, ip_list)

    def test_server(self, ip: str):
        self.logger.debug(f"Testing {ip}")
        ip, port = ip.split(":")
        self.serverLib.update(host=ip, port=port, fast=False)

    def test_starter(self):
        self.logger.debug("Starting tests")
        while not self.STOP:
            if self.que.qsize() > 0:
                ip = self.que.get()
                self.test_server(ip)
            else:
                self.logger.debug("No ips in que, sleeping")
                time.sleep(30)

    def stats(self):
        while True:
            while len(self.counts) > 100:
                self.counts.pop(0)

            self.logger.print(
                f"Scanned {self.counts[-1]} servers in the last hour, average of {sum(self.counts) / len(self.counts)} per hour"
            )
            self.counts.append(0)

            time.sleep(60 * 60)  # sleep for an hour
