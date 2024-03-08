from ...pycraft2.packet import S2S_0xFF, States, DataTypes


class S2C_0x04(S2S_0xFF):
    """
    Login Plugin Request (0x04) Packet

    Data:
        - Message ID | VarInt | The ID of the message
        - Channel | String (Identifier) | The name of the channel
        - Data | Byte Array | The data of the message
    """

    def _info(self):
        return {
            "name": "Login Plugin Request",
            "id": 0x04,
            "state": States.LOGIN,
        }

    def _dataTypes(self):
        return {
            "message_id": DataTypes.VARINT,
            "channel": DataTypes.STRING,
            "data": DataTypes.BYTE_ARRAY,
        }
