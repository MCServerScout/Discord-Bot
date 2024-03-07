from ...pycraft2.packet import S2S_0xFF, States


class C2S_0x03(S2S_0xFF):
    """
    Login Acknowledgement (0x03)

    Data:
        - None
    """

    def _info(self):
        return {
            "name": "Login Acknowledgement",
            "id": 0x03,
            "state": States.LOGIN,
        }

    def _dataTypes(self):
        return {}
