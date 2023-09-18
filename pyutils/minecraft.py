import asyncio
import http.server
import os
import secrets
import traceback
import urllib.parse
from base64 import urlsafe_b64encode
from hashlib import sha1, sha256
from http.server import BaseHTTPRequestHandler
from threading import Thread
from typing import Tuple, Literal, cast

import aiohttp
import mcstatus
import requests
import sentry_sdk
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.serialization import load_der_public_key
from mcstatus.protocol.connection import Connection, TCPSocketConnection

from .logger import Logger
from .player import Player
from .server import Server


class Minecraft:
    """
    Steps:
    1. Request authorization url
    2. Start the http server
    3. Send the auth url to the user
    4. Wait for the user to login
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
            BaseHTTPRequestHandler (_type_): the base request handler
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

    def __init__(self, logger: Logger, server: Server, player: Player):
        self.key = os.urandom(16)
        self.logger = logger
        self.server = server
        self.player = player

    async def join(
        self,
        ip: str,
        port: int,
        player_username: str,
        version: int = 47,
        mine_token: str = None,
    ) -> ServerType:
        try:
            # get info on the server
            server = mcstatus.JavaServer.lookup(ip + ":" + str(port))
            version = server.status().version.protocol if version == -1 else version
            _uuid = await self.player.async_get_uuid(player_username)

            if not _uuid:
                self.logger.print("Player UUID not found")
                return self.ServerType(ip, version, "bad uuid")

            _uuid = _uuid.replace("-", "")
            _uuid = (
                f"{_uuid[:8]}-{_uuid[8:12]}-{_uuid[12:16]}-{_uuid[16:20]}-{_uuid[20:]}"
            )
            async with aiohttp.ClientSession() as httpSession:
                # check if the account owns the game
                url = "https://api.minecraftservices.com/entitlements/mcstore"
                async with httpSession.get(
                    url,
                    headers={
                        "Authorization": "Bearer {}".format(mine_token),
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
                        self.logger.print(
                            "Failed to check if account owns the game")
                        self.logger.error(res.text)
                        return self.ServerType(ip, version, "BAD_TOKEN")

            connection = TCPSocketConnection((ip, port))

            # Send a handshake packet: ID, protocol version, server address, server port, intention to log in
            # This does not change between versions
            handshake = Connection()

            handshake.write_varint(0)  # Packet ID
            handshake.write_varint(version)  # Protocol version
            handshake.write_utf(ip)  # Server address
            handshake.write_ushort(int(port))  # Server port
            handshake.write_varint(2)  # Intention to login

            connection.write_buffer(handshake)
            self.logger.debug("Sent handshake packet")

            # Send login start packet: ID, username, include sig data, has uuid, uuid
            loginStart = Connection()

            loginStart.write_varint(0)  # Packet ID
            if len(player_username) > 16:
                self.logger.print("Username too long")
                return self.ServerType(ip, version, "BAD_USERNAME")
            loginStart.write_utf(player_username)  # Username

            connection.write_buffer(loginStart)
            self.logger.debug("Sent login start packet")

            # Read response
            try:
                response = connection.read_buffer()
            except OSError:
                self.logger.print("No response from server")
                return self.ServerType(ip, version, "OFFLINE")

            _id: int = response.read_varint()
            self.logger.debug("Received packet ID:", _id)
            if _id == 2:
                self.logger.print("Logged in successfully")
                return self.ServerType(ip, version, "CRACKED")
            elif _id == 0:
                self.logger.print("Failed to login")
                reason = response.read_utf()
                self.logger.print(reason)
                if any(i in reason.lower() for i in ["fml", "forge", "modded", "mods"]):
                    return self.ServerType(ip, version, "MODDED")
                elif any(i in reason.lower() for i in ["whitelist", "not whitelisted"]):
                    return self.ServerType(ip, version, "WHITELISTED")

                return self.ServerType(ip, version, "UNKNOWN")
            elif _id == 3:
                self.logger.print("Setting compression")
                compression_threshold = response.read_varint()
                self.logger.print(f"Compression threshold: {compression_threshold}")

                response = connection.read_buffer()
                _id: int = response.read_varint()
            if _id == 1:
                self.logger.debug("Encryption requested")
                if mine_token is None:
                    return self.ServerType(ip, version, "PREMIUM")

                # Read encryption request
                length = response.read_varint()
                server_id = response.read(length)
                length = response.read_varint()
                public_key = response.read(length)
                length = response.read_varint()
                verify_token = response.read(length)

                shared_secret = os.urandom(16)

                # change verify_token to bytes form bytearray
                verify_token = bytes(verify_token)

                shaHash = sha1()
                shaHash.update(server_id)
                shaHash.update(shared_secret)
                shaHash.update(public_key)
                verify_hash = shaHash.hexdigest()

                pubKey = load_der_public_key(public_key, default_backend())

                self.logger.debug(
                    f"Encryption info:\nserver_id: {server_id}\npublic_key: {public_key}\nverify_token: {verify_token}\nshared_secret: {shared_secret}\nverify_hash: {verify_hash}\npublic key: {pubKey}"
                )

                self.logger.debug("Sending authentication request")
                await self.session_join(
                    mine_token=mine_token, server_hash=verify_hash, _uuid=_uuid
                )

                # send encryption response
                self.logger.debug("Sending encryption response")
                encryptedSharedSecret = pubKey.encrypt(
                    shared_secret, PKCS1v15())
                encryptedVerifyToken = pubKey.encrypt(verify_token, PKCS1v15())

                encryptionResponse = Connection()
                encryptionResponse.write_varint(1)  # Packet ID
                encryptionResponse.write_varint(len(encryptedSharedSecret))
                encryptionResponse.write(encryptedSharedSecret)
                encryptionResponse.write_varint(len(encryptedVerifyToken))
                encryptionResponse.write(encryptedVerifyToken)

                connection.write_buffer(encryptionResponse)
                self.logger.debug("Sent encryption response")

                # listen for a set compression packet
                try:
                    _id = 51
                    werid_ps = 0
                    while _id > 50:
                        response = connection.read_buffer()
                        _id = response.read_varint()
                        if _id >= 1000:
                            werid_ps += 1
                            if werid_ps > 2:
                                self.logger.print(
                                    "Server is sending weird packets and probably modded"
                                )
                                return self.ServerType(ip, version, "MODDED")
                            continue
                        self.logger.debug("Received packet ID:", _id)
                except OSError:
                    self.logger.print("Invalid session")
                    return self.ServerType(ip, version, "BAD_SESSION")

                if _id == 3:
                    self.logger.print("Setting compression")
                    compression_threshold = response.read_varint()
                    self.logger.print(
                        f"Compression threshold: {compression_threshold}")

                    response = connection.read_buffer()
                    _id: int = response.read_varint()

                if _id == 0:
                    self.logger.print("Failed to login")
                    return self.ServerType(ip, version, "WHITELISTED")
                else:
                    self.logger.print("Logged in successfully")
                    return self.ServerType(ip, version, "PREMIUM")
            else:
                self.logger.info("Unknown response: " + str(_id))
                try:
                    reason = response.read_utf()
                except UnicodeDecodeError:
                    reason = "Unknown"

                self.logger.info("Reason: " + reason)
                return self.ServerType(ip, version, "UNKNOWN: " + reason)
        except TimeoutError:
            return self.ServerType(ip, version, "OFFLINE:Timeout")
        except TypeError:
            self.logger.error(traceback.format_exc())
            return self.ServerType(ip, version, "OFFLINE:TypeError")
        except Exception as e:
            sentry_sdk.capture_exception(e)
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
                    self.logger.debug("Got xbl token: ")
                else:
                    self.logger.print(
                        "Failed to verify account: ", res2.status)
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
                    self.logger.debug("Got xsts token: ")
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
                    "identityToken": "XBL3.0 x={};{}".format(xuid, xstsToken),
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
                    "Authorization": "Bearer {}".format(minecraftToken),
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
                "identityToken": "XBL3.0 x={};{}".format(xuid, xstsToken),
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
                "Authorization": "Bearer {}".format(minecraftToken),
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
                        "code_challenge": code_challenge,
                        "code_challenge_method": code_challenge_method,
                    }
                )
            )
            .geturl(),
            code_verifier,
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

    async def session_join(self, mine_token, server_hash, _uuid, tries=0):
        try:
            if tries > 5:
                self.logger.print(
                    "Failed to authenticate account after 5 tries")
                return 1
            async with aiohttp.ClientSession() as httpSession:
                url = "https://sessionserver.mojang.com/session/minecraft/join"
                async with httpSession.post(
                    url,
                    json={
                        "accessToken": mine_token,
                        "selectedProfile": _uuid.replace("-", ""),
                        "serverId": server_hash,
                    },
                    headers={
                        "Content-Type": "application/json",
                    },
                ) as res:
                    if res.status == 204:  # success
                        self.logger.debug(
                            "Authenticated account: " + (await res.text())
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
                        await self.session_join(
                            mine_token, server_hash, _uuid, tries + 1
                        )
                    else:
                        self.logger.print("Failed to authenticate account")
                        self.logger.error(res.status, await res.text())

            return 1
        except Exception:
            self.logger.error(traceback.format_exc())
