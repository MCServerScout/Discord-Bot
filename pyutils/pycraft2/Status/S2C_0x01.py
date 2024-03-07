from ...pycraft2.packet import S2S_0xFF, States, DataTypes


class S2C_0x01(S2S_0xFF):
    """
    Ping Response (0x01) sent by the server to the client.

    Data:
        - Payload | Long | The client's payload, sent in the ping packet.
    """

    def _info(self):
        return {
            "name": "Ping Response",
            "id": 0x01,
            "state": States.STATUS,
        }

    def _dataTypes(self):
        return {
            "payload": DataTypes.LONG,
        }
