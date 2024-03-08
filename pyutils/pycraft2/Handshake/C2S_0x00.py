from ...pycraft2.packet import S2S_0xFF, States, DataTypes


class C2S_0x00(S2S_0xFF):
    """
    Handshake packet (0x00) sent by the client to the server.

    Data:
        - Protocol Version | VarInt | See protocol version numbers (currently 765 in Minecraft 1.20.4).
        - Server Address | String (255) | Hostname or IP, e.g., localhost or 127.0.0.1, that was used to connect. The Notchian server does not use this information. Note that SRV records are a simple redirect, e.g. if _minecraft._tcp.example.com points to mc.example.org, users connecting to example.com will provide example.org as server address in addition to connecting to it.
        - Server Port | Unsigned Short | Default is 25565. The Notchian server does not use this information.
        - Next State | VarInt Enum | 1 for Status, 2 for Login.
    """

    def _info(self):
        return {
            "name": "Handshake (0x00)",
            "id": 0x00,
            "state": States.HANDSHAKE,
        }

    def _dataTypes(self):
        return {
            "protocol_version": DataTypes.VARINT,
            "server_address": DataTypes.STRING,
            "server_port": DataTypes.USHORT,
            "next_state": DataTypes.VARINT,
        }
