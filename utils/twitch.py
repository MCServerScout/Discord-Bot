import aiohttp

from .logger import Logger


class Twitch:
    def __init__(self, logger: "Logger", client_id: str, client_secret: str):
        self.logger = logger
        self.client_id = client_id
        self.client_secret = client_secret

    async def asyncGetStreamers(
        self, client_id: str, client_secret: str, lang: str = None
    ) -> list:
        token_url = "https://id.twitch.tv/oauth2/token"
        streams_url = "https://api.twitch.tv/helix/streams"

        if self.client_id is not None:
            client_id = self.client_id
        if self.client_secret is not None:
            client_secret = self.client_secret

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
        headers = {"Client-ID": client_id,
                   "Authorization": f"Bearer {access_token}"}
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

    async def getStream(self, user: str) -> dict:
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

            self.logger.info(
                f"[twitch.getStream] Found stream: {stream['user_name']} - {stream['title']}"
            )
            stream = {
                "name": stream["user_login"],
                "viewer_count": stream["viewer_count"],
                "title": stream["title"],
                "url": f"https://twitch.tv/{stream['user_login']}",
                "thumbnail_url": stream["thumbnail_url"]
                .replace("{width}", "320")
                .replace("{height}", "180"),
            }

        return stream
