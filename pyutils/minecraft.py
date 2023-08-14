import http.server
import json
import os
import traceback
from hashlib import sha1
from http.server import BaseHTTPRequestHandler
from threading import Thread

import aiohttp
import mcstatus
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
            self.wfile.write(
                bytes("Thanks for logging in!", "utf-8")
            )
            if "code" in self.path:
                global activationCode
                activationCode = self.path.split("=")[1][:-6]
                self.server.shutdown()

    def __init__(self, logger: Logger, server: Server, player: Player):
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
            self.logger.print("Getting server/player info")
            # get info on the server
            server = mcstatus.JavaServer.lookup(ip + ":" + str(port))
            version = server.status().version.protocol if version == -1 else version
            uuid = await self.player.async_get_uuid(player_username)

            if not uuid:
                self.logger.error("Player UUID not found")
                return self.ServerType(ip, version, "bad uuid")

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
            self.logger.print("Sent handshake packet:", handshake.read_utf())

            # Send login start packet: ID, username, include sig data, has uuid, uuid
            loginStart = Connection()

            if version > 760:
                loginStart.write_varint(0)  # Packet ID
                loginStart.write_utf(player_username)  # Username
            else:
                loginStart.write_varint(0)  # Packet ID
                loginStart.write_utf(player_username)  # Username
            connection.write_buffer(loginStart)
            self.logger.print("Sent login start packet:", loginStart.read_utf())

            # Read response
            response = connection.read_buffer()
            _id: int = response.read_varint()
            self.logger.print("Received packet ID:", _id)
            if _id == 2:
                self.logger.print("Logged in successfully")
                return self.ServerType(ip, version, "CRACKED")
            elif _id == 0:
                self.logger.print("Failed to login")
                self.logger.print(response.read_utf())
                return self.ServerType(ip, version, "UNKNOWN")
            elif _id == 3:
                self.logger.print("Setting compression")
                compression_threshold = response.read_varint()
                self.logger.print(f"Compression threshold: {compression_threshold}")

                response = connection.read_buffer()
                _id: int = response.read_varint()
            if _id == 1:
                self.logger.print("Encryption requested")
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

                self.logger.print(
                    f"Encryption info:\nserver_id: {server_id}\npublic_key: {public_key}\nverify_token: {verify_token}\nshared_secret: {shared_secret}\nverify_hash: {verify_hash}\npublic key: {pubKey}")

                # send encryption response
                self.logger.print("Sending encryption response")
                encryptedSharedSecret = pubKey.encrypt(shared_secret, PKCS1v15())
                encryptedVerifyToken = pubKey.encrypt(verify_token, PKCS1v15())

                encryptionResponse = Connection()
                encryptionResponse.write_varint(1)  # Packet ID
                encryptionResponse.write_varint(len(encryptedSharedSecret))
                encryptionResponse.write(encryptedSharedSecret)
                encryptionResponse.write_varint(len(encryptedVerifyToken))
                encryptionResponse.write(encryptedVerifyToken)

                connection.write_buffer(encryptionResponse)

                # check if the account owns the game
                self.logger.print("Checking if account owns the game")
                url = "https://api.minecraftservices.com/entitlements/mcstore"
                async with aiohttp.ClientSession().get(
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

                # verify the account with mojang
                self.logger.print("Verifying account")
                url = "https://sessionserver.mojang.com/session/minecraft/join"
                async with aiohttp.ClientSession().post(
                        url,
                        json={
                            "accessToken": mine_token,
                            "selectedProfile": uuid.replace("-", ""),
                            "serverId": verify_hash,
                        },
                        headers={
                            "Content-Type": "application/json",
                        },
                ) as res2:
                    if res2.status == 204:  # success
                        if "error" in res2.text:
                            self.logger.print("Failed to verify account")
                            self.logger.error(res2.text)
                            return self.ServerType(ip, version, "BAD_TOKEN")
                        else:
                            self.logger.print("Verified account")
                    else:
                        self.logger.print("Failed to verify account")
                        self.logger.error(res2.text)
                        return self.ServerType(ip, version, "BAD_TOKEN")

                    # listen for a set compression packet
                    try:
                        response = connection.read_buffer()
                    except OSError:
                        self.logger.print("Something went wrong!")
                        self.logger.error(traceback.format_exc())
                        return self.ServerType(ip, version, "UNKNOWN")
                    _id: int = response.read_varint()

                    if _id == 3:
                        self.logger.print("Setting compression")
                        compression_threshold = response.read_varint()
                        self.logger.print(f"Compression threshold: {compression_threshold}")
                    elif _id == 2:
                        self.logger.print("Logged in successfully")
                        return self.ServerType(ip, version, "PREMIUM")
                    elif _id == 0:
                        self.logger.print("Failed to login")
                        self.logger.print(response.read_utf())
                        return self.ServerType(ip, version, "WHITELISTED")
                    else:
                        self.logger.print("Failed to set compression")
                        return self.ServerType(ip, version, "UNKNOWN")

            else:
                self.logger.info("Unknown response: " + str(_id))
                try:
                    reason = response.read_utf()
                except UnicodeDecodeError:
                    reason = "Unknown"

                self.logger.info("Reason: " + reason)
                return self.ServerType(ip, version, "UNKNOWN")
        except TimeoutError:
            self.logger.print("Server timed out")
            self.logger.error("Server timed out")
            return self.ServerType(ip, version, "OFFLINE")
        except OSError:
            self.logger.print("Server did not respond")
            self.logger.error("Server did not respond: " + traceback.format_exc())
            return self.ServerType(ip, version, "UNKNOWN")
        except Exception:
            self.logger.print(traceback.format_exc())
            self.logger.error(traceback.format_exc())
            return self.ServerType(ip, version, "OFFLINE")

    async def get_minecraft_token(self, clientID, redirect_uri, act_code):
        # get access token
        endpoint = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
        async with aiohttp.ClientSession() as oauthSession:
            async with oauthSession.post(
                    endpoint,
                    data={
                        "client_id": clientID,
                        "scope": "XboxLive.signin",
                        "code": act_code,
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                    },
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
            ) as res:
                # get the access token
                if res.status == 200:
                    accessToken = (await res.json())["access_token"]
                else:
                    self.logger.print("Failed to get access token")
                    try:
                        error_j = await res.json()
                        self.logger.error(error_j["error"], error_j["error_description"])
                    except KeyError:
                        self.logger.error(res.reason)
                    return {"type": "error", "error": "Failed to get access token"}

        # verify account
        url = "https://user.auth.xboxlive.com/user/authenticate"
        async with aiohttp.ClientSession() as xblSession:
            async with xblSession.post(
                    url,
                    data=json.dumps({
                        "Properties": {
                            "AuthMethod": "RPS",
                            "SiteName": "user.auth.xboxlive.com",
                            "RpsTicket": f"d={accessToken}",
                        },
                        "RelyingParty": "https://auth.xboxlive.com",
                        "TokenType": "JWT",
                    }),
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
            ) as res2:
                if res2.status == 200:
                    xblToken = (await res2.json())["Token"]
                    self.logger.print("Verified account: " + xblToken)
                else:
                    self.logger.print("Failed to verify account")
                    self.logger.error(res2.reason, res2.request_info)
                    self.logger.error(await res2.text())
                    return {"type": "error", "error": "Failed to verify account"}

        # obtain xsts token
        url = "https://xsts.auth.xboxlive.com/xsts/authorize"
        async with aiohttp.ClientSession() as xstsSession:
            async with xstsSession.post(
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
                    self.logger.print("Got xsts token: " + xstsToken)
                else:
                    self.logger.print("Failed to obtain xsts token")
                    self.logger.error(res3.reason)
                    return {"type": "error", "error": "Failed to obtain xsts token"}

        # obtain minecraft token
        xuid = (await res3.json())["DisplayClaims"]["xui"][0]["uhs"]
        url = "https://api.minecraftservices.com/authentication/login_with_xbox"
        async with aiohttp.ClientSession() as xuidSession:
            async with xuidSession.post(
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
                    self.logger.print("Got xuid: " + xuid)
                else:
                    self.logger.print("Failed to obtain minecraft token")
                    self.logger.error(res4.reason)
                    return {"type": "error", "error": "Failed to obtain minecraft token"}

        # get the profile
        url = "https://api.minecraftservices.com/minecraft/profile"
        async with aiohttp.ClientSession() as profileSession:
            async with profileSession.get(
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

    @staticmethod
    def get_activation_code_url(clientID, redirect_uri):
        """Returns a url to get the activation code from microsoft."""

        # check if the redirect uri is http encoded
        if "%3A%2F%2F" not in redirect_uri:
            # encode the redirect uri
            redirect_uri = redirect_uri.replace(":", "%3A").replace("/", "%2F")

        return f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_id={clientID}&response_type=code&redirect_uri={redirect_uri}&response_mode=query&scope=XboxLive.signin&prompt=login"

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

        thread = Thread(target=start_server, args=(port,))
        thread.start()

        return thread