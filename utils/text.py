import datetime
import re

import unicodedata


class Text:
    def __init__(self, logger):
        """Initializes the text class

        Args:
            logger (Logger): The logger class
        """
        self.logger = logger

    @staticmethod
    def cFilter(text: str, trim: bool = True) -> str:
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
            char
            if unicodedata.category(char) in ("Cc", "Cf", "Cn", "Co", "Cs")
            else char
            for char in text
        )

        return text

    def ansiColor(self, text: str) -> str:
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
        text = self.colorAnsi(text)

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
    def colorAnsi(text: str) -> str:
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
        colorChar = ""  # \u001b
        ansi = {
            "§0": colorChar + "[30m",
            "§1": colorChar + "[34m",
            "§2": colorChar + "[32m",
            "§3": colorChar + "[36m",
            "§4": colorChar + "[31m",
            "§5": colorChar + "[35m",
            "§6": colorChar + "[33m",
            "§7": colorChar + "[30m",
            "§9": colorChar + "[34m",
            "§a": colorChar + "[32m",
            "§b": colorChar + "[36m",
            "§c": colorChar + "[31m",
            "§d": colorChar + "[35m",
            "§e": colorChar + "[33m",
            "§f": colorChar + "[37m",
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
    def colorMine(color: str) -> str:
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
        elif color == "blue":
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
    def timeNow():
        # return local time
        return datetime.datetime.now(
            datetime.timezone(
                datetime.timedelta(
                    hours=-6
                )  # no clue why this is needed, but it works now?
            )
        ).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def timeAgo(date: datetime.datetime) -> str:
        """Returns a string of how long ago a date was

        Args:
            date (datetime.datetime): The date to compare

        Returns:
            str: The string of how long ago the date was (now if less than 30 seconds ago)
        """

        diff = datetime.datetime.utcnow() - date

        if datetime.timedelta(seconds=30) > diff:
            return "now"

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

        return out

    @staticmethod
    def protocolStr(protocol: int) -> str:
        """Returns a string of the protocol version

        Args:
            protocol (int): The protocol version

        Returns:
            str: The string of the protocol version
        """
        out = "1."
        match protocol:
            case 3:
                out += "7.1"
            case 4:
                out += "7.5"
            case 5:
                out += "7.10"
            case 47:
                out += "8.9"
            case 107:
                out += "9"
            case 108:
                out += "9.1"
            case 109:
                out += "9.2"
            case 110:
                out += "9.4"
            case 210:
                out += "10.2"
            case 315:
                out += "11"
            case 316:
                out += "11.2"
            case 335:
                out += "12"
            case 338:
                out += "12.1"
            case 340:
                out += "12.2"
            case 393:
                out += "13"
            case 401:
                out += "13.1"
            case 404:
                out += "13.2"
            case 477:
                out += "14"
            case 480:
                out += "14.1"
            case 485:
                out += "14.2"
            case 490:
                out += "14.3"
            case 498:
                out += "14.4"
            case 573:
                out += "15"
            case 575:
                out += "15.1"
            case 578:
                out += "15.2"
            case 735:
                out += "16"
            case 736:
                out += "16.1"
            case 751:
                out += "16.2"
            case 753:
                out += "16.3"
            case 754:
                out += "16.5"
            case 755:
                out += "17"
            case 756:
                out += "17.1"
            case 757:
                out += "18.1"
            case 758:
                out += "18.2"
            case 759:
                out += "19"
            case 760:
                out += "19.2"
            case 761:
                out += "19.3"
            case 762:
                out += "19.4"

        return out

    def motdParse(self, motd: dict) -> dict:
        """Parses a motd dict to remove color codes

        Args:
            motd (dict): The motd dict

        Returns:
            dict: The parsed motd dict
        """
        text = ""
        if "extra" in motd:
            for ext in motd["extra"]:
                if "color" in ext:
                    text += self.colorMine(color=ext["color"]) + ext["text"]
                else:
                    text += ext["text"]

        if "text" in motd:
            text += motd["text"]

        if type(motd) is str:
            text = motd

        if text == "":
            text = "Unknown"

        return {
            "text": text,
        }
