import time
from itertools import zip_longest

import aiohttp

from .logger import Logger


class Twitch:
    def __init__(self, logger: "Logger", client_id: str, client_secret: str):
        self.logger = logger
        self.client_id = client_id
        self.client_secret = client_secret

    async def async_get_streamers(
        self, client_id: str = None, client_secret: str = None, lang: str = None
    ) -> list:
        """
        Get a list of Minecraft streamers

        :param client_id: The Twitch client ID
        :param client_secret: The Twitch client secret
        :param lang: The language to filter by

        :return: A list of Minecraft streamers
        """

        token_url = "https://id.twitch.tv/oauth2/token"
        streams_url = "https://api.twitch.tv/helix/streams"

        if self.client_id is not None:
            client_id = self.client_id
        if self.client_secret is not None:
            client_secret = self.client_secret

        if client_id is None or client_secret is None:
            self.logger.error(
                "[twitch.asyncGetStreamers] Client ID or secret not provided"
            )
            return []

        # Get access token
        async with aiohttp.ClientSession() as session:
            params = {
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            }
            async with session.post(token_url, params=params) as response:
                token_data = await response.json()
                access_token = token_data["access_token"]

        # Fetch Minecraft streams
        headers = {"Client-ID": client_id, "Authorization": f"Bearer {access_token}"}
        params = {
            "game_id": "27471",
            "first": 100,
            "type": "live",
        }
        if lang:
            params["language"] = lang

        async with aiohttp.ClientSession() as session, session.get(
            streams_url, headers=headers, params=params
        ) as response:
            data = await response.json()
            self.logger.info(
                f"[twitch.asyncGetStreamers] Fetched {len(data['data'])} Minecraft streams"
            )

        # Process stream data
        if "data" in data:
            return data["data"]

        return []

    async def get_stream(self, user: str) -> dict:
        """
        Get a stream

        :param user: The user to get the stream of

        :return: The stream data
        """
        start = time.perf_counter()

        # Get access token
        token_url = "https://id.twitch.tv/oauth2/token"
        streams_url = "https://api.twitch.tv/helix/streams"

        async with aiohttp.ClientSession() as session:
            params = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            }
            async with session.post(token_url, params=params) as response:
                token_data = await response.json()
                access_token = token_data["access_token"]

        # Fetch stream
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {access_token}",
        }
        params = {
            "user_login": user,
            "type": "live",
        }

        async with aiohttp.ClientSession() as session, session.get(
            streams_url, headers=headers, params=params
        ) as response:
            data = await response.json()

        # Process stream data
        stream = {}
        if "data" in data:
            stream = data["data"][0] if len(data["data"]) > 0 else {}
            if stream == {}:
                return stream

            self.logger.info(f"Found stream: {stream['user_name']} - {stream['title']}")
            stream = {
                "name": stream["user_login"],
                "viewer_count": stream["viewer_count"],
                "title": stream["title"],
                "url": f"https://twitch.tv/{stream['user_login']}",
                "thumbnail_url": stream["thumbnail_url"]
                .replace("{width}", "320")
                .replace("{height}", "180"),
            }

        end = time.perf_counter()
        self.logger.debug(f"Took {end - start:0.4f} seconds")

        return stream

    async def get_users_streaming(self) -> list[str]:
        streamers = await self.async_get_streamers(self.client_id, self.client_secret)
        return [streamer["user_name"] for streamer in streamers]

    async def is_twitch_user(self, *users: str) -> bool:
        """
        Check if a user is a Twitch user

        :param users: The users to check

        :return: Whether the user is a Twitch user
        """
        out = []

        # Get access token
        token_url = "https://id.twitch.tv/oauth2/token"
        users_url = "https://api.twitch.tv/helix/users"

        async with aiohttp.ClientSession() as session:
            params = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            }
            async with session.post(token_url, params=params) as response:
                token_data = await response.json()
                access_token = token_data["access_token"]

        for group in zip_longest(*[iter(users)] * 100):
            # Fetch user
            headers = {
                "Client-ID": self.client_id,
                "Authorization": f"Bearer {access_token}",
            }
            params = "?" + "&".join([f"login={user}" if user else "" for user in group])

            async with aiohttp.ClientSession() as session, session.get(
                users_url + params, headers=headers
            ) as response:
                data = await response.json()

            if "data" in data:
                for user in data["data"]:
                    out.append(bool(user))

        return out
