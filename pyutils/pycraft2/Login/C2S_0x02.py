from ...pycraft2.packet import S2S_0xFF, States, DataTypes


class C2S_0x02(S2S_0xFF):
    """
    Login Plugin Response (0x02) Packet

    Data:
        - message_id | VarInt | The ID of the message
        - successful | Boolean | Whether the response was successful
        - data | Byte Array | The data of the response (OPTIONAL)
    """

    def _info(self):
        return {
            "name": "Login Plugin Response",
            "id": 0x02,
            "state": States.LOGIN,
        }

    def _dataTypes(self):
        return {
            "message_id": DataTypes.VARINT,
            "successful": DataTypes.BOOL,
            "data": DataTypes.BYTE_ARRAY,
        }
