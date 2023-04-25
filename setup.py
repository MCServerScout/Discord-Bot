"""Install requirements.txt and create privVars.py"""

import asyncio
import sys


async def install_requirements():
    # check that python is 3.10+
    if not (3, 10) <= sys.version_info:
        print("Python 3.10+ is required")
        sys.exit(1)

    proc = await asyncio.create_subprocess_shell(
        "pip install -r requirements.txt",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    print(f"[stdout]\n{stdout.decode()}")
    print(f"[stderr]\n{stderr.decode()}")


async def create_privVars():
    text = """# Path: privVars.py
DISCORD_TOKEN = ""
DISCORD_WEBHOOK = ""
MONGO_URL = ""
"""
    with open("privVars.py", "w") as f:
        f.write(text)


async def main():
    await install_requirements()
    await create_privVars()


if __name__ == "__main__":
    asyncio.run(main())
