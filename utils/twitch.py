import asyncio

import aiohttp

from .logger import Logger


class Twitch:
    def __init__(self, logger: "Logger"):
        self.logger = logger

    def getStreamers(self, client_id: str, client_secret: str) -> list:
        return asyncio.run(self._getStreamers(client_id, client_secret))

    async def _getStreamers(self, client_id: str, client_secret: str) -> list:
        """Return a list of streamers that are live playing Minecraft

        Args:
            client_id (str): Twitch client ID
            client_secret (str): Twitch client secret

        Returns:
            list: List of streamers that are live
        """

        # get access token
        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        }

        try:
            response = await aiohttp.ClientSession().post(url, params=params)
            response.raise_for_status()
        except aiohttp.ClientResponseError as e:
            if str(e).startswith("400"):
                self.logger.error("[twitch.getStreamers] Invalid client ID or client secret")
            else:
                self.logger.error(f"[twitch.getStreamers] {e}")
            return []
        else:
            self.logger.print("[twitch.getStreamers] Got access token")

        access_token = (await response.json())["access_token"]

        url = "https://api.twitch.tv/helix/streams"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Client-Id": client_id,
        }
        url += "?game_id=27471&first=100&type=live"

        try:
            response = await aiohttp.ClientSession().get(url, headers=headers)
            response.raise_for_status()
        except aiohttp.ClientResponseError as e:
            self.logger.error(f"[twitch.getStreamers] {e}")
            return []
        else:
            self.logger.print(f"[twitch.getStreamers] {len((await response.json())['data'])} streamers are live")

        streamers = []
        for stream in (await response.json())["data"]:
            streamers.append({
                "name": stream["user_name"],
                "title": stream["title"],
                "viewer_count": stream["viewer_count"],
                "url": f"https://twitch.tv/{stream['user_name']}?tt_content=live_view_card",
            })

        return streamers
