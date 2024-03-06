from ...pycraft2.packet import S2S_0xFF, States, DataTypes


class C2S_0x01(S2S_0xFF):
    """
    Encryption Request (0x01) Packet

    Data:
        - Shared Secret Length | VarInt | The length of the shared secret
        - Shared Secret | Byte Array | The shared secret
        - Public Key Length | VarInt | The length of the public key
        - Public Key | Byte Array | The public key
    """

    def __info(self):
        return {
            "name": "Encryption Request",
            "id": 0x01,
            "state": States.LOGIN,
        }

    def __dataTypes(self):
        return {
            "Shared Secret Length": DataTypes.VARINT,
            "Shared Secret": DataTypes.BYTE_ARRAY,
            "Public Key Length": DataTypes.VARINT,
            "Public Key": DataTypes.BYTE_ARRAY,
        }
