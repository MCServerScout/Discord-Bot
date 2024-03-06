import asyncio

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
        super().__init__(args, kwargs)
        self.compress = None
        self.state = None
        self.version = None

    async def __ainit__(self, host, port):
        """
        Connect to a Minecraft server.
        """

        self.reader, self.writer = await asyncio.open_connection(host, port)
        self.compress = -1
        self.addr = (host, port)
        self.state = 0
        self.version = 47

    async def send(self, data: bytes) -> None:
        self.writer.write(data)
        await self.writer.drain()

    async def recv(self, n: int) -> bytes:
        return await self.reader.read(n)

    async def close(self):
        self.writer.close()
        await self.writer.wait_closed()

    async def send_packet(self, p: "S2S_0xFF"):
        assert isinstance(p, S2S_0xFF)

        if self.compress != -1:
            if len(p) > self.compress:
                p.compress()

        await p.send(self)

    async def recv_packet(self, state: int, version: int) -> "S2CPacket":
        p = packet.S2CPacket(self, state, version)
        await p.read_response(self.compress)

        print(f"Received packet: {hex(p.id)}")

        return p

    def set_compression(self, threshold):
        self.compress = threshold

    def set_state(self, state):
        self.state = state

    def get_state(self):
        return self.state

    # Connection methods

    async def handshake_status(self, version_id: int):
        setattr(self.handshake_status, "__doc__", Handshake.C2S_0x00.__doc__)

        p = Handshake.C2S_0x00(
            protocol_version=version_id,
            server_address=self.addr[0],
            server_port=self.addr[1],
            next_state=1,
        )
        self.version = version_id
        await self.send_packet(p)

    async def handshake_login(self, version_id: int):
        setattr(self.handshake_login, "__doc__", Handshake.C2S_0x00.__doc__)

        p = Handshake.C2S_0x00(
            protocol_version=version_id,
            server_address=self.addr[0],
            server_port=self.addr[1],
            next_state=2,
        )
        self.version = version_id
        await self.send_packet(p)

    async def status_request(self) -> dict:
        setattr(self.status_request, "__doc__", Status.C2S_0x00.__doc__)

        p = Status.C2S_0x00()
        await self.send_packet(p)

        # get a response
        response = await self.recv_packet(States.STATUS, self.version)
        assert response.id == 0x00

        # read the response
        json_data = response.read_json()
        return json_data
