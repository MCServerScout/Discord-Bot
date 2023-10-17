import asyncio
import http.server
import json
import os
import secrets
import traceback
import urllib.parse
import zlib
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
            comp_thresh = 0

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
                        self.logger.print("Failed to check if account owns the game")
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

            self.compress_packet(handshake, comp_thresh, connection)
            self.logger.debug("Sent handshake packet")

            # Send login start packet: ID, username, include sig data, has uuid, uuid
            loginStart = Connection()

            loginStart.write_varint(0)  # Packet ID
            if len(player_username) > 16:
                self.logger.print("Username too long")
                return self.ServerType(ip, version, "BAD_USERNAME")
            loginStart.write_utf(player_username)  # Username

            if version >= 735:
                # write uuid by splitting it into two 64-bit integers
                uuid1 = int(_uuid.replace("-", "")[:16], 16)
                uuid2 = int(_uuid.replace("-", "")[16:], 16)
                loginStart.write_ulong(uuid1)
                loginStart.write_ulong(uuid2)

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
                reason = json.loads(response.read_utf())
                reason = self.read_chat(reason)
                self.logger.print(reason)

                if any(i in reason.lower() for i in ["fml", "forge", "modded", "mods"]):
                    return self.ServerType(ip, version, "MODDED")
                elif any(i in reason.lower() for i in ["whitelist", "not whitelisted"]):
                    return self.ServerType(ip, version, "WHITELISTED")

                return self.ServerType(ip, version, "UNKNOWN")
            elif _id == 3:
                self.logger.print("Setting compression")
                comp_thresh = response.read_varint()
                self.logger.print(f"Compression threshold: {comp_thresh}")

                response = self.read_compressed(connection)
                _id: int = response.read_varint()
            if _id == 1:
                self.logger.debug("Encryption requested")
                if mine_token is None:
                    return self.ServerType(ip, version, "PREMIUM")

                # Read encryption request
                server_id = response.read_utf().encode("utf-8")
                length = response.read_varint()
                public_key = response.read(length)
                length = response.read_varint()
                try:
                    verify_token = response.read(length)
                except OSError:
                    self.logger.print("Weird packet")
                    verify_token = response.read(response.remaining())
                    self.logger.debug(
                        f"Length mismatch: {length} != {len(verify_token)}"
                    )

                shared_secret = os.urandom(16)

                # change verify_token to bytes form bytearray
                verify_token = bytes(verify_token)

                shaHash = sha1()
                shaHash.update(server_id)
                shaHash.update(shared_secret)
                shaHash.update(public_key)
                verify_hash = shaHash.hexdigest()

                pubKey = load_der_public_key(public_key, default_backend())

                self.logger.debug("Sending authentication request")
                if await self.session_join(
                    mine_token=mine_token, server_hash=verify_hash, _uuid=_uuid
                ):
                    self.logger.print("Failed to authenticate account")

                # send encryption response
                self.logger.debug("Sending encryption response")
                encryptedSharedSecret = pubKey.encrypt(shared_secret, PKCS1v15())
                encryptedVerifyToken = pubKey.encrypt(verify_token, PKCS1v15())

                encryptionResponse = Connection()
                encryptionResponse.write_varint(1)  # Packet ID
                encryptionResponse.write_varint(len(encryptedSharedSecret))
                encryptionResponse.write(encryptedSharedSecret)
                encryptionResponse.write_varint(len(encryptedVerifyToken))
                encryptionResponse.write(encryptedVerifyToken)

                self.compress_packet(encryptionResponse, comp_thresh, connection)
                self.logger.debug("Sent encryption response")

                # listen for a set compression packet
                try:
                    _id = 0x71
                    weird_ps = 0
                    while _id > 0x70:
                        if comp_thresh > 0:
                            response = self.read_compressed(connection)
                        else:
                            response = connection.read_buffer()

                        _id = response.read_varint()
                        if _id >= 1000:
                            weird_ps += 1
                            if weird_ps > 2:
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
                    comp_thresh = response.read_varint()
                    self.logger.print(
                        f"Compression threshold (after enc): {comp_thresh}"
                    )

                    response = self.read_compressed(connection)
                    _id: int = response.read_varint()

                if _id == 0:
                    self.logger.print("Failed to login")
                    reason = json.loads(response.read_utf())
                    reason = self.read_chat(reason)
                    self.logger.print(reason)

                    return self.ServerType(ip, version, "WHITELISTED")
                elif _id < 0:
                    self.logger.print("This server is a honey pot: " + str(_id))
                    return self.ServerType(ip, version, "HONEY_POT")
                elif _id == 2:
                    self.logger.print("Logged in successfully")

                    try:
                        # send a login acknowledgement
                        self.logger.debug("Sending login ack")
                        loginAck = Connection()

                        loginAck.write_varint(3)  # Packet ID

                        self.compress_packet(loginAck, comp_thresh, connection)
                    except Exception:
                        self.logger.error(traceback.format_exc())

                    return self.ServerType(ip, version, "PREMIUM")
                else:
                    self.logger.print("Logged in successfully")

                    return self.ServerType(ip, version, "PREMIUM")
            elif _id == 4:
                # load plugin request
                self.logger.debug("Loading plugins")

                return self.ServerType(ip, version, "MODDED")
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
        except ConnectionRefusedError:
            return self.ServerType(ip, version, "OFFLINE:ConnectionRefused")
        except TypeError:
            self.logger.error(traceback.format_exc())
            return self.ServerType(ip, version, "OFFLINE:TypeError")
        except Exception as e:
            sentry_sdk.capture_exception(e)
            self.logger.debug(traceback.format_exc())
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
                self.logger.error(error_j["error"],
                                  error_j["error_description"])
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
                self.logger.print("Failed to authenticate account after 5 tries")
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
                        return await self.session_join(
                            mine_token, server_hash, _uuid, tries + 1
                        )
                    elif res.status == 429:
                        tries += 1
                        await asyncio.sleep(1)
                        return await self.session_join(
                            mine_token, server_hash, _uuid, tries
                        )
                    else:
                        self.logger.print("Failed to authenticate account")
                        self.logger.error(res.status, await res.text())

            return 1
        except Exception:
            self.logger.error(traceback.format_exc())

    @staticmethod
    def compress_packet(packet: Connection, threshold, connection: Connection) -> None:
        """
        Compresses a packet if it is over the threshold in the format of:

            Length of (Data Length) + Compressed length of (Packet ID + Data)
            Length of uncompressed data
            Packet ID
            Data

        Args:
            packet (Connection): the packet to compress
            threshold (int): the threshold to compress at
            connection (Connection): the connection to write to

        Returns:
            Connection: the compressed packet
        """

        if threshold <= 0:
            connection.write_buffer(packet)

        data = packet.flush()

        # get the total length of the packet
        uncomp_len = len(data)

        if uncomp_len < threshold:
            # we can send uncompressed but in a different format
            # data length is now 0
            new_data = Connection()
            new_data.write_varint(uncomp_len)  # packet length
            new_data.write_varint(0)  # data length
            new_data.write(data[0:1])  # packet id
            new_data.write(data[1:])  # data

            return new_data

        # compress the packet with zlib
        cdata = zlib.compress(data)

        # packet length is now the Length of (Data Length) + Compressed length of (Packet ID + Data)
        new_data = Connection()
        new_data.write_varint(len(cdata) + 1)  # packet length
        new_data.write_varint(uncomp_len)  # data length
        new_data.write(cdata)  # compressed data

        connection.write(new_data.flush())

    def read_compressed(self, con: Connection):
        try:
            length = con.read_varint()
            data_length = con.read_varint()

            result = Connection()
            comp = con.read(length)
            data = zlib.decompress(comp)
            if len(data) != data_length:
                raise Exception("Data length does not match")

            self.logger.debug(f"Data: {data}")

            result.receive(data)

            return result
        except Exception:
            self.logger.error(traceback.format_exc())
            return con

    def read_chat(self, chat: dict):
        try:
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
