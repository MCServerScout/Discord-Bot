import datetime
import re
import traceback

import unicodedata


class Text:
    def __init__(self, logger):
        """Initializes the text class

        Args:
            logger (Logger): The logger class
        """
        self.logger = logger

    @staticmethod
    def c_filter(text: str, trim: bool = True) -> str:
        """Removes all color bits from a string

        Args:
            text [str]: The string to remove color bits from
            trim [bool]: Whether to trim the string or not

        Returns:
            [str]: The string without color bits
        """
        # remove all color bits
        text = re.sub(r"§[0-9a-fk-or]*", "", text).replace("|", "")
        if trim:
            text = text.strip()

        text = text.replace("@", "@ ")  # fix @ mentions

        # escape all unicode chars
        text = "".join(
            char.encode("unicode_escape").decode("utf-8")
            if unicodedata.category(char) in ("Cc", "Cf", "Cn", "Co", "Cs")
            else char
            for char in text
        )

        return text

    def ansi_color(self, text: str) -> str:
        """Changes color tags to those that work with markdown

        Args:
            text (str): text to change

        Returns:
            str: text with markdown color tags
        """

        # color char prefix \u001b[{color}m
        # color #s
        # 30: Gray   <- §7
        # 31: Red    <- §c
        # 32: Green  <- §a
        # 33: Yellow <- §e
        # 34: Blue   <- §9
        # 35: Pink   <- §d
        # 36: Cyan   <- §b
        # 37: White  <- §f

        # use the ansi color codes
        text = self.color_ansi(text)

        text = "```ansi\n" + text + "\n```"

        # loop through and escape all unicode chars that are not \u001b or \n
        text = "".join(
            [
                char
                if char in ("\u001b", "\n")
                else unicodedata.normalize("NFKD", char)
                for char in text
            ]
        )

        return text

    @staticmethod
    def color_ansi(text: str) -> str:
        """Changes color tags to those that work with ansi code blocks

        Args:
            text (str): text to change

        Returns:
            str: text with ansi color tags
        """
        # 30: Gray   <- §7
        # 31: Red    <- §c
        # 32: Green  <- §a
        # 33: Yellow <- §e
        # 34: Blue   <- §9
        # 35: Pink   <- §d
        # 36: Cyan   <- §b
        # 37: White  <- §f
        color_char = ""  # \u001b
        ansi = {
            "§0": color_char + "[30m",
            "§1": color_char + "[34m",
            "§2": color_char + "[32m",
            "§3": color_char + "[36m",
            "§4": color_char + "[31m",
            "§5": color_char + "[35m",
            "§6": color_char + "[33m",
            "§7": color_char + "[30m",
            "§9": color_char + "[34m",
            "§a": color_char + "[32m",
            "§b": color_char + "[36m",
            "§c": color_char + "[31m",
            "§d": color_char + "[35m",
            "§e": color_char + "[33m",
            "§f": color_char + "[37m",
            "§l": "",  # text styles
            "§k": "",
            "§m": "",
            "§n": "",
            "§o": "",
            "§r": "",
        }

        for color in ansi.items():
            text = text.replace(color[0], color[1])

        # remove remaining color codes
        text = re.sub(r"§[0-9a-fk-or]*", "", text)

        return text

    @staticmethod
    def color_mine(color: str) -> str:
        # given a color like 'yellow' return the color code like '§e'
        color = color.lower()

        if color == "gray":
            return "§7"
        elif color == "red":
            return "§c"
        elif color == "green":
            return "§a"
        elif color == "yellow":
            return "§e"
        elif color in ("blue", "aqua"):
            return "§9"
        elif color == "pink":
            return "§d"
        elif color == "cyan":
            return "§b"
        elif color == "white":
            return "§f"
        else:
            return ""

    @staticmethod
    def time_now():
        """Timestamp in a format usable by discord timestamps"""
        # return local time
        return datetime.datetime.now(
            datetime.timezone(
                datetime.timedelta(
                    hours=-6
                )  # no clue why this is needed, but it works now?
            )
        ).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def time_ago(date: datetime.datetime) -> str:
        """Returns a string of how long ago a date was

        Args:
            date (datetime.datetime): The date to compare

        Returns:
            str: The string of how long ago the date was (now if less than 30 seconds ago)
        """

        diff = datetime.datetime.utcnow() - date

        if datetime.timedelta(seconds=30) > diff:
            return "now"

        years = diff.days // 365
        months = diff.days // 30
        days = diff.days % 30
        hours = diff.seconds // 3600
        minutes = (diff.seconds % 3600) // 60
        seconds = (diff.seconds % 3600) % 60

        out = ""

        if months:
            out += f"{months} month{'s' if months > 1 else ''}, "
        if days:
            out += f"{days} day{'s' if days > 1 else ''}, "
        if hours:
            out += f"{hours} hour{'s' if hours > 1 else ''}, "
        if minutes:
            out += f"{minutes} minute{'s' if minutes > 1 else ''}, "
        if seconds:
            out += f"{seconds} second{'s' if seconds > 1 else ''}"
        if years:
            out = "Long long ago..."

        return out

    def motd_parse(self, motd: dict) -> dict:
        """Parses a motd dict to remove color codes

        Args:
            motd (dict): The motd dict

        Returns:
            dict: The parsed motd dict
        """
        try:
            if not motd:
                return {
                    "text": "...",
                }

            def parse_extra(extra):
                _text = ""
                last_color = ""
                for ext in extra:
                    if "extra" in ext:
                        _text += parse_extra(ext["extra"])
                    else:
                        if "color" in ext:
                            if ext["color"] != last_color:
                                last_color = ext["color"]
                                _text += self.color_mine(color=ext["color"])
                            _text += ext["text"]
                        elif "text" in ext:
                            _text += ext["text"]
                        elif isinstance(ext, str):
                            _text += ext
                return _text

            text = ""
            if "text" in motd:
                text += motd["text"]

            if "extra" in motd:
                text += parse_extra(motd["extra"])

            if type(motd) is str:
                text = motd

            if text == "":
                text = "Unknown"

            # remove bad chars
            chars = ["`", "@"]
            for char in chars:
                text = text.replace(char, "")

            # replace "digit.digit.digit.digit" with "x.x.x.x"
            text = re.sub(r"\d+\.\d+\.\d+\.\d+", "x.x.x.x", text)

            if text.startswith("motd="):
                text = text[5:]

            return {
                "text": text,
            }
        except TypeError:
            self.logger.error(f"Failed to parse motd: TypeError (motd: {motd})")
            self.logger.error(traceback.format_exc())
            return {
                "text": "Unknown",
            }

    @staticmethod
    def percent_bar(
        iteration: int,
        total: int,
        prefix: str = "",
        suffix: str = "",
        length: int = 15,
        fill: str = "█",
    ):
        """
        Call in a loop to create terminal progress bar

        Args:
            iteration (int): current iteration
            total (int): total iterations
            prefix (str): prefix string
            suffix (str): suffix string
            length (int): character length of bar
            fill (str): bar fill character
        """
        if total == 0:
            return f"\r{prefix} |{fill * length}| {100}% {suffix}"

        decimals = 2
        percent = ("{0:." + str(decimals) + "f}").format(
            100 * (iteration / float(total))
        )
        filledLength = int(length * iteration // total)
        bar = fill * filledLength + "-" * (length - filledLength)
        return f"\r{prefix} |{bar}| {percent}% {suffix}"

    def update_dict(self, dict1, dict2):
        """
        dict2 -> dict1
        Update dict1 with dict2, recursively.
        """
        dic3 = dict1.copy()
        for key, value in dict2.items():
            if key in dict1:
                if type(value) is dict and type(dict1[key]) is dict:
                    dic3[key] = self.update_dict(dict1[key], value)
                elif (
                    hasattr(value, "__iter__")
                    and type(value) is not str
                    and type(dic3[key]) is not str
                ):
                    if dic3[key] == value:
                        continue
                    dic3[key].extend(value)
                    # remove duplicates
                    dic3[key] = list(set(dic3[key]))
                else:
                    dic3[key] = value
            else:
                dic3[key] = value

        return dic3

    @staticmethod
    def parse_range(rng: str) -> list[tuple, tuple]:
        """
        Parses a range string into a tuple of ints

        ex `(1, 2)` -> ((0, 1), (0, 2))
           `(1, 3]` -> ((0, 1), (1, 3))
           `(1, )` -> ((0, 1), ())
           `[ , 3)` -> ((), (0, 3))

        Returns:
            tuple: the first tuple group is the lower bound, the second is the upper bound
              The tuple groups have two ints, one for is equal (1) or not (0), and the other is the number
        """
        out = [(), ()]
        if rng.startswith(("(", "[")) and rng.endswith((")", "]")) and "," in rng:
            rng = rng.replace(" ", "").split(",")

            if len(rng) == 1:
                # one sided limit
                if rng[0].startswith(("(", "[")):
                    out[0] = (
                        int(rng[0].startswith("(")),
                        int(rng[0][1:]),
                    )
                else:
                    out[1] = (
                        int(rng[0].endswith(")")),
                        int(rng[0][1:-1]),
                    )
            elif len(rng) == 2:
                # two-sided limit
                out[0] = (
                    int(rng[0].startswith("(")),
                    int(rng[0][1:]),
                )

                out[1] = (
                    int(rng[1].endswith(")")),
                    int(rng[1][:-1]),
                )
            elif len(rng) > 0:
                # attempt to parse the range

                if out[0][0] not in ("(", "[") or out[-1][-1] not in (")", "]"):
                    raise ValueError("Invalid range")

                out[0] = (
                    int(rng[0].startswith("(")),
                    int(rng[0][1:]),
                )

                out[1] = (
                    int(rng[-1].endswith(")")),
                    int(rng[-1][:-1]),
                )
            else:
                raise ValueError("Invalid range")

        return out
