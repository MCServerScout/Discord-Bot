"""
Microsoft_account contains functions for login with a Microsoft Account. Before using this module you need to `create an Azure application <https://docs.microsoft.com/en-us/azure/active-directory/develop/quickstart-register-app>`_.
Many thanks to wiki.vg for it `documentation of the login process <https://wiki.vg/Microsoft_Authentication_Scheme>`_.
You may want to read the :doc:`/tutorial/microsoft_login` tutorial before using this module.
For a list of all types see :doc:`microsoft_types`.

.. Note::
    Copied verbatim from https://codeberg.org/JakobDev/minecraft-launcher-lib/src/commit/a0742a9c728456654fbd45347c8ac7ff26a9993a/minecraft_launcher_lib/microsoft_account.py
    then modified to be async and to use aiohttp instead of requests.
"""
import secrets
import urllib.parse
from base64 import urlsafe_b64encode
from hashlib import sha256
from typing import Literal, Optional, Tuple, cast

import aiohttp

from .microsoft_types import (
    AuthorizationTokenResponse,
    XBLResponse,
    XSTSResponse,
    MinecraftAuthenticateResponse,
    MinecraftStoreResponse,
    MinecraftProfileResponse,
    CompleteLoginResponse,
)

__AUTH_URL__ = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
__TOKEN_URL__ = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
__SCOPE__ = "XboxLive.signin offline_access"


def get_login_url(client_id: str, redirect_uri: str) -> str:
    """
    Generate a login url.\\
    For a more secure alternative, use :func:`get_secure_login_data`

    :param client_id: The Client ID of your Azure App
    :param redirect_uri: The Redirect URI of your Azure App
    :return: The url to the website on which the user logs in
    """
    parameters = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": __SCOPE__,
    }

    url = (
        urllib.parse.urlparse(__AUTH_URL__)
        ._replace(query=urllib.parse.urlencode(parameters))
        .geturl()
    )
    return url


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


def generate_state() -> str:
    """
    Generates a random state
    """
    return secrets.token_urlsafe(16)


def get_secure_login_data(
    client_id: str, redirect_uri: str, state: Optional[str] = None
) -> Tuple[str, str, str]:
    """
    Generates the login data for a secure login with pkce and state.\\
    Prevents Cross-Site Request Forgery attacks and authorization code injection attacks.

    :param client_id: The Client ID of your Azure App
    :param redirect_uri: The Redirect URI of your Azure App
    :param state: You can use an existing state. If not set, a state will be generated using :func:`generate_state`.
    """
    code_verifier, code_challenge, code_challenge_method = _generate_pkce_data()

    if state is None:
        state = generate_state()

    parameters = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": __SCOPE__,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
    }

    url = (
        urllib.parse.urlparse(__AUTH_URL__)
        ._replace(query=urllib.parse.urlencode(parameters))
        .geturl()
    )

    return url, state, code_verifier


def url_contains_auth_code(url: str) -> bool:
    """
    Checks if the given url contains an authorization code

    :param url: The URL to check
    """
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    return "code" in qs


def get_auth_code_from_url(url: str) -> Optional[str]:
    """
    Get the authorization code from the url.\\
    If you want to check the state, use :func:`parse_auth_code_url`, which throws errors instead of returning an optional value.

    :param url: The URL to parse
    :return: The auth code or None if the code is nonexistent
    """
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    try:
        return qs["code"][0]
    except KeyError:
        return None


def parse_auth_code_url(url: str, state: Optional[str]) -> str:
    """
    Parse the authorization code url and checks the state.

    :param url: The URL to parse
    :param state: If set, the function raises an AssertionError, if the state does not match the state in the URL
    :return: The auth code
    """
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)

    if state is not None:
        assert state == qs["state"][0]

    return qs["code"][0]


async def get_authorization_token(
    client_id: str,
    client_secret: Optional[str],
    redirect_uri: str,
    auth_code: str,
    session: aiohttp.ClientSession,
    code_verifier: Optional[str] = None,
) -> AuthorizationTokenResponse:
    """
    Get the authorization token. This function is called during :func:`complete_login`, so you need to use this function only if :func:`complete_login` doesn't work for you.

    :param client_id: The Client ID of your Azure App
    :param client_secret: The Client Secret of your Azure App. This is deprecated and should not be used anymore.
    :param redirect_uri: The Redirect URI of your Azure App
    :param auth_code: The Code you get from :func:`parse_auth_code_url`
    :param session: The aiohttp session
    :param code_verifier: The 3rd entry in the Tuple you get from :func:`get_secure_login_data`
    """
    parameters = {
        "client_id": client_id,
        "scope": __SCOPE__,
        "code": auth_code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    if client_secret is not None:
        parameters["client_secret"] = client_secret

    if code_verifier is not None:
        parameters["code_verifier"] = code_verifier

    header = {
        "Content-Type": "application/x-www-form-urlencoded",
    }
    async with session.post(__TOKEN_URL__, data=parameters, headers=header) as r:
        return await r.json()


async def refresh_authorization_token(
    client_id: str,
    client_secret: Optional[str],
    redirect_uri: Optional[str],
    refresh_token: str,
    session: aiohttp.ClientSession,
) -> AuthorizationTokenResponse:
    """
    Refresh the authorization token. This function is called during :func:`complete_refresh`, so you need to use this function only if :func:`complete_refresh` doesn't work for you.

    :param client_id: The Client ID of your Azure App
    :param client_secret: The Client Secret of your Azure App. This is deprecated and should not be used anymore.
    :param redirect_uri: The Redirect URI of Azure App. This Parameter only exists for backwards compatibility and is not used anymore.
    :param refresh_token: Your refresh token
    :param session: The aiohttp session
    """
    parameters = {
        "client_id": client_id,
        "scope": __SCOPE__,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    if client_secret is not None:
        parameters["client_secret"] = client_secret

    # redirect_uri was used in a previous version of this library
    # we keep it for backwards compatibility, but it is not required anymore
    _ = redirect_uri

    async with session.post(__TOKEN_URL__, data=parameters) as r:
        return await r.json()


async def authenticate_with_xbl(
    access_token: str, session: aiohttp.ClientSession
) -> XBLResponse:
    """
    Authenticate with Xbox Live. This function is called during :func:`complete_login`, so you need to use this function only if :func:`complete_login` doesn't work for you.

    :param access_token: The Token you get from :func:`get_authorization_token`
    :param session: The aiohttp session
    """
    parameters = {
        "Properties": {
            "AuthMethod": "RPS",
            "SiteName": "user.auth.xboxlive.com",
            "RpsTicket": f"d={access_token}",
        },
        "RelyingParty": "http://auth.xboxlive.com",
        "TokenType": "JWT",
    }
    header = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    async with session.post(
        "https://user.auth.xboxlive.com/user/authenticate",
        json=parameters,
        headers=header,
    ) as r:
        return await r.json()


async def authenticate_with_xsts(
    xbl_token: str, session: aiohttp.ClientSession
) -> XSTSResponse:
    """
    Authenticate with XSTS. This function is called during :func:`complete_login`, so you need to use this function only if :func:`complete_login` doesn't work for you.

    :param xbl_token: The Token you get from :func:`authenticate_with_xbl`
    :param session: The aiohttp session
    """
    parameters = {
        "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl_token]},
        "RelyingParty": "rp://api.minecraftservices.com/",
        "TokenType": "JWT",
    }
    header = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    async with session.post(
        "https://xsts.auth.xboxlive.com/xsts/authorize", json=parameters, headers=header
    ) as r:
        return await r.json()


async def authenticate_with_minecraft(
    userhash: str, xsts_token: str, session: aiohttp.ClientSession
) -> MinecraftAuthenticateResponse:
    """
    Authenticate with Minecraft. This function is called during :func:`complete_login`, so you need to use this function only if :func:`complete_login` doesn't work for you.

    :param userhash: The Hash you get from :func:`authenticate_with_xbl`
    :param xsts_token: The Token you get from :func:`authenticate_with_xsts`
    :param session: The aiohttp session
    """
    parameters = {"identityToken": f"XBL3.0 x={userhash};{xsts_token}"}
    header = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    async with session.post(
        "https://api.minecraftservices.com/authentication/login_with_xbox",
        json=parameters,
        headers=header,
    ) as r:
        return await r.json()


async def get_store_information(
    access_token: str, session: aiohttp.ClientSession
) -> MinecraftStoreResponse:
    """
    Get the store information.

    :param access_token: The Token you get from :func:`authenticate_with_minecraft`
    :param session: The aiohttp session
    """
    header = {"Authorization": f"Bearer {access_token}"}
    async with session.get(
        "https://api.minecraftservices.com/entitlements/mcstore", headers=header
    ) as r:
        return await r.json()


async def get_profile(
    access_token: str, session: aiohttp.ClientSession
) -> MinecraftProfileResponse:
    """
    Get the profile. This function is called during :func:`complete_login`, so you need to use this function ony if :func:`complete_login` doesnt't work for you.

    :param access_token: The Token you get from :func:`authenticate_with_minecraft`
    :param session: The aiohttp session
    """
    header = {"Authorization": f"Bearer {access_token}"}
    async with session.get(
        "https://api.minecraftservices.com/minecraft/profile", headers=header
    ) as r:
        return await r.json()


async def complete_login(
    client_id: str,
    client_secret: Optional[str],
    redirect_uri: str,
    auth_code: str,
    code_verifier: Optional[str] = None,
) -> CompleteLoginResponse:
    """
    Do the complete login process.

    :param client_id: The Client ID of your Azure App
    :param client_secret: The Client Secret of your Azure App. This is deprecated and should not been used anymore.
    :param redirect_uri: The Redirect URI of your Azure App
    :param auth_code: The Code you get from :func:`parse_auth_code_url`
    :param code_verifier: The 3rd entry in the Tuple you get from :func:`get_secure_login_data`
    :raises AzureAppNotPermitted: Your Azure App don't have the Permission to use the Minecraft API

    It returns the following:

    .. code:: json

        {
            "id" : "The uuid",
            "name" : "The username",
            "access_token": "The acces token",
            "refresh_token": "The refresh token",
            "skins" : [{
                "id" : "6a6e65e5-76dd-4c3c-a625-162924514568",
                "state" : "ACTIVE",
                "url" : "http://textures.minecraft.net/texture/1a4af718455d4aab528e7a61f86fa25e6a369d1768dcb13f7df319a713eb810b",
                "variant" : "CLASSIC",
                "alias" : "STEVE"
            } ],
            "capes" : []
        }
    """
    async with aiohttp.ClientSession() as session:
        token_request = await get_authorization_token(
            client_id, client_secret, redirect_uri, auth_code, session, code_verifier
        )
        token = token_request["access_token"]

        xbl_request = await authenticate_with_xbl(token, session)
        xbl_token = xbl_request["Token"]
        userhash = xbl_request["DisplayClaims"]["xui"][0]["uhs"]

        xsts_request = await authenticate_with_xsts(xbl_token, session)
        xsts_token = xsts_request["Token"]

        account_request = await authenticate_with_minecraft(
            userhash, xsts_token, session
        )

        if "access_token" not in account_request:
            raise Exception("Azure App not permitted")

        access_token = account_request["access_token"]

        profile = cast(
            CompleteLoginResponse, (await get_profile(access_token, session))
        )

        profile["access_token"] = account_request["access_token"]
        profile["refresh_token"] = token_request["refresh_token"]

        return profile


async def complete_refresh(
    client_id: str,
    client_secret: Optional[str],
    redirect_uri: Optional[str],
    refresh_token: str,
) -> CompleteLoginResponse:
    """
    Do the complete login process with a refresh token. It returns the same as :func:`complete_login`.

    :param client_id: The Client ID of your Azure App
    :param client_secret: The Client Secret of your Azure App. This is deprecated and should not been used anymore.
    :param redirect_uri: The Redirect URI of Azure App. This Parameter only exists for backwards compatibility and is not used anymore.
    :param refresh_token: Your refresh token
    :raises InvalidRefreshToken: Your refresh token is not valid

    Raises a :class:`~minecraft_launcher_lib.exceptions.InvalidRefreshToken` exception when the refresh token is invalid.
    """
    async with aiohttp.ClientSession() as session:
        token_request = await refresh_authorization_token(
            client_id, client_secret, redirect_uri, refresh_token, session
        )

        if "error" in token_request:
            raise Exception("Invalid refresh token")

        token = token_request["access_token"]

        xbl_request = await authenticate_with_xbl(token, session)
        xbl_token = xbl_request["Token"]
        userhash = xbl_request["DisplayClaims"]["xui"][0]["uhs"]

        xsts_request = await authenticate_with_xsts(xbl_token, session)
        xsts_token = xsts_request["Token"]

        account_request = await authenticate_with_minecraft(
            userhash, xsts_token, session
        )
        access_token = account_request["access_token"]

        profile = cast(
            CompleteLoginResponse, (await get_profile(access_token, session))
        )

        profile["access_token"] = account_request["access_token"]
        profile["refresh_token"] = token_request["refresh_token"]

        return profile
