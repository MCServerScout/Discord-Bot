from ...pycraft2.packet import S2S_0xFF, States, DataTypes


class C2S_0x01(S2S_0xFF):
    """
    Ping Request (0x01)

    Data:
        - Payload | Long | Any number
    """

    def _info(self):
        return {
            "name": "Ping Request",
            "id": 0x01,
            "state": States.STATUS,
        }

    def _dataTypes(self):
        return {
            "payload": DataTypes.LONG,
        }
