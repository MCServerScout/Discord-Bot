from ...pycraft2.packet import S2S_0xFF, States, DataTypes


class S2C_0x00(S2S_0xFF):
    """
    Status Response Packet (0x00)

    Data:
        - JSON Response | String (32767) | See (Server List Ping#Status Response)[https://wiki.vg/Server_List_Ping#Status_Response]; as with all strings, this is prefixed by its length as a VarInt.
    """

    def _info(self):
        return {
            "name": "Status Response",
            "id": 0x00,
            "state": States.STATUS,
        }

    def _dataTypes(self):
        return {
            "json_response": DataTypes.STRING,
        }
