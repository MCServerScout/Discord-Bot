"""Class for server connection and communication.
"""
import datetime
import json
import re
import socket
import threading
import traceback
from typing import Optional, Mapping, Any

import ipinfo
from mcstatus.protocol.connection import Connection, TCPSocketConnection

from .database import Database
from .logger import Logger
from .text import Text


class Server:
    """Class for server connection and communication."""

    class ServerType:
        def __init__(self, ip, version, joinability):
            self._ip: str = ip
            self._version: int = version
            self._type: str = joinability

        def __str__(self):
            return (
                f"ServerType(ip={self._ip}, version={self._version}, type={self._type})"
            )

        def get_type(self) -> str:
            return self._type

    def __init__(
            self,
            db: "Database",
            logger: "Logger",
            text: "Text",
            ipinfo_token: str,
    ):
        self.db = db
        self.logger = logger
        self.text = text
        self.ipinfoHandle = ipinfo.getHandler(ipinfo_token)

    def update(
            self,
            host: str,
            fast: bool = False,
            port: int = 25565,
    ) -> Optional[Mapping[str, Any]]:
        """
        Update a server and return a doc, returns either, None or Mapping[str, Any]
        """
        status = None
        try:
            status = {
                "ip": host,
                "port": port,
                "version": {"protocol": -1, "name": "UNKNOWN"},
                "description": "",
                "players": {"online": 0, "max": 0},
                "hasForgeData": False,
                "cracked": False,
                "lastSeen": 0,
            }
            geo = {}
            # fetch info from ipinfo
            try:
                if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", host):
                    geo_data = self.ipinfoHandle.getDetails(
                        status["ip"]
                    ).all  # technically, \
                    # this uses requests and not aiohttp and is not asynchronous
                    geo["lat"] = float(geo_data["latitude"])
                    geo["lon"] = float(geo_data["longitude"])
                    geo["country"] = str(geo_data["country"])
                    geo["city"] = str(geo_data["city"])
                    if "org" in geo_data:
                        geo["org"] = str(geo_data["org"])
            except Exception as err:
                self.logger.warning(f"Failed to get geo for {host}")
                self.logger.print(err)
                self.logger.print(f"{traceback.format_exc()}")

            if geo != {}:
                status["geo"] = geo
                if "org" in geo:
                    status["org"] = geo["org"]
                    # remove the org from the geo dict
                    del status["geo"]["org"]

            # if the server is in the db, then get the db doc
            if (
                    self.db.col.find_one(
                        {"ip": status["ip"], "port": status["port"]})
                    is not None
            ):
                db_val = self.db.col.find_one(
                    {"ip": status["ip"], "port": status["port"]}
                )
                status.update(db_val)
                status["description"] = self.text.motd_parse(
                    status["description"])
                status["cracked"] = db_val["cracked"] if "cracked" in db_val else False
            else:
                db_val = None

            # get the status response
            status2 = self.status(host)

            if status2 is None:
                self.logger.warning(f"Failed to get status for {host}")
                self.update_db(status) if status is not None else None
                return status
            else:
                status.update(status2)

            server_type = (
                self.join(ip=host, port=port,
                          version=status["version"]["protocol"])
                if not fast
                else self.ServerType(host, status["version"]["protocol"], "UNKNOWN")
            )

            status["cracked"] = server_type.get_type() == "CRACKED"

            status["ip"] = host
            status["port"] = port
            status["lastSeen"] = int(datetime.datetime.utcnow().timestamp())
            status["hasFavicon"] = "favicon" in status
            status["hasForgeData"] = server_type.get_type() == "MODDED"
            status["description"] = self.text.motd_parse(status["description"])
            if "sample" in status["players"]:
                for player in status["players"]["sample"]:
                    player["lastSeen"] = int(
                        datetime.datetime.utcnow().timestamp())

            if db_val is not None:
                # append the dbVal sample to the status sample
                if "sample" in db_val["players"] and "sample" in status["players"]:
                    for player in db_val["players"]["sample"]:
                        if player["name"] not in str(status["players"]["sample"]):
                            player["lastSeen"] = int(0)
                            list(status["players"]["sample"]).append(player)
            else:
                self.logger.warning(
                    f"Failed to get dbVal for {host}, making new entry")
            self.update_db(status)

            return status
        except Exception as err:
            self.logger.warning(err)
            self.logger.print(f"{traceback.format_exc()}")

            self.update_db(status) if status is not None else None

            if status is not None:
                return status
            else:
                return None

    def status(
            self,
            ip: str,
            port: int = 25565,
            version: int = 47,
    ) -> Optional[dict]:
        """Returns a status response dict

        Args:
            ip (str): The host to connect to
            port (int, optional): The port to connect to.
            Default to 25565.
            version (int, optional): The protocol version to use.
            Default to -1.

        Returns:
            Optional[dict]: The status response dict
        """
        try:
            connection = TCPSocketConnection((ip, port))

            # Send a handshake packet: ID, protocol version, server address, server port, intention to log in
            # This does not change between versions
            handshake = Connection()

            handshake.write_varint(0)  # Packet ID
            handshake.write_varint(version)  # Protocol version
            handshake.write_utf(ip)  # Server address
            handshake.write_ushort(int(port))  # Server port
            handshake.write_varint(1)  # Intention to get status

            connection.write_buffer(handshake)

            # Send status request packet
            # This does not change between versions
            request = Connection()

            request.write_varint(0)  # Packet ID
            connection.write_buffer(request)

            # Read response
            try:
                response = connection.read_buffer()
            except socket.error:
                self.logger.error("Connection error")
                return None
            res_id = response.read_varint()

            if res_id == -1:
                self.logger.error("Connection error")
                return None
            elif res_id != 0:
                self.logger.error("Invalid packet ID received: " + str(res_id))
                return None
            elif res_id == 0:
                length = response.read_varint()
                data = response.read(length)

                data = json.loads(data.decode("utf8"))
                return data
        except TimeoutError:
            self.logger.print("Connection error (timeout)")
            return None
        except ConnectionRefusedError:
            self.logger.print("Connection error (refused)")
            return None
        except socket.gaierror:
            self.logger.print("Connection error (invalid host)")
            return None
        except Exception as err:
            self.logger.warning(err)
            self.logger.print(f"{traceback.format_exc()}")
            return None

    def join(
            self,
            ip: str,
            port: int,
            version: int = 47,
            player_username: str = "Pilot1783",
    ) -> ServerType:
        try:
            connection = TCPSocketConnection((ip, port))
            # Send a handshake packet: ID, protocol version, server address, server port, intention to log in
            # This does not change between versions
            handshake = Connection()

            handshake.write_varint(0)  # Packet ID
            handshake.write_varint(version)  # Protocol version
            handshake.write_utf(ip)  # Server address
            handshake.write_ushort(int(port))  # Server port
            handshake.write_varint(2)  # Intention to login

            connection.write_buffer(handshake)

            # Send login start packet: ID, username, include sig data, has uuid, uuid
            login_start = Connection()

            login_start.write_varint(0)  # Packet ID
            login_start.write_utf(player_username)  # Username
            connection.write_buffer(login_start)

            # Read response
            response = connection.read_buffer()
            _id: int = response.read_varint()
            if _id == 2:
                self.logger.print("Logged in successfully")
                return self.ServerType(ip, version, "CRACKED")
            elif _id == 0:
                reason = response.read_utf()
                modded = "Forge" in reason
                if modded:
                    self.logger.print("Modded server")
                else:
                    self.logger.print("Vanilla server")
                return self.ServerType(
                    ip, version, "VANILLA" if not modded else "MODDED"
                )
            elif _id == 3:
                self.logger.print("Setting compression")
                compression_threshold = response.read_varint()
                self.logger.print(
                    f"Compression threshold: {compression_threshold}")

                response = connection.read_buffer()
                _id: int = response.read_varint()
            if _id == 1:
                self.logger.print("Logged in successfully")

                return self.ServerType(ip, version, "CRACKED")
            elif _id == 0:
                reason = response.read_utf()
                modded = "Forge" in reason
                if modded:
                    self.logger.print("Modded server")
                else:
                    self.logger.print("Vanilla server")
                return self.ServerType(
                    ip, version, "VANILLA" if not modded else "MODDED"
                )
            else:
                self.logger.warning("Unknown response: " + str(_id))
                try:
                    reason = response.read_utf()
                except TimeoutError:
                    return self.ServerType(ip, version, "OFFLINE")

                self.logger.debug("Reason: " + reason)
                return self.ServerType(ip, version, "UNKNOWN")
        except TimeoutError:
            self.logger.print("Connection error (timeout)")
            return self.ServerType(ip, version, "OFFLINE")
        except ConnectionRefusedError:
            self.logger.print("Connection refused")
            return self.ServerType(ip, version, "OFFLINE")
        except ConnectionResetError:
            self.logger.print("Connection reset")
            return self.ServerType(ip, version, "OFFLINE")
        except OSError:
            self.logger.print("Server did not respond")
            return self.ServerType(ip, version, "UNKNOWN")
        except Exception as err:
            self.logger.error(err)
            self.logger.print(f"{traceback.format_exc()}")
            return self.ServerType(ip, version, "OFFLINE")

    @staticmethod
    def resolve(host: str) -> str:
        """Resolves a hostname to an IP address

        Args:
            host (str): The hostname to resolve

        Returns:
            str: The IP address
        """
        if host.replace(".", "").isdigit():  # if host is an IP address
            return host

        return socket.gethostbyname(host)

    @staticmethod
    def res_hostname(ip: str) -> str:
        """Resolves an IP address to a hostname

        Args:
            ip (str): The IP address to resolve

        Returns:
            str: The hostname
        """
        return socket.gethostbyaddr(ip)[0]

    def update_db(self, data: dict):
        """Updates the database with the given data

        Args:
            data (dict): The data to update the database with
        """
        if "favicon" in data:
            del data["favicon"]

        threading.Thread(target=self._update_db, args=(data,)).start()

    def _update_db(self, data: dict):
        """Updates the database with the given data

        Args:
            data (dict): The data to update the database with
        """

        try:
            self.db.update_one(
                {"ip": data["ip"], "port": data["port"]},
                {"$set": data},
                upsert=True,
            )
        except Exception as err:
            self.logger.error(err)
            self.logger.print(f"{traceback.format_exc()}")
