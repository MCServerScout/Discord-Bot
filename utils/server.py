"""Class for server connection and communication.
"""
import datetime
import json
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

        def getType(self) -> str:
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

    async def update(
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
                "version": {"protocol": -1},
                "description": "",
            }
            geo = {}
            # fetch info from ipinfo
            try:
                geoData = self.ipinfoHandle.getDetails(status["ip"]).all
                geo["lat"] = float(geoData["latitude"])
                geo["lon"] = float(geoData["longitude"])
                geo["country"] = str(geoData["country"])
                geo["city"] = str(geoData["city"])
                if "hostname" in geoData:
                    geo["hostname"] = str(geoData["hostname"])
            except Exception as err:
                self.logger.warning(
                    f"[server.update] Failed to get geo for {host}")
                self.logger.print(f"[server.update] {err}")
                self.logger.print(f"[server.update] {traceback.format_exc()}")

            if geo != {}:
                status["geo"] = geo

            # if the server is in the db, then get the db doc
            if (
                self.db.col.find_one(
                    {"ip": status["ip"], "port": status["port"]})
                is not None
            ):
                dbVal = self.db.col.find_one(
                    {"ip": status["ip"], "port": status["port"]}
                )
                status.update(dbVal)
                status["description"] = self.text.motdParse(
                    status["description"])
                status["cracked"] = dbVal["cracked"] if "cracked" in dbVal else False
            else:
                dbVal = None

            # get the status response
            status2 = self.status(host)

            if status2 is None:
                self.logger.warning(
                    f"[server.update] Failed to get status for {host}")
                self.updateDB(status) if status is not None else None
                return status
            else:
                status.update(status2)

            server_type = (
                self.join(ip=host, port=port,
                          version=status["version"]["protocol"])
                if not fast
                else self.ServerType(host, status["version"]["protocol"], "UNKNOWN")
            )

            status["cracked"] = server_type.getType() == "CRACKED"

            status["ip"] = host
            status["port"] = port
            status["lastSeen"] = int(datetime.datetime.utcnow().timestamp())
            status["hasFavicon"] = "favicon" in status
            status["hasForgeData"] = server_type.getType() == "MODDED"
            status["description"] = self.text.motdParse(status["description"])

            if dbVal is not None:
                # append the dbVal sample to the status sample
                if "sample" in dbVal["players"] and "sample" in status["players"]:
                    for player in dbVal["players"]["sample"]:
                        if player not in status["players"]["sample"]:
                            status["players"]["sample"].append(player)
            else:
                self.logger.warning(
                    f"[server.update] Failed to get dbVal for {host}, making new entry"
                )
            self.updateDB(status)

            return status
        except Exception as err:
            self.logger.warning(f"[server.update] {err}")
            self.logger.print(f"[server.update] {traceback.format_exc()}")

            self.updateDB(status) if status is not None else None

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
                self.logger.error("[server.status] Connection error")
                return None
            resID = response.read_varint()

            if resID == -1:
                self.logger.error("[server.status] Connection error")
                return None
            elif resID != 0:
                self.logger.error(
                    "[server.status] Invalid packet ID received: " + str(resID)
                )
                return None
            elif resID == 0:
                length = response.read_varint()
                data = response.read(length)

                data = json.loads(data.decode("utf8"))
                return data
        except TimeoutError:
            self.logger.print("[server.status] Connection error (timeout)")
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
            loginStart = Connection()

            loginStart.write_varint(0)  # Packet ID
            loginStart.write_utf(player_username)  # Username
            connection.write_buffer(loginStart)

            # Read response
            response = connection.read_buffer()
            _id: int = response.read_varint()
            if _id == 2:
                self.logger.print("[server.join] Logged in successfully")
                return self.ServerType(ip, version, "CRACKED")
            elif _id == 0:
                reason = response.read_utf()
                modded = "Forge" in reason
                if modded:
                    self.logger.print("[server.join] Modded server")
                else:
                    self.logger.print("[server.join] Vanilla server")
                return self.ServerType(
                    ip, version, "VANILLA" if not modded else "MODDED"
                )
            elif _id == 3:
                self.logger.print("[server.join] Setting compression")
                compression_threshold = response.read_varint()
                self.logger.print(
                    f"[server.join] Compression threshold: {compression_threshold}"
                )

                response = connection.read_buffer()
                _id: int = response.read_varint()
            if _id == 1:
                self.logger.print("[server.join] Logged in successfully")

                return self.ServerType(ip, version, "CRACKED")
            elif _id == 0:
                reason = response.read_utf()
                modded = "Forge" in reason
                if modded:
                    self.logger.print("[server.join] Modded server")
                else:
                    self.logger.print("[server.join] Vanilla server")
                return self.ServerType(
                    ip, version, "VANILLA" if not modded else "MODDED"
                )
            else:
                self.logger.warning(
                    "[server.join] Unknown response: " + str(_id))
                try:
                    reason = response.read_utf()
                except Exception:
                    reason = "Unknown"

                self.logger.debug("[server.join] Reason: " + reason)
                return self.ServerType(ip, version, "UNKNOWN")
        except TimeoutError:
            self.logger.print("[server.join] Connection error (timeout)")
            return self.ServerType(ip, version, "OFFLINE")
        except ConnectionRefusedError:
            self.logger.print("[server.join] Connection refused")
            return self.ServerType(ip, version, "OFFLINE")
        except ConnectionResetError:
            self.logger.print("[server.join] Connection reset")
            return self.ServerType(ip, version, "OFFLINE")
        except OSError:
            self.logger.print("[server.join] Server did not respond")
            return self.ServerType(ip, version, "UNKNOWN")
        except Exception as err:
            self.logger.error(f"[server.join] {err}")
            self.logger.print(f"[server.join] {traceback.format_exc()}")
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
    def resHostname(ip: str) -> str:
        """Resolves an IP address to a hostname

        Args:
            ip (str): The IP address to resolve

        Returns:
            str: The hostname
        """
        return socket.gethostbyaddr(ip)[0]

    def updateDB(self, data: dict):
        """Updates the database with the given data

        Args:
            data (dict): The data to update the database with
        """
        if "favicon" in data:
            del data["favicon"]

        threading.Thread(target=self._updateDB, args=(data,)).start()

    def _updateDB(self, data: dict):
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
            self.logger.error(f"[server._updateDB] {err}")
            self.logger.print(f"[server._updateDB] {traceback.format_exc()}")
