import asyncio
import logging
import sys

import aiohttp
import unicodedata

norm = sys.stdout


class StreamToLogger:
    """
    Fake file-like stream object that redirects writes to a logger instance.
    """

    def __init__(self, logger, level: int = logging.INFO):
        self.logger = logger
        self.level = level
        self.line_buffer = ""

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.level, line.rstrip())

    def flush(self):
        pass

    def read(self):
        text1, text2 = "", ""
        with open("log.log", "r") as f:
            text1 = f.read()

        try:
            with open("out.log", "r") as f:
                text2 = f.read()
        except FileNotFoundError:
            self.write("out.log does not exist")

        return text1 + "\n" + text2


class EmailFileHandler(logging.FileHandler):
    def emit(self, record):
        if (
                "To sign in, use a web browser to open the page" in record.getMessage()
                or "email_modal" in record.getMessage()
                or "heartbeat" in record.getMessage().lower()
                or "Added " in record.getMessage()
                or "Sending data to websocket: {" in record.getMessage()
                or "event.ctx.responses" in record.getMessage()
        ):
            return
        super().emit(record)


class Logger:
    def __init__(
            self, debug=False, level: int = logging.INFO, discord_webhook: str = None
    ):
        """Initializes the logger class

        Args:
            debug (bool, optional): Show debugging. Defaults to False.
        """
        self.DEBUG = debug
        self.logging = logging
        self.webhook = discord_webhook

        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%d-%b %H:%M:%S",
            handlers=[
                EmailFileHandler("log.log", mode="a",
                                 encoding="utf-8", delay=False),
            ],
        )

        self.log = logging.getLogger("STDOUT")
        self.out = StreamToLogger(self.log, level)
        sys.stdout = self.out
        sys.stderr = self.out

        self.clear()

    def info(self, message):
        """Same level as print but no console output"""
        self.logging.info(message)

    def error(self, *message):
        msg = " ".join([str(arg) for arg in message])
        self.logging.error(msg)
        self.hook(msg)
        self.print(msg, log=False)

    def critical(self, *message):
        message = " ".join([str(arg) for arg in message])
        self.logging.critical(message)
        self.hook(message)
        self.print(message, log=False)

    def debug(self, *args, **kwargs):
        self.logging.debug(" ".join([str(arg) for arg in args]))
        if self.DEBUG:
            self.print(*args, **kwargs, log=False)

    def warning(self, message):
        self.print(message, log=False)
        self.logging.warning(message)

    def war(self, message):
        self.logging.warning(message)

    def exception(self, message):
        self.logging.exception(message)
        self.hook(message)
        self.print(message, log=False)

    def read(self):
        text1, text2 = "", ""
        with open("log.log", "r") as f:
            text1 = f.read()

        try:
            with open("out.log", "r") as f:
                text2 = f.read()[3:]
                text2 = "".join(
                    ch
                    for ch in text2
                    if unicodedata.category(ch)[0] != "C" or ch in "\t" or ch in "\n"
                )
                text2 = text2.replace("\n\n", "\n")
        except FileNotFoundError:
            self.error("out.log does not exist")

        return text1 + "\n" + text2

    def print(self, *args, log=True, **kwargs):
        msg = " ".join([str(arg) for arg in args])
        sys.stdout = norm  # output to console
        print(msg, **kwargs)
        if log:
            sys.stdout = self.out  # output to log.log
            self.info(msg)

    def hook(self, message: str):
        if asyncio.get_event_loop().is_running():
            asyncio.create_task(self.async_hook(message))
        else:
            asyncio.run(self.async_hook(message))

    async def async_hook(self, message: str):
        if self.webhook is not None and self.webhook != "":
            async with aiohttp.ClientSession() as session, session.post(
                    self.webhook,
                    json={
                        "content": message,
                    },
            ) as resp:
                if resp.status != 204:
                    self.error(f"Failed to send message to webhook: {message}")
            self.print(f"Sent message to webhook: {message}")

    def __repr__(self):
        return self.read()

    def __str__(self):
        return self.read()

    @staticmethod
    def clear():
        with open("log.log", "w") as f:
            f.write("")
