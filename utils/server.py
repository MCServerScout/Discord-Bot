"""Class for server connection and communication.
"""
import datetime
import json
import socket
import threading
import traceback
from typing import Optional

import mcstatus
from bson import DatetimeMS
from mcstatus.protocol.connection import Connection, TCPSocketConnection

from .database import Database
from .logger import Logger


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
    ):
        self.db = db
        self.logger = logger

    def update(
            self,
            host: str,
            fast: bool = False,
            port: int = 25565,
    ) -> Optional[dict]:
        """
        Update a server and return a doc similar to:
        {
            "host": {
                "ip": "127.0.0.1",
                "hostname": "localhost",
                "port": 25565,
            }
            "version": {
                "name": "1.19.3",
                "protocol": 761
            },
            "players": {
                "max": 100,
                "online": 5,
                "sample": [
                    {
                        "name": "thinkofdeath",
                        "id": "4566e69f-c907-48ee-8d71-d7ba5aa00d20"
                    },
                ]
            },
            "world": {
                "signs": [
                    {
                        "pos": {0,0,0},
                        "text": "Hello World!",
                    },
                ]
            },
            "description": {
                "text": "Hello world!"
            },
            "favicon": "data:image/png;base64,<data>",
            "cracked": false,
            "online": Date(12345),
            "enforcesSecureChat": true
        }
        """

        try:
            # check if the server is online
            try:
                mcstatus.JavaServer.lookup(host).ping()
            except socket.gaierror:
                return None

            # get the status response
            status = self.status(host)

            if status is None:
                return None

            server_type = (
                self.join(host, status["version"]["protocol"])
                if not fast
                else self.ServerType(host, status["version"]["protocol"], "UNKNOWN")
            )

            if server_type.getType() == "CRACKED":
                status["cracked"] = True
            else:
                status["cracked"] = False

            status["ip"] = host
            status["port"] = port
            status["online"] = DatetimeMS(int(datetime.datetime.utcnow().timestamp() * 1000))

            # if the server is in the db, then get the db doc
            if self.db.col.find_one({"ip": status["ip"]}) is not None:
                dbVal = self.db.col.find_one({"ip": status["ip"]})
                status["cracked"] = (
                        status["cracked"]
                        or dbVal[
                            "cracked"
                        ]
                )
                self.updateDB(status)
            else:
                self.updateDB(status)

            return status
        except Exception:
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

        # get info on the server
        server = mcstatus.JavaServer.lookup(ip + ":" + str(port))
        try:
            version = server.status().version.protocol if version == -1 else version
        except TimeoutError:
            self.logger.error(f"[server.status] Connection error (timeout)")
            return None
        except ConnectionRefusedError:
            self.logger.error(f"[server.status] Connection error (refused)")
            return None
        except Exception as err:
            if "An existing connection was forcibly closed by the remote host" in str(err):
                self.logger.error(f"[server.status] Connection error")
                return None
            else:
                self.logger.error(f"[server.status] {err}")
                self.logger.print(f"[server.status] {traceback.format_exc()}")
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
            self.logger.error(f"[server.status] Connection error")
            return None
        resID = response.read_varint()

        if resID == -1:
            self.logger.error(f"[server.status] Connection error")
            return None
        elif resID != 0:
            self.logger.error("[server.status] Invalid packet ID received: " + str(resID))
            return None
        elif resID == 0:
            length = response.read_varint()
            data = response.read(length)

            data = json.loads(data.decode("utf8"))
            return data

    def join(
        self,
        ip: str,
        port: int,
        version: int = -1,
        player_username: str = "Pilot1782",
    ) -> ServerType:
        try:
            # get info on the server
            server = mcstatus.JavaServer.lookup(ip + ":" + str(port))
            try:
                version = server.status().version.protocol if version == -1 else version
            except TimeoutError:
                self.logger.error(f"[server.join] Connection error (timeout)")
                return self.ServerType(ip, -1, "UNKNOWN")
            except ConnectionRefusedError:
                self.logger.error(f"[server.join] Connection error (refused)")
                return self.ServerType(ip, -1, "UNKNOWN")
            except Exception as err:
                if "An existing connection was forcibly closed by the remote host" in str(err):
                    self.logger.error(f"[server.join] Connection error")
                    return self.ServerType(ip, -1, "UNKNOWN")
                else:
                    self.logger.error(f"[server.join] {err}")
                    self.logger.print(f"[server.join] {traceback.format_exc()}")
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
                return self.ServerType(ip, version, "VANILLA" if not modded else "MODDED")
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
            else:
                self.logger.error("[server.join] Unknown response: " + str(_id))
                try:
                    reason = response.read_utf()
                except Exception:
                    reason = "Unknown"

                self.logger.debug("[server.join] Reason: " + reason)
                return self.ServerType(ip, version, "UNKNOWN")
        except TimeoutError:
            self.logger.print("[server.join] Server timed out")
            return self.ServerType(ip, version, "OFFLINE")
        except OSError:
            self.logger.error(
                "[server.join] Server did not respond:\n" + traceback.format_exc()
            )
            return self.ServerType(ip, version, "UNKNOWN")
        except ConnectionRefusedError:
            self.logger.error("[server.join] Connection refused")
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
        threading.Thread(target=self._updateDB, args=(data,)).start()

    def _updateDB(self, data: dict):
        """Updates the database with the given data

        Args:
            data (dict): The data to update the database with
        """

        self.db.update_one(
            {"host.ip": data["ip"]},
            {"$set": {data}},
            upsert=True,
        )
