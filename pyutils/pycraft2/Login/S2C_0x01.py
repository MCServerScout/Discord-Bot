from ...pycraft2.packet import S2S_0xFF, States, DataTypes


class S2C_0x01(S2S_0xFF):
    """
    Encryption request packet

    Data:
        - Server ID | String(20) | The server's ID which should be empty
        - Public Key Length | VarInt | The length of the public key
        - Public Key | Byte Array | The server's public key
        - Verify Token Length | VarInt | The length of the verify token
        - Verify Token | Byte Array | The verify token
    """

    def __info(self):
        return {
            "name": "Encryption Request (0x01)",
            "id": 0x01,
            "state": States.LOGIN,
        }

    def __dataTypes(self):
        return {
            "Server ID": DataTypes.STRING,
            "Public Key Length": DataTypes.VARINT,
            "Public Key": DataTypes.BYTE_ARRAY,
            "Verify Token Length": DataTypes.VARINT,
            "Verify Token": DataTypes.BYTE_ARRAY,
        }
