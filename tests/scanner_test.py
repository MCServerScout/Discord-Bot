import logging
import os
import sys

try:
    from pyutils.scanner import Scanner
except ImportError:
    sys.path.append(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    from pyutils.scanner import Scanner


class bcolors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


# Init tests
def test_normal_init():
    logger = logging.getLogger("test_normal_init")
    scanner = Scanner(logger_func=logger, serverLib=None)

    assert scanner.STOP is False
    scanner.stop()
    assert scanner.STOP is True


def test_init_with_max_thread_count():
    logger = logging.getLogger("test_init_with_max_thread_count")
    scanner = Scanner(logger_func=logger, serverLib=None, max_thread_count=999)

    assert scanner.max_threads == 999

    assert scanner.STOP is False
    scanner.stop()
    assert scanner.STOP is True


def test_init_with_max_ping_rate():
    logger = logging.getLogger("test_init_with_max_ping_rate")
    scanner = Scanner(logger_func=logger, serverLib=None, max_ping_rate=999)

    assert scanner.max_pps == 999

    assert scanner.STOP is False
    scanner.stop()
    assert scanner.STOP is True


def test_subnet_fix():
    logger = logging.getLogger("test_subnet_fix")
    scanner = Scanner(logger_func=logger, serverLib=None)

    fixed = scanner.fix_subnet("10.0.0.0")

    assert fixed == "10.0.0.0/24"
    assert isinstance(fixed, str)


def test_large_subnet_fix():
    logger = logging.getLogger("test_large_subnet_fix")
    scanner = Scanner(logger_func=logger, serverLib=None)

    fixed = scanner.fix_subnet("10.0.0.0/8")
    assert hasattr(fixed, "__iter__")

    i, j = 0, 0
    while i < 256:
        while j < 256:
            assert f"10.{i}.{j}.0/24" in fixed
            j += 1
        j = 0
        i += 1
