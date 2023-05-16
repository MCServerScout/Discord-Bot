import datetime
import logging
import os
import subprocess
import time
import traceback

import requests

from privVars import DISCORD_WEBHOOK

logging.basicConfig(
    filename="botHandler.log",
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%m/%d/%Y %I:%M:%S %p",
)


def printAndLog(*args, **kwargs):
    logging.info(*args, **kwargs)
    print(*args, **kwargs)


zipURL = (
    "https://github.com/ServerScout-bust-cosmic-trespass/Discord-Bot/archive/refs/heads/master.zip"
)

runFile = "main.pyw"


def seconds_until_midnight_mountain():
    mountain = datetime.timezone(datetime.timedelta(hours=-7))
    now = datetime.datetime.now(mountain)
    midnight = now.replace(
        hour=0, minute=0, second=0, microsecond=0
    ) + datetime.timedelta(days=1)
    seconds_until_midnight = (midnight - now).total_seconds()
    return seconds_until_midnight


def downloadZip():
    printAndLog("\n{}\nUpdating files".format("-" * 10))
    zipFile = "main.zip"
    if os.path.exists(zipFile):
        os.remove(zipFile)

    gitDir = "Discord-Bot-main"
    if os.path.exists(gitDir):
        # force and recursive remove of dir gitDir
        subprocess.call(["rm", "-rf", gitDir])

    subprocess.call(["mkdir", gitDir])

    subprocess.call(["wget", zipURL, "-O", zipFile])
    subprocess.call(["unzip", zipFile, "-d", gitDir])


def installRequirements():
    printAndLog("\n{}\nInstalling reqs".format("-" * 10))
    subprocess.call(
        [
            "pip3",
            "install",
            "-Ur",
            "Discord-Bot-main/Discord-Bot-master/requirements.txt",
        ]
    )
    subprocess.call(
        ["cp", "privVars.py", "Discord-Bot-main/Discord-Bot-master/privVars.py"]
    )


def run():
    printAndLog("\n{}\nRunning".format("-" * 10))
    exitID = 0
    try:
        # time remaining until midnight
        timeOut = seconds_until_midnight_mountain()
        SCRIPT_DURATION = 60 * 60 * 1  # 1 hour
        printAndLog("Time remaining until midnight: {} sec".format(timeOut))

        if timeOut <= SCRIPT_DURATION:
            timeOut = SCRIPT_DURATION
        else:
            timeOut -= SCRIPT_DURATION
        exitID = subprocess.call(
            ["python3", "Discord-Bot-main/Discord-Bot-master/" + runFile],
            timeout=timeOut,
        )
    except subprocess.TimeoutExpired:
        return "1 - Timeout"
    except Exception:
        printAndLog(traceback.format_exc())
    return str(exitID) + " - Exited"


def main():
    while True:
        downloadZip()
        installRequirements()
        err = run()

        if not err.startswith("0"):
            printAndLog(err)
            try:
                requests.post(DISCORD_WEBHOOK, json={"content": str(err)})
            except Exception:
                printAndLog(traceback.format_exc())
        else:
            printAndLog("Exited with code: {}, restarting".format(err))
        printAndLog("\n{}\nRestarting  after 30 sec".format("-" * 10))
        time.sleep(30)


if __name__ == "__main__":
    main()
