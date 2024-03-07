from ...pycraft2.packet import S2S_0xFF, States, DataTypes


class C2S_0x00(S2S_0xFF):
    """
    Login Start (0x00)

    Data:
        - Name | String(16) | The player's username
        - UUID | 128 bit int | The player's UUID
    """

    def _info(self):
        return {
            "name": "Login Start",
            "id": 0x00,
            "state": States.LOGIN,
        }

    def _dataTypes(self):
        return {"Name": DataTypes.STRING, "UUID": DataTypes.UUID}
