from ...pycraft2.packet import S2S_0xFF, States, DataTypes


class S2C_0x02(S2S_0xFF):
    """
    Login Success (0x02)

    Data:
        - uuid | 128-bit int | The player's UUID
        - username | String(16) | The player's username
        - ...
    """

    def _info(self):
        return {
            "name": "Login Success",
            "id": 0x02,
            "state": States.LOGIN,
        }

    def _dataTypes(self):
        return {
            "uuid": DataTypes.UUID,
            "username": DataTypes.STRING,
        }
