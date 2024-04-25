from ...pycraft2.packet import S2S_0xFF, States, DataTypes


class C2S_0xFE(S2S_0xFF):
    """
    Handshake packet (0xFE) sent by the client to the server.

    Data:
        - len | short | length of the rest of the data, as a short. Compute as 7 + len(hostname), where len(hostname) is the number of bytes in the UTF-16BE encoded hostname.
        - version | int | protocol version, e.g. 4a for the last version (74)
        - hostname | string | hostname the client is connecting to, encoded as a UTF-16BE string
        - port | int | port the client is connecting to, as an int.
    """

    def _info(self):
        return {
            "name": "Handshake (0xFE)",
            "id": 0xFE,
            "state": States.HANDSHAKE,
        }

    def _dataTypes(self):
        return {
            "payload": DataTypes.VARINT,
            "ID": DataTypes.VARINT,
            "msg": DataTypes.UTF16BE,
            "len": DataTypes.SHORT,
            "version": DataTypes.VARINT,
            "hostname": DataTypes.UTF16BE,
            "port": DataTypes.VARINT,
        }

    def toBytes(self):
        return (
            b"\xFE\x01\xFA\x00\x0B" + self.encode_utf16be("MC|PingHost") + b"\x00\x00"
        )
