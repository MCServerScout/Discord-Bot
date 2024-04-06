from ...pycraft2.packet import S2S_0xFF, States, DataTypes


class C2S_0x01(S2S_0xFF):
    """
    Encryption Request (0x01) Packet

    Data:
        - shared_secret | Byte Array | The shared secret
        - public_key | Byte Array | The public key
    """

    def _info(self):
        return {
            "name": "Encryption Request",
            "id": 0x01,
            "state": States.LOGIN,
        }

    def _dataTypes(self):
        return {
            "shared_secret": DataTypes.BYTE_ARRAY,
            "public_key": DataTypes.BYTE_ARRAY,
        }
