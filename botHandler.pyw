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


def print_and_log(*args, **kwargs):
    logging.info(*args, **kwargs)
    print(*args, **kwargs)


zip_url = (
    "https://github.com/ServerScout-bust-cosmic-trespass/Discord-Bot/archive/refs/heads/master.zip"
)

run_file = "main.pyw"


def seconds_until_midnight_mountain():
    mountain = datetime.timezone(datetime.timedelta(hours=-7))
    now = datetime.datetime.now(mountain)
    midnight = now.replace(
        hour=0, minute=0, second=0, microsecond=0
    ) + datetime.timedelta(days=1)
    seconds_until_midnight = (midnight - now).total_seconds()
    return seconds_until_midnight


def download_zip():
    print_and_log("\n{}\nUpdating files".format("-" * 10))
    zip_file = "main.zip"
    if os.path.exists(zip_file):
        os.remove(zip_file)

    git_dir = "Discord-Bot-main"
    if os.path.exists(git_dir):
        # force and recursive remove of dir git_dir
        subprocess.call(["rm", "-rf", git_dir])

    subprocess.call(["mkdir", git_dir])

    subprocess.call(["wget", zip_url, "-O", zip_file])
    subprocess.call(["unzip", zip_file, "-d", git_dir])


def install_requirements():
    print_and_log("\n{}\nInstalling reqs".format("-" * 10))
    subprocess.call(
        [
            "python3",
            "-m",
            "pip",
            "install",
            "-Ur",
            "Discord-Bot-main/Discord-Bot-master/requirements.txt",
        ]
    )
    subprocess.call(
        ["cp", "privVars.py", "Discord-Bot-main/Discord-Bot-master/privVars.py"]
    )


def run():
    print_and_log("\n{}\nRunning".format("-" * 10))
    exit_id = 0
    try:
        # time remaining until midnight
        time_out = seconds_until_midnight_mountain()
        script_duration = 60 * 60 * 24  # 24 hours
        print_and_log("Time remaining until midnight: {} sec".format(time_out))

        if time_out <= script_duration:
            time_out = script_duration
        else:
            time_out -= script_duration
        exit_id = subprocess.call(
            ["python3", "Discord-Bot-main/Discord-Bot-master/" + run_file],
            timeout=time_out,
        )
    except subprocess.TimeoutExpired:
        return "1 - Timeout"
    except Exception:
        print_and_log(traceback.format_exc())
    return str(exit_id) + " - Exited"


def main():
    last_run = 0
    while True:
        download_zip()
        install_requirements()

        if time.time() - last_run < 60 * 5:  # 5 min
            print_and_log("Restarted too soon, waiting 15 min")
            time.sleep(60 * 15)
        elif time.time() - last_run < 60 * 15:  # 15 min
            print_and_log("Someone royally messed up, waiting 60 min")
            time.sleep(60 * 60)
        last_run = time.time()

        err = run()

        if not err.startswith("0"):
            print_and_log(err)
            try:
                requests.post(DISCORD_WEBHOOK, json={"content": str(err)})
            except Exception:
                print_and_log(traceback.format_exc())
        else:
            print_and_log("Exited with code: {}, restarting".format(err))
        print_and_log("\n{}\nRestarting  after 30 sec".format("-" * 10))
        time.sleep(30)


if __name__ == "__main__":
    main()
