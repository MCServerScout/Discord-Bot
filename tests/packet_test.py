import os.path
import traceback

curDir = os.getcwd()
# move up one directory
curDir = os.path.dirname(curDir)
packetDir = os.path.join(curDir, "pyutils", "pycraft2")


def get_files(directory, add_cwd=True):
    return os.listdir(os.path.join(curDir, directory) if add_cwd else directory)


def check_foo_packets(name: str):
    directory = os.path.join(packetDir, name)
    files = get_files(directory)

    for file in files:
        file = os.path.join(directory, file)

        if file.endswith("__init__.py") or file.endswith("__pycache__"):
            continue

        with open(file, "r") as f:
            content = f.read()
            expected_name = file.split(".")[0]
            expected_name = os.path.split(expected_name)[-1]
            expected_id = expected_name[-4:]

            assert (
                f"class {expected_name}(S2S_0xFF):" in content
            ), f"Expected class {expected_name} to be in {file}"

            assert (
                f'"id": {expected_id},' in content
            ), f"Expected id to be {expected_id} in {file}"

            assert (
                "def _info(self):" in content
            ), f"Expected _info method to be in {file}"

            assert (
                "def _dataTypes(self):" in content
            ), f"Expected _dataTypes method to be in {file}"

    return 1


def test_Status_packets():
    try:
        assert check_foo_packets("Status")
    except AssertionError as err:
        print("Status packets failed:", traceback.format_exc())
        raise err


def test_Login_packets():
    try:
        assert check_foo_packets("Login")
    except AssertionError as err:
        print("Login packets failed:", traceback.format_exc())
        raise err


def test_Handshake_packets():
    try:
        assert check_foo_packets("Handshake")
    except AssertionError as err:
        print("Handshake packets failed:", traceback.format_exc())
        raise err


def test_Play_packets():
    try:
        assert check_foo_packets("Play")
    except AssertionError as err:
        print("Play packets failed:", traceback.format_exc())
        raise err
