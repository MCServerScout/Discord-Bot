import asyncio
import logging
import os
import time
from hashlib import sha1

import aiohttp
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import load_der_public_key

from pyutils.pycraft2 import Handshake, Status, Login, packet
from pyutils.pycraft2.packet import S2S_0xFF, States, S2CPacket


class AsyncObj:
    def __init__(self, *args, **kwargs):
        """
        Standard constructor used for arguments pass
        Do not override. Use __ainit__ instead
        """
        self.__storedargs = args, kwargs
        self.async_initialized = False

    async def __ainit__(self, *args, **kwargs):
        """Async constructor, you should implement this"""

    async def __initobj(self):
        """Crutch used for __await__ after spawning"""
        assert not self.async_initialized
        self.async_initialized = True
        await self.__ainit__(
            *self.__storedargs[0], **self.__storedargs[1]
        )  # pass the parameters to __ainit__ that passed to __init__
        return self

    def __await__(self):
        return self.__initobj().__await__()

    def __init_subclass__(cls, **kwargs):
        assert asyncio.iscoroutinefunction(cls.__ainit__)  # __ainit__ must be async

    @property
    def async_state(self):
        if not self.async_initialized:
            return "[initialization pending]"
        return "[initialization done and successful]"


class MCSocket(AsyncObj):
    """
    Helper class to ease the connection to a Minecraft server.

    **NB: ** This class is an async class, you should await the initialization of the object.

    Example:

    ```python
    from pyutils.pycraft2.connector import MCSocket
    import asyncio

    Async def main():
        mc = await MCSocket("localhost", 25565)
        print(mc.async_state)
        await mc.close()

    Asyncio.run(main())
    ```
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__cipher = None
        self.__shared_secret = None
        self.compress = None
        self.encrypting = None
        self.state = None
        self.version = None

    async def __ainit__(
        self,
        host,
        port: int = None,
        timeout: float = 0.2,
        logger=logging.getLogger("pycraft2.connector"),
    ):
        """
        Connect to a Minecraft server.
        """

        if isinstance(host, str) and port is None:
            host = host.split(":")
            host[1] = int(host[1])
            host, port = host

        self.reader, self.writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        self.compress = -1
        self.addr = (host, port)
        self.state = 0
        self.version = 47
        self.timeout = timeout
        self.logger = logger

    async def send(self, data: bytes) -> None:
        """
        Send data to the server

        Args:
            data (bytes): The data to send
        """

        if self.__cipher is not None:
            data = self.__cipher.encryptor().update(data)

        self.writer.write(data)
        await self.writer.drain()

    async def recv(self, n: int) -> bytes:
        """
        Receive data from the server

        Args:
            n (int): The number of bytes to receive

        Returns:
            bytes: The data received or None
                if the connection was reset or timed out
        """

        try:
            data = await asyncio.wait_for(self.reader.read(n), timeout=self.timeout)

            if self.__cipher is not None:
                data = self.__cipher.decryptor().update(data)

            return data
        except (asyncio.TimeoutError, ConnectionResetError):
            return b""

    async def close(self):
        self.writer.close()
        await self.writer.wait_closed()

    async def send_packet(self, p: "S2S_0xFF"):
        """
        Send a packet to the server

        Args:
            p (S2S_0xFF): The packet to send
        """

        t_start = time.perf_counter()

        assert isinstance(p, S2S_0xFF)

        if self.compress != -1 and len(p) > self.compress:
            p.compress()

        await p.send(self)

        t_end = time.perf_counter()
        self.logger.debug(f"Sent packet: {hex(p.id)} in {t_end - t_start:.2f} seconds")

    async def recv_packet(self, state: int, version: int) -> "S2CPacket":
        """
        Receive a packet from the server

        Args:
            state (int): The state of the connection
            version (int): The version of the protocol

        Returns:
            S2CPacket: The packet received
        """

        t_start = time.perf_counter()
        p = packet.S2CPacket(self, state=state, version=version)
        await p.read_response(self.compress)

        t_end = time.perf_counter()
        self.logger.debug(
            f"Received packet: {hex(p.id)} in {t_end - t_start:.2f} seconds"
        )

        return p

    def set_compression(self, threshold):
        self.compress = threshold

    def set_state(self, state):
        self.state = state

    def get_state(self):
        return self.state

    @staticmethod
    def classify_packet(p: "S2S_0xFF", state: int, version: int) -> "S2S_0xFF":
        """
        Classify a packet based on its ID

        Args:
            p (S2S_0xFF): The packet to classify
            state (int): The state of the connection
            version (int): The version of the protocol

        Returns:
            S2S_0xFF: The classified packet

        Raises:
            ValueError: If the state is handshake and the packet is not a handshake packet
            ValueError: If the state is status and the packet is not a status packet
            ValueError: If the state is login and the packet is not a login packet
            ValueError: If the state is unknown
        """
        if state == States.HANDSHAKE:
            raise ValueError("No S2S packets in handshake state")
        elif state == States.STATUS:
            match p.id:
                case 0x00:
                    # status response
                    data_args = {}
                    for k, v in Status.S2C_0x00._dataTypes(None).items():
                        data_args[k] = p.read_type(v)
                    return Status.S2C_0x00(version=version, **data_args)
                case 0x01:
                    # status ping
                    data_args = {}
                    for k, v in Status.S2C_0x01._dataTypes(None).items():
                        data_args[k] = p.read_type(v)
                    return Status.S2C_0x01(version=version, **data_args)
                case _:
                    raise ValueError(f"Unknown status packet {hex(p.id)}")
        elif state == States.LOGIN:
            match p.id:
                case 0x00:
                    # login disconnect
                    data_args = {}
                    for k, v in Login.S2C_0x00._dataTypes(None).items():
                        data_args[k] = p.read_type(v)
                    return Login.S2C_0x00(version=version, **data_args)
                case 0x01:
                    # login encryption request
                    data_args = {}
                    for k, v in Login.S2C_0x01._dataTypes(None).items():
                        data_args[k] = p.read_type(v)
                    return Login.S2C_0x01(version=version, **data_args)
                case 0x02:
                    # login success
                    data_args = {}
                    for k, v in Login.S2C_0x02._dataTypes(None).items():
                        data_args[k] = p.read_type(v)
                    return Login.S2C_0x02(version=version, **data_args)
                case 0x03:
                    # login set compression
                    data_args = {}
                    for k, v in Login.S2C_0x03._dataTypes(None).items():
                        data_args[k] = p.read_type(v)
                    return Login.S2C_0x03(version=version, **data_args)
                case 0x04:
                    # login plugin request
                    data_args = {}
                    for k, v in Login.S2C_0x04._dataTypes(None).items():
                        data_args[k] = p.read_type(v)
                    return Login.S2C_0x04(version=version, **data_args)
                case _:
                    raise ValueError(f"Unknown login packet {hex(p.id)}")
        else:
            raise ValueError(f"Unknown state {state}")

    @staticmethod
    async def attempt_session_join(verify_hash: str, mc_token: str, profile: dict):
        async with aiohttp.ClientSession() as session, session.post(
            "https://sessionserver.mojang.com/session/minecraft/join",
            json={
                "accessToken": mc_token,
                "selectedProfile": {
                    "id": profile["id"].replace("-", ""),
                    "name": profile["name"],
                },
                "serverId": verify_hash,
            },
            headers={
                "Content-Type": "application/json",
            },
        ) as resp:
            return resp.status

    # Encryption methods

    def verify_hash(self, server_id: bytes, public_key: bytes) -> str:
        sha1_hash = sha1()
        sha1_hash.update(server_id)
        sha1_hash.update(self.__shared_secret)
        sha1_hash.update(public_key)

        return sha1_hash.hexdigest()

    def load_private_cipher(self):
        assert self.__shared_secret is not None, "Shared secret is not set"
        assert self.__cipher is None, "Cipher is already set"

        self.__cipher = Cipher(
            # key
            algorithms.AES(self.__shared_secret),
            # iv
            modes.CFB8(self.__shared_secret),
        )

    # Status methods
    async def handshake_status(self, version_id: int = 47):
        """
        Send a handshake packet to the server

        Args:
            version_id (int, optional): The version of the protocol. Defaults to 47.
        """

        p = Handshake.C2S_0x00(
            protocol_version=version_id,
            server_address=self.addr[0],
            server_port=self.addr[1],
            next_state=1,
        )
        self.version = version_id
        await self.send_packet(p)

    async def status_request(self) -> dict:
        """
        Send a status request to the server

        Returns:
            dict: The response from the server

        Raises:
            AssertionError: If the response is not a status response
        """

        p = Status.C2S_0x00()
        await self.send_packet(p)

        # get a response
        response = await self.recv_packet(States.STATUS, self.version)

        if response.id == 0x54 and response.read(1) == b"T":
            # this is a web server, not a minecraft server
            raise ConnectionError("This is a web server, not a minecraft server")

        if response.id != 0x00:
            self.logger.debug(
                f"Expected status response (0x00), got {hex(response.id)} with data {response.read(len(response))}"
            )
            raise AssertionError(
                f"Expected status response (0x00), got {hex(response.id)} with data {response.read(len(response))}"
            )

        # read the response
        json_data = response.read_json()
        return json_data

    async def status_ping(self, payload: int) -> int:
        """
        Send a status ping to the server

        Args:
            payload (int): The payload to send to the server

        Returns:
            int: The response from the server

        Raises:
            AssertionError: If the response is not a status response
        """

        p = Status.C2S_0x01(payload)
        await self.send_packet(p)

        # get a response
        response = await self.recv_packet(States.STATUS, self.version)

        if response.id != 0x01:
            self.logger.debug(
                f"Expected status response (0x01), got {hex(response.id)} with data {response.read(len(response))}"
            )
            raise AssertionError(
                f"Expected status response (0x01), got {hex(response.id)} with data {response.read(len(response))}"
            )

        # read the response
        return response.read_long()

    # Login methods

    async def handshake_login(self, version_id: int):
        """
        Send a handshake packet to the server

        Args:
            version_id (int): The version of the protocol.
        """

        p = Handshake.C2S_0x00(
            protocol_version=version_id,
            server_address=self.addr[0],
            server_port=self.addr[1],
            next_state=2,
        )
        self.version = version_id
        await self.send_packet(p)

    async def login(self, mc_token: str, username: str = "", uuid: str = ""):
        """
        Send a login start packet to the server
        You must provide either a username or a UUID (UUID is preferred and overrides the username)

        Args:
            mc_token (str): The Mojang access token
            username (str): The username to use
            uuid (str): The UUID to use

        Raises:
            ValueError: If neither a username nor a UUID is provided
            ValueError: If the UUID is invalid
            ValueError: If the username is invalid
            ConnectionError: If the server disconnects
        """

        if not uuid and not username:
            raise ValueError("You must provide either a username or a UUID")

        if uuid:
            assert len(uuid) == 36, "UUID must be 36 characters long"
            assert int(
                uuid.replace("-", ""), 16
            ), "UUID must be a valid hexadecimal number"
            assert (
                int(uuid.replace("-", ""), 16) > 0
            ), "UUID must be a valid hexadecimal number"
            assert (
                int(uuid.replace("-", ""), 16) < 2**128
            ), "UUID must be a valid hexadecimal number"

            # we need to get the username from the UUID
            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    "https://sessionserver.mojang.com/session/minecraft/profile/"
                    + uuid.replace("-", "")
                ) as resp,
            ):
                if resp.status == 200:
                    username = (await resp.json())["name"]
                else:
                    raise ValueError("Invalid UUID")
        elif username:
            assert len(username) <= 16, "Username must be 16 characters or less"

            # we need to get the UUID from the username
            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    "https://api.mojang.com/users/profiles/minecraft/" + username
                ) as resp,
            ):
                if resp.status == 200:
                    uuid = (await resp.json())["id"]
                    uuid = f"{uuid[:8]}-{uuid[8:12]}-{uuid[12:16]}-{uuid[16:20]}-{uuid[20:]}"
                else:
                    raise ValueError("Invalid username")
        else:
            raise ValueError("You must provide either a username or a UUID")

        p = Login.C2S_0x00(name=username, uuid=uuid)
        await self.send_packet(p)

        # receive the encryption request
        p = await self.recv_packet(States.LOGIN, self.version)
        p = self.classify_packet(p, States.LOGIN, self.version)

        match p:
            case Login.S2C_0x03():
                # set compression
                self.set_compression(p["threshold"])
                # receive another packet
                p = await self.recv_packet(States.LOGIN, self.version)
            case Login.S2C_0x00():
                # disconnect
                raise ConnectionError(p["reason"])
            case Login.S2C_0x04():
                # plugin request
                raise ConnectionError("Plugin request is not supported")
            case Login.S2C_0x02():
                # login success
                return p
            case Login.S2C_0x01():
                pass
            case _:
                raise ConnectionError("Unexpected packet: " + str(p))

        # encryption request

        server_id: bytes = bytes(p["Server ID"])  # should be empty
        public_key: bytes = p["Public Key"]
        verify_token: bytes = p["Verify Token"]

        self.__shared_secret = os.urandom(16)
        self.load_private_cipher()

        verify_hash = self.verify_hash(server_id, public_key)

        public_cipher = load_der_public_key(public_key, default_backend())

        # send a session join request
        for _ in range(5):
            if (
                await self.attempt_session_join(
                    verify_hash, mc_token, {"id": uuid, "name": username}
                )
                == 204
            ):
                break
            await asyncio.sleep(1)
        else:
            raise ConnectionError("Failed to join session after 5 attempts")

        self.encrypting = True

        # send a response
        enc_shared_secret = public_cipher.encrypt(self.__shared_secret, PKCS1v15())
        enc_verify_token = public_cipher.encrypt(verify_token, PKCS1v15())

        p = Login.C2S_0x01(
            shared_secret=enc_shared_secret,
            public_key=enc_verify_token,
            version=self.version,
        )
        await self.send_packet(p)

        # get a response
        p = await self.recv_packet(States.LOGIN, self.version)
        p = self.classify_packet(p, States.LOGIN, self.version)

        match p:
            case Login.S2C_0x02():
                # login success
                return p
            case Login.S2C_0x00():
                # disconnect
                raise ConnectionError(p["reason"])
            case Login.S2C_0x04():
                # plugin request
                raise ConnectionError("Plugin request is not supported")
            case Login.S2C_0x03():
                # set compression
                self.set_compression(p["threshold"])
                # receive another packet
                p = await self.recv_packet(States.LOGIN, self.version)
            case _:
                raise ConnectionError("Unexpected packet: " + str(p))

        # send a login ack
        p = Login.C2S_0x03()
        await self.send_packet(p)
