import asyncio
import logging
import time

from pyutils.pycraft2 import Handshake, Status, packet
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

    **NB:** This class is an async class, you should await the initialization of the object.

    Example:

    ```python
    from pyutils.pycraft2.connector import MCSocket
    import asyncio

    async def main():
        mc = await MCSocket("localhost", 25565)
        print(mc.async_state)
        await mc.close()

    asyncio.run(main())
    ```
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.compress = None
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
        self.writer.write(data)
        await self.writer.drain()

    async def recv(self, n: int) -> bytes:
        try:
            return await asyncio.wait_for(self.reader.read(n), timeout=self.timeout)
        except (asyncio.TimeoutError, ConnectionResetError):
            return b""

    async def close(self):
        self.writer.close()
        await self.writer.wait_closed()

    async def send_packet(self, p: "S2S_0xFF"):
        tStart = time.perf_counter()

        assert isinstance(p, S2S_0xFF)

        if self.compress != -1:
            if len(p) > self.compress:
                p.compress()

        await p.send(self)

        tEnd = time.perf_counter()
        self.logger.debug(f"Sent packet: {hex(p.id)} in {tEnd - tStart:.2f} seconds")

    async def recv_packet(self, state: int, version: int) -> "S2CPacket":
        tStart = time.perf_counter()
        p = packet.S2CPacket(self, state, version)
        await p.read_response(self.compress)

        tEnd = time.perf_counter()
        self.logger.debug(
            f"Received packet: {hex(p.id)} in {tEnd - tStart:.2f} seconds"
        )

        return p

    def set_compression(self, threshold):
        self.compress = threshold

    def set_state(self, state):
        self.state = state

    def get_state(self):
        return self.state

    # Connection methods

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
