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
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import load_der_public_key
from mcstatus.protocol.connection import Connection, TCPSocketConnection

from .logger import Logger
from .player import Player
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
        version: int = -1,
    ) -> ServerType:
        try:
            # get info on the server
            server = mcstatus.JavaServer.lookup(ip + ":" + str(port))
            version = server.status().version.protocol if version == -1 else version

            # get the player's uuid
            _uuid = await self.player.async_get_uuid(player_username)
            # set the compression threshold off (<= 0)
            comp_thresh = 0

            # needed if a username is invalid
            if not _uuid:
                self.logger.print("Player UUID not found")
                return self.ServerType(ip, version, "bad uuid")

            _uuid = _uuid.replace("-", "")
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
                        self.logger.print(
                            "Failed to check if account owns the game")
                        self.logger.error(res.text)
                        return self.ServerType(ip, version, "BAD_TOKEN")

            # connect to the server via tcp socket
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

            if version > 758:
                # older protocols don't want the uuid
                # https://wiki.vg/index.php?title=Protocol&oldid=16918#Login_Start

                if version <= 760:
                    # a few want signature data
                    # https://wiki.vg/index.php?title=Protocol&oldid=17753#Login_Start
                    loginStart.write_bool(False)  # has sig data

                if version in [760, 761, 762, 763]:
                    # these want the uuid sometimes
                    # https://wiki.vg/index.php?title=Protocol&oldid=18375#Login_Start
                    loginStart.write_bool(True)  # has uuid

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
            if _id == 3:
                self.logger.print("Setting compression")
                comp_thresh = response.read_varint()
                self.logger.print(f"Compression threshold: {comp_thresh}")

                response = self.read_compressed(connection)
                _id: int = response.read_varint()

            if _id == 2:
                self.logger.print("Logged in successfully")
                return self.ServerType(ip, version, "CRACKED")
            elif _id == 0:
                self.logger.print(f"Failed to login, vers: {version}")
                reason = json.loads(response.read_utf())
                reason = self.read_chat(reason)
                self.logger.print(reason)

                if any(i in reason.lower() for i in ["fml", "forge", "modded", "mods"]):
                    return self.ServerType(ip, version, "MODDED")
                elif any(i in reason.lower() for i in ["whitelist", "not whitelisted"]):
                    return self.ServerType(ip, version, "WHITELISTED")
                elif reason.startswith("multiplayer.disconnect.incompatible:"):
                    vers = reason.split(":")[1].strip()
                    protocol = self.text.protocol_int(vers)

                    return await self.join(
                        ip=ip,
                        port=port,
                        player_username=player_username,
                        version=protocol,
                        mine_token=mine_token,
                    )

                return self.ServerType(ip, version, "UNKNOWN")
            elif _id == 1:
                self.logger.debug("Encryption requested")
                if mine_token is None:
                    return self.ServerType(ip, version, "PREMIUM")

                # Read encryption request
                length = response.read_varint()
                server_id = response.read(length)
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
                    self.logger.debug(
                        f"Server id: {server_id}\nPublic key: {public_key}\nVerify token: {verify_token}"
                    )

                shared_secret = os.urandom(16)

                # change verify_token to bytes form bytearray
                verify_token = bytes(verify_token)

                # create the server hash
                # https://wiki.vg/Protocol_Encryption#Client
                shaHash = sha1()  # skipcq: PTC-W1003
                shaHash.update(server_id)
                shaHash.update(shared_secret)
                shaHash.update(public_key)
                verify_hash = shaHash.hexdigest()

                print(
                    f"Server id: {server_id}\n"
                    f"Public key: {public_key}\n"
                    f"Verify token: {verify_token}\n"
                    f"Shared secret: {shared_secret}\n"
                    f"Verify hash: {verify_hash}"
                )

                # load the public key into an object, so we can use it to encrypt bytes
                pubKey = load_der_public_key(public_key, default_backend())

                # create a cipher object to encrypt the packet after encryption response
                # use the shared secret as the key and iv
                cipher = Cipher(
                    # key
                    algorithms.AES(shared_secret),
                    # iv
                    modes.CFB8(shared_secret),
                )
                encryptor = cipher.encryptor()
                decryptor = cipher.decryptor()

                # send a request to mojang servers to request that we are joining a server
                self.logger.debug("Sending authentication request")
                if await self.session_join(
                    mine_token=mine_token, server_hash=verify_hash, _uuid=_uuid
                ):
                    self.logger.print("Failed to authenticate account")

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

                self.compress_packet(encryptionResponse,
                                     connection, comp_thresh)
                self.logger.debug("Sent encryption response")

                # listen for a set compression packet
                try:
                    _id = 0x71
                    weird_ps = 0
                    # keep looping until we get a packet ID that is valid
                    while _id > 0x70:
                        if comp_thresh > 0:
                            response = self.read_compressed(connection)
                        else:
                            response = connection.read_buffer()

                        # decrypt the packet
                        data = response.read(response.remaining())
                        response = self.decrypt_data(data, decryptor)

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
                    self.logger.print(f"Failed to login, vers: {version}")
                    reason = json.loads(response.read_utf())
                    reason = self.read_chat(reason)
                    self.logger.print(reason)

                    if "whitelist" in reason.lower() or " ban " in reason.lower():
                        return self.ServerType(ip, version, "WHITELISTED")

                    return self.ServerType(ip, version, "ERRORED")
                elif _id < 0:
                    # all packet ids must be positive and less than 0x70 (not in(70), but rather int(112))
                    self.logger.print(
                        "This server is a honey pot: " + str(_id))
                    return self.ServerType(ip, version, "HONEY_POT")
                elif _id == 2:
                    self.logger.print("Logged in successfully")

                    uuid1 = response.read_ulong()
                    uuid2 = response.read_ulong()
                    # convert to hex and add dashes
                    uuid = f"{uuid1:016x}-{uuid2:016x}"
                    self.logger.debug("UUID:", uuid)

                    uname = response.read_utf()

                    remaining_properties = response.read_varint()
                    props = {}
                    for _ in range(remaining_properties):
                        name = response.read_utf()
                        value = response.read_utf()
                        has_signature = response.read_bool()
                        if has_signature:
                            signature_length = response.read_varint()
                            _ = response.read(signature_length)

                        props[name] = value

                    self.logger.debug("Username:", uname)
                    self.logger.debug("Properties:", props)

                    try:
                        # send a login acknowledgement
                        self.logger.debug("Sending login ack")
                        loginAck = Connection()

                        loginAck.write_varint(3)  # Packet ID

                        self.compress_packet(
                            loginAck, comp_thresh, connection, encryptor
                        )
                    except Exception:
                        self.logger.error(traceback.format_exc())

                    return self.ServerType(ip, version, "PREMIUM")
                else:
                    # TODO: figure out why this is
                    # the server is probably sending config or play packets for some reason
                    self.logger.print("Logged in successfully")

                    return self.ServerType(ip, version, "PREMIUM")
            elif _id == 4:
                # load plugin request
                self.logger.debug("Loading plugins")

                message_id, channel, data = self.read_plugin(connection)

                self.logger.debug("Message ID:", message_id)
                self.logger.debug("Channel:", channel)
                self.logger.debug("Data:", data)

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

    def compress_packet(
        self,
        packet: Connection,
        connection: Connection,
        threshold=0,
        encryptor: Cipher.encryptor = None,
    ) -> None:
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
            encryptor (Cipher.encryptor): the encryptor to use if you want to encrypt the packet

        Returns:
            Connection: the compressed packet
        """

        if threshold <= 0:
            if encryptor:
                packet = self.encrypt_data(packet.flush(), encryptor)

            connection.write_buffer(packet)
            return

        data = packet.flush()

        # get the total length of the packet
        uncomp_len = len(data)

        if uncomp_len < threshold:
            # we can send uncompressed but in a different format
            # data length is now 0
            new_data = Connection()
            new_data.write_varint(0)  # uncompressed data length
            new_data.write(data)

            if encryptor:
                new_data = self.encrypt_data(new_data.flush(), encryptor)

            connection.write_buffer(new_data)
            return

        # compress the packet with zlib
        cdata = zlib.compress(data)

        packet = Connection()
        packet.write_varint(uncomp_len)  # packet length (uncompressed)
        packet.write(cdata)  # compressed data

        if encryptor:
            packet = self.encrypt_data(packet.flush(), encryptor)

        connection.write_buffer(packet)

    def read_compressed(self, con: Connection):
        try:
            data = con.read_buffer()

            uncomp_len = data.read_varint()
            cdata = data.read(data.remaining())

            if uncomp_len == 0:
                # the data is not compressed
                data = cdata
                uncomp_len = len(data)
            else:
                data = zlib.decompress(cdata)

            if len(data) != uncomp_len:
                self.logger.print(
                    f"Length mismatch when decompressing: {len(data)} != {uncomp_len}"
                )

            out = Connection()
            out.receive(data)

            return out
        except Exception as err:
            self.logger.error(traceback.format_exc())
            raise err

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

    def read_plugin(self, plugin: Connection):
        try:
            message_id = plugin.read_varint()
            channel = plugin.read_utf()

            data = plugin.read(plugin.remaining())

            return message_id, channel, data
        except Exception:
            self.logger.error(traceback.format_exc())
            return None, None, None

    def decrypt_packet(
        self, connection: TCPSocketConnection, decryptor: Cipher.decryptor
    ) -> Connection:
        try:
            # everything is encrypted so first receive all the data
            data = connection.read(connection.remaining())

            # decrypt the data
            unc_data = self.decrypt_data(data, decryptor)

            return unc_data
        except Exception:
            self.logger.error(traceback.format_exc())
            return Connection()

    def decrypt_data(self, data: bytes, decryptor: Cipher.decryptor):
        try:
            unc_data = decryptor.update(data) + decryptor.finalize()
            out = Connection()
            out.receive(unc_data)
            out.write(unc_data)

            return out
        except Exception:
            self.logger.error(traceback.format_exc())
            return data

    def encrypt_data(self, data: bytes, encryptor: Cipher.encryptor):
        try:
            enc_data = encryptor.update(data) + encryptor.finalize()
            out = Connection()
            out.receive(enc_data)
            out.write(enc_data)

            return out
        except Exception:
            self.logger.error(traceback.format_exc())
            return data

    def can_join(self, ip: str, port: int, version: int, uname: str):
        try:
            uuid = self.player.get_uuid(uname)
            if not uuid:
                return False

            uuid = uuid.replace("-", "")
            uuid = f"{uuid[:8]}-{uuid[8:12]}-{uuid[12:16]}-{uuid[16:20]}-{uuid[20:]}"

            # connect to the server via tcp socket
            connection = TCPSocketConnection((ip, port))

            handshake = Connection()

            handshake.write_varint(0)  # Packet ID
            handshake.write_varint(version)  # Protocol version
            handshake.write_utf(ip)  # Server address
            handshake.write_ushort(int(port))  # Server port
            handshake.write_varint(2)  # Intention to login

            connection.write_buffer(handshake)

            # Send login start packet: ID, username, include sig data, has uuid, uuid
            loginStart = Connection()

            loginStart.write_varint(0)  # Packet ID
            if len(uname) > 16:
                self.logger.print("Username too long")
                return False

            loginStart.write_utf(uname)  # Username

            if version > 758:
                # older protocols don't want the uuid
                # https://wiki.vg/index.php?title=Protocol&oldid=16918#Login_Start

                if version <= 760:
                    # a few want signature data
                    # https://wiki.vg/index.php?title=Protocol&oldid=17753#Login_Start
                    loginStart.write_bool(False)

                if version in [760, 761, 762, 763]:
                    # these want the uuid sometimes
                    # https://wiki.vg/index.php?title=Protocol&oldid=18375#Login_Start
                    loginStart.write_bool(True)

                # write uuid by splitting it into two 64-bit integers
                uuid1 = int(uuid.replace("-", "")[:16], 16)
                uuid2 = int(uuid.replace("-", "")[16:], 16)
                loginStart.write_ulong(uuid1)
                loginStart.write_ulong(uuid2)

            connection.write_buffer(loginStart)

            # Read response
            try:
                response = connection.read_buffer()
            except OSError:
                self.logger.print("No response from server")
                return False

            _id: int = response.read_varint()
            self.logger.debug("Received packet ID:", _id)

            if _id == 3:
                self.logger.print("Setting compression")
                comp_thresh = response.read_varint()
                self.logger.print(f"Compression threshold: {comp_thresh}")

                response = self.read_compressed(connection)
                _id: int = response.read_varint()

            if _id in (2, 1):
                return True

            if _id == 0:
                self.logger.print(f"Failed to login, vers: {version}")
                reason = json.loads(response.read_utf())
                reason = self.read_chat(reason)
                self.logger.print(reason)

                return reason

            return False
        except Exception:
            self.logger.error(traceback.format_exc())
            return False
