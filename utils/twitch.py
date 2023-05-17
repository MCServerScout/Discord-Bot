import aiohttp

from .logger import Logger


class Twitch:
    def __init__(self, logger: "Logger"):
        self.logger = logger

    async def asyncGetStreamers(self, client_id: str, client_secret: str) -> list:
        token_url = "https://id.twitch.tv/oauth2/token"
        streams_url = "https://api.twitch.tv/helix/streams"

        # Get access token
        async with aiohttp.ClientSession() as session:
            params = {
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials"
            }
            async with session.post(token_url, params=params) as response:
                token_data = await response.json()
                access_token = token_data["access_token"]

        # Fetch Minecraft streams
        headers = {
            "Client-ID": client_id,
            "Authorization": f"Bearer {access_token}"
        }
        params = {
            "game_id": "27471",
            "first": 100,
            "type": "live"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(streams_url, headers=headers, params=params) as response:
                data = await response.json()

        # Process stream data
        minecraft_streams = []
        if "data" in data:
            for stream in data["data"]:
                self.logger.info(
                    f"Found Minecraft stream: {stream['user_name']} ({stream['viewer_count']} viewers) - {stream['title']}")
                streamer = {
                    "name": stream["user_name"],
                    "viewer_count": stream["viewer_count"],
                    "title": stream["title"],
                    "url": f"https://twitch.tv/{stream['user_name']}"
                }
                minecraft_streams.append(streamer)

        return minecraft_streams
