import datetime
import gzip
import io
import logging
import os
import subprocess
import sys
import time
import traceback
import zipfile

import requests

# ---------------------------------------------

# whether to use the dev branch
dev = True
# launch the scanner or the bot (True = scanner, False = bot)
target = [
    # "scanner",
    "bot",
    # "rescanner",
][0]
# autoupdate the handler
autoupdate = True

# ---------------------------------------------

try:
    from privVars import *
except ImportError:
    sys.exit("Config error in privVars.py, please fix before rerunning")

logging.basicConfig(
    filename="botHandler.log",
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%m/%d/%Y %I:%M:%S %p",
)


def print_and_log(*args, **kwargs):
    logging.info(*args, **kwargs)
    print(*args, **kwargs)


def webhook_send(msg: str, webhook: str, file: str | io.BytesIO = None):
    try:
        if file:
            requests.post(
                webhook,
                json={"content": msg},
                files={"file": file},
            )
        else:
            requests.post(
                webhook,
                json={"content": msg},
            )
    except Exception:
        print_and_log(traceback.format_exc())


if not dev:
    zip_url = (
        "https://github.com/MCServerScout/Discord-Bot/archive/refs/heads/master.zip"
    )
else:
    zip_url = (
        "https://github.com/MCServerScout/Discord-Bot/archive/refs/heads/dev-builds.zip"
    )

if target == "scanner":
    run_file = "scanner.pyw"
elif target == "bot":
    run_file = "main.pyw"
elif target == "rescanner":
    run_file = "rescanner.pyw"
else:
    raise Exception("Invalid target")


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
    zip_file = os.path.join(os.getcwd(), zip_file)
    if os.path.exists(zip_file):
        os.remove(zip_file)

    git_dir = "Discord-Bot-main"
    git_dir = os.path.join(os.getcwd(), git_dir)
    if os.path.exists(git_dir):
        # force and recursive remove of dir git_dir
        for root, dirs, files in os.walk(git_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))

        os.rmdir(git_dir)

    os.mkdir(git_dir)

    resp = requests.get(zip_url)
    with open(zip_file, "wb") as f:
        f.write(resp.content)

    with zipfile.ZipFile(zip_file, "r") as zip_ref:
        zip_ref.extractall(git_dir)


def install_requirements():
    # remove all the packages listed in requirements.txt
    print_and_log("\n{}\nUninstalling reqs".format("-" * 10))
    subprocess.call(
        [
            "python3",
            "-m",
            "pip",
            "uninstall",
            "-y",
            "-r",
            "Discord-Bot-main/Discord-Bot-master/requirements.txt"
            if not dev
            else "Discord-Bot-main/Discord-Bot-dev-builds/requirements.txt",
        ]
    )

    print_and_log("\n{}\nInstalling reqs".format("-" * 10))
    subprocess.call(
        [
            "python3",
            "-m",
            "pip",
            "install",
            "-Ur",
            "Discord-Bot-main/Discord-Bot-master/requirements.txt"
            if not dev
            else "Discord-Bot-main/Discord-Bot-dev-builds/requirements.txt",
        ]
    )
    subprocess.call(
        ["cp", "privVars.py", "Discord-Bot-main/Discord-Bot-master/privVars.py"]
        if not dev
        else [
            "cp",
            "privVars.py",
            "Discord-Bot-main/Discord-Bot-dev-builds/privVars.py",
        ]
    )


def run():
    print_and_log("\n{}\nRunning".format("-" * 10))
    exit_id = 0
    try:
        # time remaining until midnight
        time_out = seconds_until_midnight_mountain()
        script_duration = 60 * 20  # 20 min
        if time_out <= script_duration:
            time_out = script_duration
        print_and_log("Time remaining until midnight: {} sec".format(time_out))

        exit_id = subprocess.call(
            ["python3", "Discord-Bot-main/Discord-Bot-master/" + run_file]
            if not dev
            else ["python3", "Discord-Bot-main/Discord-Bot-dev-builds/" + run_file],
            timeout=time_out,
        )
    except subprocess.TimeoutExpired:
        return "1 - Timeout"
    except Exception:
        print_and_log(traceback.format_exc())
    return str(exit_id) + " - Exited"


def update():
    if autoupdate:
        if dev:
            handler_url = "https://raw.githubusercontent.com/MCServerScout/Discord-Bot/dev-builds/botHandler.pyw"
        else:
            handler_url = "https://raw.githubusercontent.com/MCServerScout/Discord-Bot/master/botHandler.pyw"

        contents = requests.get(handler_url).text
        with open(__file__, "r") as f:
            if f.read() != contents:
                print_and_log("Updating botHandler")
                with open(__file__, "w") as n:
                    n.write(contents)
                print_and_log("Restarting")
                # restart
                os.execl(sys.executable, sys.executable, *sys.argv)


def main():
    last_run = 0
    while True:
        try:
            update()  # updates this file

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
                webhook_send(str(err), DISCORD_WEBHOOK)
            else:
                print_and_log("Exited with code: {}, restarting".format(err))

            # upload the log file with the discord webhook
            # compress log.log
            gz_file = io.BytesIO()
            with open("log.log", "rb") as f:
                with gzip.open(gz_file, "wb") as g:
                    g.writelines(f)

            # upload the compressed log file
            webhook_send(
                "Log file",
                DISCORD_WEBHOOK,
                file=gz_file,
            )

            print_and_log("\n{}\nRestarting  after 30 sec".format("-" * 10))
            time.sleep(30)
        except Exception as err:
            print_and_log(traceback.format_exc())
            webhook_send(str(err), DISCORD_WEBHOOK)

            print_and_log("\n{}\nRestarting  after 90 sec".format("-" * 10))
            time.sleep(90)


if __name__ == "__main__":
    main()
