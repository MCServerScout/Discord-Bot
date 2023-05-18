"""Class for server connection and communication.
"""
import datetime
import json
import socket
import threading
import traceback
from typing import Optional

import mcstatus
from mcstatus.protocol.connection import Connection, TCPSocketConnection

from .database import Database
from .logger import Logger
from .text import Text


class Server:
    """Class for server connection and communication."""

    class ServerType:
        def __init__(self, ip, version, joinability):
            self.ip: str = ip
            self.version: int = version
            self.type: str = joinability

        def __str__(self):
            return f"ServerType(ip={self.ip}, version={self.version}, type={self.type})"

        def getType(self) -> str:
            return self.type

    def __init__(
        self,
        db: "Database",
        logger: "Logger",
        text: "Text",
    ):
        self.db = db
        self.logger = logger
        self.text = text

    def update(
        self,
        host: str,
        fast: bool = False,
        port: int = 25565,
    ) -> Optional[dict]:
        """
        Update a server and return a doc
        """

        try:
            # get the status response
            status = self.status(host)

            if status is None:
                self.logger.warning(
                    f"[server.update] Failed to get status for {host}")
                return None

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

            # if the server is in the db, then get the db doc
            if (
                self.db.col.find_one(
                    {"ip": status["ip"], "port": status["port"]})
                is not None
            ):
                dbVal = self.db.col.find_one(
                    {"ip": status["ip"], "port": status["port"]}
                )
                if dbVal is not None:
                    if "cracked" in dbVal:
                        status["cracked"] = status["cracked"] or dbVal["cracked"]

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
            else:
                self.logger.warning(
                    f"[server.update] Failed to get dbVal for {host}, making new entry"
                )
                self.updateDB(status)

            return status
        except Exception as err:
            self.logger.warning(f"[server.update] {err}")
            self.logger.print(f"[server.update] {traceback.format_exc()}")
            return None

    def status(
        self,
        ip: str,
        port: int = 25565,
        version: int = -1,
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
            if version == -1:
                # get info on the server
                server = mcstatus.JavaServer.lookup(
                    ip + ":" + str(port), timeout=5)
                try:
                    version = (
                        server.status().version.protocol if version == -1 else version
                    )
                except TimeoutError:
                    self.logger.print(
                        "[server.status] Connection error (timeout)")
                    return None
                except ConnectionRefusedError:
                    self.logger.print(
                        "[server.status] Connection error (refused)")
                    return None
                except Exception as err:
                    if (
                        "An existing connection was forcibly closed by the remote host"
                        in str(err)
                    ):
                        self.logger.error("[server.status] Connection error")
                        return None
                    else:
                        self.logger.error(f"[server.status] {err}")
                        self.logger.print(
                            f"[server.status] {traceback.format_exc()}")
                        return None

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
        version: int = -1,
        player_username: str = "Pilot1783",
    ) -> ServerType:
        try:
            # get info on the server
            server = mcstatus.JavaServer.lookup(ip + ":" + str(port))
            try:
                version = server.status().version.protocol if version == -1 else version
            except TimeoutError:
                self.logger.print("[server.join] Connection error (timeout)")
                return self.ServerType(ip, -1, "UNKNOWN")
            except ConnectionRefusedError:
                self.logger.print("[server.join] Connection error (refused)")
                return self.ServerType(ip, -1, "UNKNOWN")
            except Exception as err:
                if (
                    "An existing connection was forcibly closed by the remote host"
                    in str(err)
                ):
                    self.logger.print("[server.join] Connection error")
                    return self.ServerType(ip, -1, "UNKNOWN")
                else:
                    self.logger.error(f"[server.join] {err}")
                    self.logger.print(
                        f"[server.join] {traceback.format_exc()}")
                    return self.ServerType(ip, -1, "UNKNOWN")

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

            if version > 760:
                loginStart.write_varint(0)  # Packet ID
                loginStart.write_utf(player_username)  # Username
            else:
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
        except OSError:
            self.logger.print("[server.join] Server did not respond")
            return self.ServerType(ip, version, "UNKNOWN")
        except ConnectionRefusedError:
            self.logger.print("[server.join] Connection refused")
            return self.ServerType(ip, version, "OFFLINE")
        except ConnectionResetError:
            self.logger.print("[server.join] Connection reset")
            return self.ServerType(ip, version, "OFFLINE")
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
