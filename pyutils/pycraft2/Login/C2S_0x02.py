from ...pycraft2.packet import S2S_0xFF, States, DataTypes


class C2S_0x02(S2S_0xFF):
    """
    Login Plugin Response (0x02) Packet

    Data:
        - Message ID | VarInt | The ID of the message
        - Successful | Boolean | Whether the response was successful
        - Data | Byte Array | The data of the response (OPTIONAL)
    """

    def __info(self):
        return {
            "name": "Login Plugin Response",
            "id": 0x02,
            "state": States.LOGIN,
        }

    def __dataTypes(self):
        return {
            "Message ID": DataTypes.VARINT,
            "Successful": DataTypes.BOOL,
            "Data": DataTypes.BYTE_ARRAY,
        }
