from ...pycraft2.packet import S2S_0xFF, States, DataTypes


class S2C_0x01(S2S_0xFF):
    """
    Encryption request packet

    Data:
        - server_id | String(20) | The server's ID which should be empty
        - public_key | Byte Array | The server's public key
        - verify_token | Byte Array | The verify token
    """

    def _info(self):
        return {
            "name": "Encryption Request (0x01)",
            "id": 0x01,
            "state": States.LOGIN,
        }

    def _dataTypes(self):
        return {
            "server_id": DataTypes.STRING,
            "public_key": DataTypes.BYTE_ARRAY,
            "verify_token": DataTypes.BYTE_ARRAY,
        }
