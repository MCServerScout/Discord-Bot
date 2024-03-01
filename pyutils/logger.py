import asyncio
import inspect
import logging
import os.path
import re
import sys
import time

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
    if any(
        (
            "To sign in, use a web browser to open the page" in msg,
            "email_modal" in msg,
            "heartbeat" in msg.lower(),
            "Sending data to websocket: {" in msg,
            "event.ctx.responses" in msg,
            re.match(
                r"(POST|PATCH)::https://discord.com/api/v\d{1,2}/\S+\s[1-5][0-9]{2}",
                msg,
            )
            is not None,
            msg.startswith("[http_client."),
            re.match(r"^\s*\^\s*$", msg) is not None,
        )
    ) and not any(
        (
            "exception" in msg.lower(),
            "raised" in msg.lower(),
            "error" in msg.lower(),
        )
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
        self.__last_print = None
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

        self.v_stack = ()

    def stack_trace(self, stack):
        """Returns a stack trace"""
        out = (
            stack[1].filename.replace("\\", "/").split("/")[-1].split(".")[0]
            + "."
            + f"{stack[1].function}"
        )
        if any((v in out for v in self.v_stack)):
            # get the full stack trace
            out = "->".join(
                [
                    stack[-i].filename.replace("\\", "/").split("/")[-1].split(".")[0]
                    + "."
                    + f"{stack[-i].function}"
                    for i in range(1, len(stack))
                ]
            )

        return out

    def info(self, message):
        """Same level as print but no console output"""
        message = f"[{self.stack_trace(inspect.stack())}] {message}"
        self.logging.info(message)

    def log(self, *args, **kwargs):
        """Overload for log"""
        self.logging.log(*args, **kwargs)

    def error(self, *message, **kwargs):
        message = " ".join([str(arg) for arg in message])
        message = f"[{self.stack_trace(inspect.stack())}] {message}"
        self.logging.error(message, **kwargs)
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

    def exception(self, message, *_, exception: Exception = None):
        if exception is None:
            message = f"[{self.stack_trace(inspect.stack())}] {message}"
            self.logging.exception(message)
            self.hook(message)
            self.print(message, log=False)
        else:
            # pretty print the exception, function calls, and variables
            stacks = inspect.trace()
            msg = ""
            for stack in stacks:
                msg += f"{os.path.basename(stack.filename)}.{stack.function}({stack.lineno}): {stack.code_context[0].strip()}\n"

                # get the variables
                for var in stack.frame.f_locals:
                    msg += f"    {var}: {stack.frame.f_locals[var]}\n"
                msg += "\n"
            msg += f"{exception.__class__.__name__}: {exception}"
            self.logging.error(msg)

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
        msg = filter_msg(msg)

        if msg is None:
            return

        stack_tr = self.stack_trace(inspect.stack())
        if not stack_tr.lower().startswith("logger."):
            msg = f"[{stack_tr}] {msg}"

        if (
            self.__last_print != msg
        ):  # prevent duplicate messages and spamming the console
            if (
                isinstance(msg, str)
                and self.__last_print is not None
                and not self.__last_print.endswith("\r")
                and (msg.endswith("\r") or ("end" in kwargs and kwargs["end"] != "\n"))
                and msg.endswith("\n")
                and ("end" not in kwargs or kwargs["end"] == "\n")
            ):
                msg = "\n" + msg

            sys.stdout = norm  # output to console
            self.__last_print = str(msg) + (
                "" if "end" not in kwargs else kwargs["end"]
            )
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

    def timer(self, func: callable, *args, **kwargs):
        if inspect.iscoroutinefunction(func):
            self.error("Function is a coroutine")
            return

        start = time.perf_counter()
        res = func(*args, **kwargs)
        end = time.perf_counter()

        tDelta = self.auto_range_time(end - start)
        self.debug(f"Function {func.__name__} took {tDelta}")

        if self.sentry_sdk is not None:
            with sentry_sdk.start_transaction(
                name=f"{func.__name__}", op=f"{func.__name__}"
            ):
                sentry_sdk.set_context("timing", {"duration": tDelta})
        return res

    async def async_timer(self, func: callable, *args, **kwargs):
        if not inspect.iscoroutinefunction(func):
            self.error("Function is not a coroutine")
            return

        start = time.perf_counter()
        res = await func(*args, **kwargs)
        end = time.perf_counter()
        tDelta = self.auto_range_time(end - start)
        self.debug(f"(ASYNC) Function {func.__name__} took {tDelta}")

        if self.sentry_sdk is not None:
            with sentry_sdk.start_transaction(
                name=f"{func.__name__}", op=f"{func.__name__}"
            ):
                sentry_sdk.set_context("timing", {"duration": tDelta})
        return res

    @staticmethod
    def auto_range_time(seconds: float) -> str:
        """
        Returns a time string for a given number of seconds

        Args:
            seconds (float): The number of seconds

        Returns:
            str: The time string
        """

        units = {
            "hr": str(int(seconds // 3600)),
            "min": str(int(seconds // 60)),
            "s": str(int(seconds)),
            "ms": str(int(seconds * 1000)),
            "us": str(int(seconds * 1000000)),
            "ns": str(int(seconds * 1000000000)),
        }

        best = f"{units['ns']} ns"
        units = sorted(units.items(), key=lambda x: len(x[1]))
        for unit in units:
            if unit[1] != "0":
                best = unit
                break

        return f"{best[1]} {best[0]}"
