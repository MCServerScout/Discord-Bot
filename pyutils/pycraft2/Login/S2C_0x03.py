from ...pycraft2.packet import S2S_0xFF, States, DataTypes


class S2C_0x03(S2S_0xFF):
    """
    Set Compression (0x03) Packet

    Data:
        - Threshold | VarInt | The maximum size of a packet before it will be compressed
    """

    def __info(self):
        return {
            "name": "Set Compression",
            "id": 0x03,
            "state": States.LOGIN,
        }

    def __dataTypes(self):
        return {"Threshold": DataTypes.VARINT}
