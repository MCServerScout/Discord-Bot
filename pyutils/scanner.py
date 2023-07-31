import json
import queue
import threading
import time
import traceback
from multiprocessing.pool import ThreadPool

import masscan


class Scanner:
    def __init__(self, logger_func, serverLib, max_thread_count=10, max_ping_rate=1000):
        self.STOP = False
        self.logger = logger_func
        self.que = queue.Queue()
        self.max_threads = max_thread_count
        self.max_pps = max_ping_rate
        self.serverLib = serverLib

    def stop(self):
        self.STOP = True

    def start(self, *, ip_ranges=None):
        if not ip_ranges:
            self.logger.error("No ip ranges provided")
            return
        threading.Thread(target=self.test_starter, args=(self.logger,)).start()
        self.scan_starter(ip_ranges)

    def scan_range(self, ip_range):
        try:
            # step one, get a range of online ips
            self.logger.debug(f"Scanning {ip_range}")
            scanner = masscan.PortScanner()
            scanner.scan(
                ip_range,
                ports="25560-25575",
                arguments="--rate=" + str(self.max_pps // self.max_threads),
            )

            hosts = json.loads(scanner.scan_result)["scan"]
            host_ips = hosts.keys()
            self.logger.debug(f"Found {len(host_ips)} hosts in {ip_range}")

            for ip in host_ips:
                host = hosts[ip]
                for port in host:
                    if port["status"] == "open":
                        self.logger.print(
                            f"Found open port {port['port']} on {ip}")
                        self.que.put(ip + ":" + str(port["port"]))
        except Exception as err:
            self.logger.error(f"Error scanning {ip_range}: {err}")
            self.logger.print(traceback.format_exc())
            raise err

    def scan_starter(self, ip_list):
        self.logger.print("Starting scans")
        # creates all the threads that run the scan_range function
        pool = ThreadPool(processes=self.max_threads)
        pool.map(self.scan_range, ip_list)

    def test_server(self, ip: str):
        self.logger.debug(f"Testing {ip}")
        ip, port = ip.split(":")
        self.serverLib.update(host=ip, port=port, fast=False)

    def test_starter(self):
        self.logger.print("Starting tests")
        while not self.STOP:
            if self.que.qsize() > 0:
                ip = self.que.get()
                self.test_server(ip)
            else:
                self.logger.debug("No ips in que, sleeping")
                time.sleep(30)
