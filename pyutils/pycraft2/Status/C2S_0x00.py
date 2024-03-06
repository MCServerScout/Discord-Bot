from ...pycraft2.packet import S2S_0xFF, States


class C2S_0x00(S2S_0xFF):
    """
    Status Request (0x00)

    Data:
        - None
    """

    def __info(self):
        return {
            "name": "Status Request",
            "id": 0x00,
            "state": States.STATUS,
        }

    def __dataTypes(self):
        return {}
