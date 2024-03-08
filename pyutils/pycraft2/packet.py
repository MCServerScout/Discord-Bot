import json
import struct
import zlib
from ctypes import c_int32 as signed_int32
from ctypes import c_uint32 as unsigned_int32


class Locks:
    # only allow for encryption of data
    ENC_ONLY = "enc_only"
    # only allow for decryption of data
    DEC_ONLY = "dec_only"
    # allow for both encryption and decryption of data
    ENC_DEC = "enc_dec"
    # no locks
    NONE = "none"
    # read only
    READ_ONLY = "read_only"
    # write only
    WRITE_ONLY = "write_only"


class States:
    HANDSHAKE = 0
    STATUS = 1
    LOGIN = 2
    CONFIGURATION = 3
    PLAY = 4


class DataTypes:
    VARINT = "VarInt"
    VARLONG = "VarLong"
    STRING = "String"
    USHORT = "Unsigned Short"
    SHORT = "Short"
    ULONG = "Unsigned Long"
    LONG = "Long"
    UUID = "UUID"
    BOOL = "Boolean"
    BYTE_ARRAY = "Byte Array"


# https://wiki.vg/Protocol#Packet_format
class Packet:
    slots = (
        "locks",
        "__data",
    )

    def __init__(self, data: bytes):
        self.__data = data
        self.locks = None

    def __str__(self):
        return self.__data

    def __repr__(self):
        return self.__data

    def __len__(self):
        return len(self.__data)

    def write(self, data: bytes):
        self.__data += data

    def read(self, length: int):
        result = self.__data[:length]
        self.__data = self.__data[length:]
        return result

    async def send(self, _socket):
        self.__data = self.encode_varint(len(self.__data)) + self.__data
        _socket.send(self.__data)

    def compress(self):
        cdata = zlib.compress(self.__data)
        cdata_len = len(cdata)

        """
        Compressed?  Field Name	    Field Type	Notes
        No	         Packet Length	VarInt	    Length of (Data Length) + Compressed length of (Packet ID + Data)
        No	         Data Length	VarInt	    Length of uncompressed (Packet ID + Data) or 0
        Yes	         Packet ID	    VarInt	    zlib compressed packet ID (see the sections below)
        Yes          Data	        Byte Array  zlib compressed packet data (see the sections below)
        """

        self.__data = self.encode_varint(cdata_len) + cdata

        self.locks = Locks.ENC_DEC

    @staticmethod
    def encode_varint(value: int):
        """Write varint with value ``value`` to ``self``.

        :param value: The Maximum is ``2 ** 31-1 `` the minimum is ``-(2 ** 31)``.
        :raises ValueError: If value is out of range.
        """
        remaining = unsigned_int32(value).value
        out = b""
        for _ in range(5):
            if not remaining & -0x80:  # remaining & ~0x7F == 0:
                out += struct.pack("!B", remaining)
                if value > 2**31 - 1 or value < -(2**31):
                    break
                return out
            out += struct.pack("!B", remaining & 0x7F | 0x80)
            remaining >>= 7
        raise ValueError(f'The value "{value}" is too big to send in a varint')

    @staticmethod
    def encode_varlong(value: int):
        """Write varlong with value ``value`` to ``self``.

        :param value: The Maximum is ``2 ** 63-1 `` the minimum is ``-(2 ** 63)``.
        :raises ValueError: If value is out of range.
        """
        remaining = unsigned_int32(value).value
        out = b""
        for _ in range(10):
            if not remaining & -0x80:
                out += struct.pack("!B", remaining)
                if value > 2**63 - 1 or value < -(2**63):
                    break
                return out
            out += struct.pack("!B", remaining & 0x7F | 0x80)
            remaining >>= 7
        raise ValueError(f'The value "{value}" is too big to send in a varlong')

    def encode_utf8(self, string: str):
        """Write utf-8 string with value ``string`` to ``self``.

        :param string: The string to write.
        """
        return self.encode_varint(len(string)) + string.encode("utf-8")

    def encode_string(self, string: str):
        """Write string with value ``string`` to ``self``.

        :param string: The string to write.
        """
        return self.encode_utf8(string)

    @staticmethod
    def encode_ushort(value: int):
        """Write unsigned short with value ``value`` to ``self``.

        :param value: The Maximum is 2 ** 16-1 `` the minimum is 0.
        :raises ValueError: If value is out of range.
        """
        if value < 0 or value > 2**16 - 1:
            raise ValueError(f"The value {value} is out of range for an unsigned short")
        return struct.pack("!H", value)

    @staticmethod
    def encode_short(value: int):
        """Write short with value ``value`` to ``self``.

        :param value: The Maximum is ``2 ** 15-1 `` the minimum is ``-(2 ** 15)``.
        :raises ValueError: If value is out of range.
        """
        if value < -(2**15) or value > 2**15 - 1:
            raise ValueError(f"The value {value} is out of range for a short")
        return struct.pack("!h", value)

    @staticmethod
    def encode_ulong(value: int):
        """Write unsigned long with value ``value`` to ``self``.

        :param value: The Maximum is 2 ** 64-1 `` the minimum is 0.
        :raises ValueError: If value is out of range.
        """
        if value < 0 or value > 2**64 - 1:
            raise ValueError(f"The value {value} is out of range for an unsigned long")
        return struct.pack("!Q", value)

    @staticmethod
    def encode_long(value: int):
        """Write long with value ``value`` to ``self``.

        :param value: The Maximum is ``2 ** 63-1 `` the minimum is ``-(2 ** 63)``.
        :raises ValueError: If value is out of range.
        """
        if value < -(2**63) or value > 2**63 - 1:
            raise ValueError(f"The value {value} is out of range for a long")
        return struct.pack("!q", value)

    def encode_uuid(self, value: str):
        """Write a 128-bit UUID with value ``value`` to ``self``.

        :param value: The value to write.
        """
        uuid = value.replace("-", "")

        uuid1 = int(uuid[:16], 16)
        uuid2 = int(uuid[16:], 16)

        return self.encode_ulong(uuid1) + self.encode_ulong(uuid2)

    @staticmethod
    def encode_bool(value: bool):
        """Write bool with value ``value`` to ``self``.

        :param value: The value to write.
        """
        return struct.pack("!?", value)

    def read_varint(self):
        result = 0
        for i in range(5):
            part = (self.read(1))[0]
            result |= (part & 0x7F) << 7 * i
            if not part & 0x80:
                return signed_int32(result).value
        raise ValueError("VarInt is too big")

    def read_varlong(self):
        result = 0
        for i in range(10):
            byte = self.read(1)
            result |= (byte & 0x7F) << 7 * i
            if not byte & 0x80:
                break
        return result

    def read_string(self):
        length = self.read_varint()
        return self.read(length).decode("utf-8")

    def read_ushort(self):
        return struct.unpack("!H", self.read(2))[0]

    def read_short(self):
        return struct.unpack("!h", self.read(2))[0]

    def read_ulong(self):
        return struct.unpack("!Q", self.read(8))[0]

    def read_long(self):
        return struct.unpack("!q", self.read(8))[0]

    def read_uuid(self):
        uuid1 = self.read_ulong()
        uuid2 = self.read_ulong()

        return f"{uuid1:016x}-{uuid2:016x}"

    def read_bool(self):
        return struct.unpack("!?", self.read(1))[0]


class S2CPacket(Packet):
    def __init__(self, _socket, state: int, version: int):
        super().__init__(b"")
        self.socket = _socket
        self.state = state
        self.version = version
        self.name = "S2C Packet ..."
        self.id = 0xFF

    async def recv(self, length, ignore_exc=False):
        result = b""
        while len(result) < length:
            try:
                new = await self.socket.recv(length - len(result))
            except TimeoutError:
                new = b""
            if not new and not ignore_exc:
                raise EOFError(
                    f"Connection closed with {length - len(result)} bytes remaining"
                )
            elif not new:
                self.socket.logger.debug(
                    f"IGNORED: Connection closed with {length - len(result)} bytes remaining"
                )
                return result
            result += new
        return result

    async def read_packet_length(self):
        self.write(await self.socket.recv(3))

        result = 0
        for i in range(3):
            part = self.read(1)
            if not part:
                raise EOFError("Connection closed")

            part = part[0]
            result |= (part & 0x7F) << 7 * i
            if not part & 0x80:
                return result - 1
        raise ValueError("VarInt is too big")

    async def read_response(self, comp_threshold: int = -1):
        length = await self.read_packet_length()

        self.socket.logger.debug(f"Packet length: {length}")
        packet = await self.recv(length, ignore_exc=True)
        self.write(packet)

        if comp_threshold == -1:
            self.id = self.read_varint()
        else:
            expected_len = self.read_varint()
            assert expected_len >= 0, f"Data length is negative: {expected_len}"

            # no compression
            if expected_len == 0:
                self.id = self.read_varint()
            else:
                uncomp_data = zlib.decompress(self.read(len(self)))

                assert (
                    len(uncomp_data) == expected_len
                ), f"Expected length: {expected_len}, actual length: {len(uncomp_data)}"

                self.id = self.read_varint()
                self.write(uncomp_data)

    def read_json(self):
        dict_str = self.read_string()

        if dict_str.count("{") > dict_str.count("}"):
            dict_str += "}" * (dict_str.count("{") - dict_str.count("}"))

        try:
            return json.loads(dict_str)
        except json.JSONDecodeError as e:
            self.socket.logger.debug(f"Failed to decode JSON {e}: {dict_str}")
            return {}


# Examples
class S2S_0xFF(S2CPacket):
    """foo:0xFF
    Example packet

    Data:
        - FieldName | FieldType | Notes
    """

    def __init__(self, version: int = 47, **kwargs):
        self.version = version
        self.state = self._info()["state"]
        super().__init__(b"", self.version, self.state)

        self.__data = kwargs
        self.name = self._info()["name"]
        self.id = self._info()["id"]

    @staticmethod
    def _info():
        return {
            "name": "Example Packet",
            "id": 0xFF,
            "state": States.PLAY,
        }

    def __str__(self):
        return f"{self.name}({', '.join([f'{k}={v}' for k, v in self.__data.items()]) if self.__data else ''})"

    def toDict(self):
        return {
            "id": self.id,
            "name": self.name,
            "data": self.__data,
        }

    @staticmethod
    def _dataTypes():
        return {
            "...": "...",
        }

    def toBytes(self):
        b = self.encode_varint(self._info()["id"])

        for k, v in self._dataTypes().items():
            match v:
                case "VarInt":
                    b += self.encode_varint(self.__data[k])
                case "VarLong":
                    b += self.encode_varlong(self.__data[k])
                case "String":
                    b += self.encode_string(self.__data[k])
                case "Unsigned Short":
                    b += self.encode_ushort(self.__data[k])
                case "Short":
                    b += self.encode_short(self.__data[k])
                case "Unsigned Long":
                    b += self.encode_ulong(self.__data[k])
                case "Long":
                    b += self.encode_long(self.__data[k])
                case "UUID":
                    b += self.encode_uuid(self.__data[k])
                case "Boolean":
                    b += self.encode_bool(self.__data[k])
                case "Byte Array":
                    b += self.encode_varint(len(self.__data[k])) + self.__data[k]
                case _:
                    raise ValueError(f"Unknown data type: {v}")

        b = self.encode_varint(len(b)) + b
        return b

    async def send(self, _socket):
        _socket.set_state(self.state)
        await _socket.send(self.toBytes())
