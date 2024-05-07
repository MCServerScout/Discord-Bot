import asyncio
import http.server
import json
import os
import secrets
import socket
import traceback
import urllib.parse
from base64 import urlsafe_b64encode
from hashlib import sha256
from http.server import BaseHTTPRequestHandler
from threading import Thread
from typing import Tuple, Literal, cast

import aiohttp
import requests
import sentry_sdk

from .logger import Logger
from .player import Player
from .pycraft2.connector import MCSocket
from .server import Server
from .text import Text

activationCode = None


class Minecraft:
    """
    Steps:
    1. Request authorization url
    2. Start the http server
    3. Send the auth url to the user
    4. Wait for the user to log in
    5. Get call the join function for the desired server
    """

    activationCode = None

    class ServerType:
        def __init__(self, ip: str, version: int, status: str):
            self.ip = ip
            self.version = version
            self.status = status

        def __str__(self):
            return f"ServerType(ip={self.ip}, version={self.version}, status={self.status})"

        def __repr__(self):
            return self.__str__()

    class RequestHandler(BaseHTTPRequestHandler):
        """Basic request handler for getting the code from microsoft.

        Args:
            BaseHTTPRequestHandler : the base request handler
        """

        def do_GET(self):
            """Handles the get request from microsoft.

            Args:
                self (_type_): the request handler
            """
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(bytes("Thanks for logging in!", "utf-8"))
            if "code" in self.path:
                global activationCode
                activationCode = self.path.split("=")[1][:-6]
                self.server.shutdown()

    def __init__(self, logger: Logger, server: Server, player: Player, text: "Text"):
        self.key = os.urandom(16)
        self.logger = logger
        self.server = server
        self.player = player
        self.text = text

    async def join(
        self,
        ip: str,
        port: int,
        player_username: str,
        mine_token: str,
        version: int = 47,
        # session_attempts: int = 5,
    ) -> ServerType:
        """
        Joins a minecraft server.

        :param ip: The ip of the server
        :param port: The port of the server
        :param player_username: The username of the player
        :param mine_token: The minecraft token
        :param version: The protocol version of the server
        # :param session_attempts: The number of times to attempt to authenticate the account

        :return: The server type
        """
        try:
            # ----
            # Pre-join checks
            # ----

            # get info on the server
            sock = await MCSocket(ip, port)

            await sock.handshake_status(version)
            server = await sock.status_request()
            version = server["version"]["protocol"]

            # get the player's uuid
            _uuid = await self.player.async_get_uuid(player_username)
            # set the compression threshold off (<= 0)
            comp_thresh = 0

            # needed if a username is invalid
            if not _uuid:
                self.logger.print("Player UUID not found")
                return self.ServerType(ip, version, "bad uuid")

            _duuid = _uuid.replace("-", "")
            _uuid = (
                f"{_uuid[:8]}-{_uuid[8:12]}-{_uuid[12:16]}-{_uuid[16:20]}-{_uuid[20:]}"
            )
            # check if the account owns the game
            async with aiohttp.ClientSession() as httpSession:
                url = "https://api.minecraftservices.com/entitlements/mcstore"
                async with httpSession.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {mine_token}",
                        "Content-Type": "application/json",
                    },
                ) as res:
                    if res.status == 200:
                        items = (await res.json()).get("items", [])

                        # make sure the account owns the game
                        if len(items) == 0:
                            self.logger.print("Account does not own the game")
                            return self.ServerType(ip, version, "NO_GAME")
                    else:
                        self.logger.print("Failed to check if account owns the game")
                        self.logger.error(res.text)
                        return self.ServerType(ip, version, "BAD_TOKEN")

            await sock.handshake_login(version)
            self.logger.debug("Sent handshake packet")

            try:
                result = await sock.login(mc_token=mine_token, uuid=_uuid)
            except NotImplementedError:
                self.logger.error("Failed to login form plugin request")
                return self.ServerType(ip, version, "MODDED")
            else:
                return self.ServerType(ip, version, "ONLINE")
        except Exception in (
            TimeoutError,
            ConnectionError,
            AssertionError,
        ) as err:
            self.logger.error(traceback.format_exc())
            return self.ServerType(ip, version, f"OFFLINE:{type(err).__name__}")
        except TypeError as err:
            self.logger.exception("TypeError", exception=err)
            return self.ServerType(ip, version, "OFFLINE:TypeError")
        except Exception as err:
            sentry_sdk.capture_exception(err)
            self.logger.exception("Exception", exception=err)
            return self.ServerType(ip, version, "OFFLINE")

    async def get_minecraft_token_async(
        self, clientID, redirect_uri, act_code, verify_code=None
    ) -> dict:
        async with aiohttp.ClientSession() as httpSession:
            # get the access token
            endpoint = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
            params = {
                "client_id": clientID,
                "scope": "XboxLive.signin",
                "code": act_code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }
            if verify_code:
                params["code_verifier"] = verify_code

            async with httpSession.post(
                endpoint,
                data=params,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            ) as res:
                # get the access token
                if res.status == 200:
                    rjson = await res.json()
                    accessToken = rjson["access_token"]
                else:
                    self.logger.print("Failed to get access token")
                    try:
                        error_j = await res.json()
                        self.logger.error(
                            error_j["error"], error_j["error_description"]
                        )
                    except KeyError:
                        self.logger.error(res.reason)
                    return {"type": "error", "error": "Failed to get access token"}

            # obtain xbl token
            url = "https://user.auth.xboxlive.com/user/authenticate"
            async with httpSession.post(
                url,
                json={
                    "Properties": {
                        "AuthMethod": "RPS",
                        "SiteName": "user.auth.xboxlive.com",
                        "RpsTicket": f"d={accessToken}",
                    },
                    "RelyingParty": "http://auth.xboxlive.com",  # changed from http -> https
                    "TokenType": "JWT",
                },
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            ) as res2:
                if res2.status == 200:
                    xblToken = (await res2.json())["Token"]
                else:
                    self.logger.print("Failed to verify account: ", res2.status)
                    self.logger.error(res2.reason)
                    self.logger.error(res2.text)
                    return {"type": "error", "error": "Failed to verify account"}

            # obtain xsts token
            url = "https://xsts.auth.xboxlive.com/xsts/authorize"
            async with httpSession.post(
                url,
                json={
                    "Properties": {
                        "SandboxId": "RETAIL",
                        "UserTokens": [xblToken],
                    },
                    "RelyingParty": "rp://api.minecraftservices.com/",
                    "TokenType": "JWT",
                },
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            ) as res3:
                if res3.status == 200:
                    xstsToken = (await res3.json())["Token"]
                else:
                    self.logger.print("Failed to obtain xsts token")
                    self.logger.error(res3.reason)
                    return {"type": "error", "error": "Failed to obtain xsts token"}

            # obtain minecraft token
            xuid = (await res3.json())["DisplayClaims"]["xui"][0]["uhs"]
            url = "https://api.minecraftservices.com/authentication/login_with_xbox"
            async with httpSession.post(
                url,
                json={
                    "identityToken": f"XBL3.0 x={xuid};{xstsToken}",
                },
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            ) as res4:
                if res4.status == 200:
                    minecraftToken = (await res4.json())["access_token"]
                    self.logger.print("Got Minecraft token")
                else:
                    self.logger.print("Failed to obtain minecraft token")
                    self.logger.error(res4.reason)
                    return {
                        "type": "error",
                        "error": "Failed to obtain minecraft token",
                    }

            # get the profile
            url = "https://api.minecraftservices.com/minecraft/profile"
            async with httpSession.get(
                url,
                headers={
                    "Authorization": f"Bearer {minecraftToken}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            ) as res5:
                if res5.status == 200 and "error" not in str(await res5.json()):
                    uuid = (await res5.json())["id"]
                    name = (await res5.json())["name"]
                    self.logger.print("Name: " + name + " UUID: " + uuid)
                else:
                    self.logger.print("Failed to obtain profile")
                    self.logger.error(res5.reason)
                    return {"type": "error", "error": "Failed to obtain profile"}

            return {
                "type": "success",
                "uuid": uuid,
                "name": name,
                "minecraft_token": minecraftToken,
            }

    def get_minecraft_token(
        self, clientID, redirect_uri, act_code, verify_code=None
    ) -> dict:
        # get the access token
        endpoint = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
        params = {
            "client_id": clientID,
            "scope": "XboxLive.signin",
            "code": act_code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        if verify_code:
            params["code_verifier"] = verify_code
        res = requests.post(
            endpoint,
            data=params,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        # get the access token
        if res.status_code == 200:
            rjson = res.json()
            accessToken = rjson["access_token"]
        else:
            self.logger.print("Failed to get access token")
            try:
                error_j = res.json()
                self.logger.error(error_j["error"], error_j["error_description"])
            except KeyError:
                self.logger.error(res.reason)
            return {"type": "error", "error": "Failed to get access token"}

        # obtain xbl token
        url = "https://user.auth.xboxlive.com/user/authenticate"
        res2 = requests.post(
            url,
            json={
                "Properties": {
                    "AuthMethod": "RPS",
                    "SiteName": "user.auth.xboxlive.com",
                    "RpsTicket": f"d={accessToken}",
                },
                "RelyingParty": "http://auth.xboxlive.com",  # changed from http -> https
                "TokenType": "JWT",
            },
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        if res2.status_code == 200:
            xblToken = res2.json()["Token"]
            self.logger.print("Verified account: " + xblToken)
        else:
            self.logger.print("Failed to verify account: ", res2.status_code)
            self.logger.error(res2.reason)
            self.logger.error(res2.text)
            return {"type": "error", "error": "Failed to verify account"}

        # obtain xsts token
        url = "https://xsts.auth.xboxlive.com/xsts/authorize"
        res3 = requests.post(
            url,
            json={
                "Properties": {
                    "SandboxId": "RETAIL",
                    "UserTokens": [xblToken],
                },
                "RelyingParty": "rp://api.minecraftservices.com/",
                "TokenType": "JWT",
            },
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        if res3.status_code == 200:
            xstsToken = res3.json()["Token"]
            self.logger.print("Got xsts token: " + xstsToken)
        else:
            self.logger.print("Failed to obtain xsts token")
            self.logger.error(res3.reason)
            return {"type": "error", "error": "Failed to obtain xsts token"}

        # obtain minecraft token
        xuid = res3.json()["DisplayClaims"]["xui"][0]["uhs"]
        url = "https://api.minecraftservices.com/authentication/login_with_xbox"
        res4 = requests.post(
            url,
            json={
                "identityToken": f"XBL3.0 x={xuid};{xstsToken}",
            },
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        if res4.status_code == 200:
            minecraftToken = res4.json()["access_token"]
            self.logger.print("Got xuid: " + xuid)
        else:
            self.logger.print("Failed to obtain minecraft token")
            self.logger.error(res4.reason)
            return {
                "type": "error",
                "error": "Failed to obtain minecraft token",
            }

        # get the profile
        url = "https://api.minecraftservices.com/minecraft/profile"
        res5 = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {minecraftToken}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        if res5.status_code == 200 and "error" not in str(res5.json()):
            uuid = res5.json()["id"]
            name = res5.json()["name"]
            self.logger.print("Name: " + name + " UUID: " + uuid)
        else:
            self.logger.print("Failed to obtain profile")
            self.logger.error(res5.reason)
            return {"type": "error", "error": "Failed to obtain profile"}

        return {
            "type": "success",
            "uuid": uuid,
            "name": name,
            "minecraft_token": minecraftToken,
        }

    @staticmethod
    def get_activation_code_url(clientID, redirect_uri):
        """Returns a url to get the activation code from microsoft."""

        (
            code_verifier,
            code_challenge,
            code_challenge_method,
        ) = Minecraft._generate_pkce_data()

        base_url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"

        state = int("0x" + os.urandom(16).hex(), 0)

        return (
            urllib.parse.urlparse(base_url)
            ._replace(
                query=urllib.parse.urlencode(
                    {
                        "client_id": clientID,
                        "response_type": "code",
                        "redirect_uri": redirect_uri,
                        "response_mode": "query",
                        "scope": "XboxLive.signin offline_access",
                        "prompt": "select_account",
                        "state": state,
                        "code_challenge": code_challenge,
                        "code_challenge_method": code_challenge_method,
                    }
                )
            )
            .geturl(),
            code_verifier,
            state,
        )

    def get_activation_code(self):
        """Returns the activation code from the server.

        Returns:
            str: the activation code
        """
        act = self.activationCode
        return act

    def start_http_server(self, port: int = 80):
        """spawns the server in a new thread"""

        def start_server(_port: int = 80):
            server = http.server.HTTPServer(("", _port), self.RequestHandler)
            server.serve_forever()

        thread = Thread(target=start_server, args=(port,))
        thread.start()

        return thread

    @staticmethod
    def _generate_pkce_data() -> Tuple[str, str, Literal["plain", "S256"]]:
        """
        Generates the PKCE code challenge and code verifier

        :return: A tuple containing the code_verifier, the code_challenge, and the code_challenge_method.
        """
        code_verifier = secrets.token_urlsafe(128)[:128]
        code_challenge = urlsafe_b64encode(
            sha256(code_verifier.encode("ascii")).digest()
        ).decode("ascii")[:-1]
        code_challenge_method = "S256"
        return (
            code_verifier,
            code_challenge,
            cast(Literal["plain", "S256"], code_challenge_method),
        )

    async def session_join(self, mine_token, server_hash, _uuid, name, tries=5):
        try:
            if tries <= 0:
                self.logger.war("Failed to authenticate account after 5 tries")
                return 1
            async with aiohttp.ClientSession() as httpSession:
                url = "https://sessionserver.mojang.com/session/minecraft/join"
                async with httpSession.post(
                    url,
                    json={
                        "accessToken": mine_token,
                        "selectedProfile": {
                            "id": _uuid.replace("-", ""),
                            "name": name,
                        },
                        "serverId": server_hash,
                    },
                    headers={
                        "Content-Type": "application/json",
                    },
                ) as res:
                    if res.status == 204:  # success
                        self.logger.debug(
                            "Authenticated account successfully " + (await res.text())
                        )
                        return 0
                    elif res.status == 403:  # bad something
                        jres = await res.json()
                        self.logger.print("Failed to authenticate account")
                        self.logger.print(jres["errorMessage"])
                    elif res.status == 503:  # service unavailable
                        # wait 1 second and try again
                        self.logger.print("Service unavailable")
                        await asyncio.sleep(1)
                        return await self.session_join(
                            mine_token, server_hash, _uuid, name, tries - 1
                        )
                    elif res.status == 429:
                        tries += 1
                        self.logger.war(
                            "Rate limited, trying again: " + (await res.text())
                        )
                        await asyncio.sleep(5)
                        return await self.session_join(
                            mine_token, server_hash, _uuid, name, tries
                        )
                    else:
                        self.logger.print("Failed to authenticate account")
                        self.logger.error(res.status, await res.text())

            return 1
        except Exception:
            self.logger.error(traceback.format_exc())

    @staticmethod
    async def send_syn(ip: str, port: int):
        """
        Sends a syn packet to the server.

        :param ip: The ip of the server
        :param port: The port of the server

        :return bool: Whether the server responded
        """

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect((ip, port))
            # return whether the server responded
            return True
        except Exception:
            return False

    def read_chat(self, chat: dict | str):
        try:
            if isinstance(chat, str):
                try:
                    chat = json.loads(chat)
                except json.JSONDecodeError:
                    return chat
            out = ""
            if "text" in chat:
                out += chat["text"]
            if "extra" in chat:
                for i in chat["extra"]:
                    out += self.read_chat(i)

            if "translate" in chat:
                out += chat["translate"] + ": "

            if "with" in chat:
                out += ", ".join(chat["with"])

            return out
        except Exception:
            self.logger.error(traceback.format_exc())
            return str(chat)

    async def vers_n2p(self, vers_name: str) -> int:
        """
        Converts a version name to a protocol version.

        :param vers_name: The version name to convert

        :return: The protocol version
        """

        versions_url = "https://gitlab.bixilon.de/bixilon/minosoft/-/raw/master/src/main/resources/assets/minosoft/mapping/versions.json"

        async with aiohttp.ClientSession() as httpSession:
            async with httpSession.get(versions_url) as res:
                if res.status == 200:
                    versions = await res.text()
                    versions = json.loads(versions)
                else:
                    self.logger.error("Failed to get versions")
                    return -1

        for i in versions.values():
            if i["name"] == vers_name:
                return i["protocol_id"]

    async def vers_p2n(self, vers: int) -> str:
        """
        Converts a protocol version to a version name.

        :param vers: The protocol version to convert

        :return: The version name
        """

        versions_url = "https://gitlab.bixilon.de/bixilon/minosoft/-/raw/master/src/main/resources/assets/minosoft/mapping/versions.json"

        async with aiohttp.ClientSession() as httpSession:
            async with httpSession.get(versions_url) as res:
                if res.status == 200:
                    versions = await res.text()
                    versions = json.loads(versions)
                else:
                    self.logger.error("Failed to get versions")
                    return -1

        for i in versions.values():
            if i["protocol_id"] == vers:
                return i["name"]

    @staticmethod
    def int2hex(num: int):
        return f"0x{num:02x}"
