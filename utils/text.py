import datetime
import json
import re

import unicodedata
from bson import ObjectId


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
            char
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
    def time_now():
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
            out += f"Long long ago..."

        return out

    @staticmethod
    def protocol_str(protocol: int) -> str:
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

    def motd_parse(self, motd: dict) -> dict:
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
                    text += self.color_mine(color=ext["color"]) + ext["text"]
                else:
                    text += ext["text"]

        if "text" in motd:
            text += motd["text"]

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

        return {
            "text": text,
        }

    @staticmethod
    def convert_string_to_json(string):
        # prefixes
        string = (
            string.replace("'", '"')
            .replace("ObjectId(", '{"$oid": ')
            .replace(")", "}")
            .replace("True", "true")
            .replace("False", "false")
            .replace("None", "null")
        )

        def convert_to_objectid(data):
            if isinstance(data, dict):
                for key, value in data.items():
                    if key == "$oid":
                        return ObjectId(value)
                    else:
                        data[key] = convert_to_objectid(value)
            elif isinstance(data, list):
                for i in range(len(data)):
                    data[i] = convert_to_objectid(data[i])
            return data

        json_data = json.loads(string)
        return convert_to_objectid(json_data)

    @staticmethod
    def convert_json_to_string(json_data):
        out = (
            str(json_data)
            .replace("'", '"')
            .replace("ObjectId(", '{"$oid": ')
            .replace(")", "}")
            .replace("True", "true")
            .replace("False", "false")
            .replace("None", "null")
        )
        return out
