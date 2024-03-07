from ...pycraft2.packet import S2S_0xFF, States, DataTypes


class S2C_0x00(S2S_0xFF):
    """
    Disconnect packet (0x00) sent by the server to the client.

    Data:
        - reason | Json Chat | The reason for the disconnection
    """

    def _info(self):
        return {
            "name": "Disconnect (0x00)",
            "id": 0x00,
            "state": States.LOGIN,
        }

    def _dataTypes(self):
        return {
            "reason": DataTypes.STRING,
        }
