import asyncio
import inspect
import logging
import re
import sys

import aiohttp
import sentry_sdk
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

    def flush(self):  # skipcq: PTC-W0049
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


def filter_msg(msg: str) -> str | None:
    if (
        "To sign in, use a web browser to open the page" in msg
        or "email_modal" in msg
        or "heartbeat" in msg.lower()
        or "Sending data to websocket: {" in msg
        or "event.ctx.responses" in msg
        or re.match(
            r"(POST|PATCH)::https://discord.com/api/v\d{1,2}/\S+\s[1-5][0-9]{2}",
            msg,
        )
        is not None
        or msg.startswith("[http_client.")
    ):
        return
    return msg


class EmailFileHandler(logging.FileHandler):
    def emit(self, record):
        if filter_msg(record.getMessage()) is None:
            return
        super().emit(record)


class Logger:
    def __init__(
        self,
        debug=False,
        level: int = logging.INFO,
        discord_webhook: str = None,
        sentry_dsn: str = None,
        ssdk: sentry_sdk = None,
    ):
        """Initializes the logger class

        Args:
            debug (bool, optional): Show debugging. Defaults to False.
        """
        self.DEBUG = debug
        self.logging = logging
        self.webhook = discord_webhook

        logging.basicConfig(
            level=level if not self.DEBUG else logging.DEBUG,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%d-%b %H:%M:%S",
            handlers=[
                EmailFileHandler("log.log", mode="a", encoding="utf-8", delay=False),
            ],
        )

        self.stdout = logging.getLogger("STDOUT")
        self.out = StreamToLogger(self.stdout, level)
        sys.stdout = self.out
        sys.stderr = self.out

        self.clear()

        if self.DEBUG:
            self.logging.info("Debugging enabled")

        if sentry_dsn is not None and ssdk is None:
            sentry_sdk.init(
                dsn=sentry_dsn,
                traces_sample_rate=1.0,
                profiles_sample_rate=0.6,
            )
            self.sentry_sdk = sentry_sdk
        elif ssdk is not None:
            self.sentry_sdk = ssdk
        else:
            self.sentry_sdk = None

    @staticmethod
    def stack_trace(stack):
        """Returns a stack trace"""
        return (
            stack[1].filename.replace("\\", "/").split("/")[-1].split(".")[0]
            + "."
            + f"{stack[1].function}"
        )

    def info(self, message):
        """Same level as print but no console output"""
        message = f"[{self.stack_trace(inspect.stack())}] {message}"
        self.logging.info(message)

    def log(self, *args, **kwargs):
        """Overload for log"""
        self.logging.log(*args, **kwargs)

    def error(self, *message, **_):
        message = " ".join([str(arg) for arg in message])
        message = f"[{self.stack_trace(inspect.stack())}] {message}"
        self.logging.error(message)
        self.print(message, log=False)

    def critical(self, *message):
        message = " ".join([str(arg) for arg in message])
        message = f"[{self.stack_trace(inspect.stack())}] {message}"
        self.logging.critical(message)
        self.hook(message)
        self.print(message, log=False)

    def debug(self, *args, **kwargs):
        msg = " ".join([str(arg) for arg in args])
        msg = f"[{self.stack_trace(inspect.stack())}] {msg}"
        self.logging.debug(msg)
        if self.DEBUG:
            self.print(*args, **kwargs, log=False)

    def warning(self, message):
        message = f"[{self.stack_trace(inspect.stack())}] {message}"
        self.print(message, log=False)
        self.logging.warning(message)

    def war(self, message):
        message = f"[{self.stack_trace(inspect.stack())}] {message}"
        self.logging.warning(message)

    def exception(self, message):
        message = f"[{self.stack_trace(inspect.stack())}] {message}"
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
        stack_tr = self.stack_trace(inspect.stack())
        if not stack_tr.lower().startswith("logger."):
            msg = f"[{stack_tr}] {msg}"
        sys.stdout = norm  # output to console
        print(msg, **kwargs)
        sys.stdout = self.out  # output to log.log
        if log:
            self.logging.info(msg)

    def hook(self, message: str):
        try:
            asyncio.ensure_future(self.async_hook(message))
        except RuntimeError:
            # create a new loop and run the coroutine
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.async_hook(message))

    async def async_hook(self, message: str):
        message = filter_msg(message)
        if self.webhook is not None and self.webhook != "" and message is not None:
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
