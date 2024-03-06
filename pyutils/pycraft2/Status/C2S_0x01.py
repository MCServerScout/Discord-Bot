import os

from ...pycraft2.packet import S2S_0xFF, States, DataTypes


class C2S_0x01(S2S_0xFF):
    """
    Ping Request (0x01)

    Data:
        - Payload | Long | Any number
    """

    def __info(self):
        return {
            "name": "Ping Request",
            "id": 0x01,
            "state": States.STATUS,
        }

    def __init(self, version: int = 765):
        self.payload = os.urandom(8)
        kwargs = {
            "payload": self.payload,
        }
        super().__init__(version, **kwargs)

    def __dataTypes(self):
        return {
            "payload": DataTypes.LONG,
        }
