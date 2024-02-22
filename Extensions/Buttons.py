import asyncio
import datetime
import time
import traceback
from threading import Timer

import sentry_sdk
from interactions import (
    Extension,
    component_callback,
    ComponentContext,
    File,
    ShortText,
    Modal,
    StringSelectMenu,
    StringSelectOption,
    ActionRow,
    Button,
    ButtonStyle,
)
from interactions.client.utils import (
    ansi_block,
    ansi_format,
    AnsiColors,
)
from interactions.ext.paginators import Paginator
# noinspection PyProtectedMember
from sentry_sdk import trace, set_tag

from .Colors import *  # skipcq: PYL-W0614

verify_cache = {}


class TimedCache(dict):
    def __init__(self, *_, timeout=60, **kwargs):
        """
        A dict that deletes itself after a certain amount of time
        The timeout resets after every setitem

        :param timeout: The amount of time in seconds before the dict deletes itself
        """
        super().__init__(**kwargs)
        self.timeout_end = time.perf_counter() + timeout
        self.timeout = timeout

        self.loop = None

        self.timer = Timer(timeout, self.__del__)

        self.timer.start()

    def __del__(self):
        self.timer.cancel()
        self.timer = None
        self.clear()

    def __reset_timeout(self):
        self.timer.cancel()

        self.timeout_end = time.perf_counter() + self.timeout
        self.timer = Timer(self.timeout, self.__del__)
        self.timer.start()

    def __setitem__(self, key, value):
        assert self.timer is not None, "This cache has been deleted"
        super().__setitem__(key, value)
        self.__reset_timeout()

    def __getitem__(self, key):
        assert self.timer is not None, "This cache has been deleted"
        try:
            return super().__getitem__(key)
        except KeyError:
            return None


class Buttons(Extension):
    def __init__(
        self,
        *_,
        mcLib,
        messageLib,
        playerLib,
        logger,
        databaseLib,
        serverLib,
        twitchLib,
        Scanner,
        textLib,
        cstats,
        azure_client_id,
        azure_redirect_uri,
        **__,
    ):
        super().__init__()

        self.mcLib = mcLib
        self.messageLib = messageLib
        self.playerLib = playerLib
        self.logger = logger
        self.databaseLib = databaseLib
        self.serverLib = serverLib
        self.twitchLib = twitchLib
        self.Scanner = Scanner
        self.textLib = textLib
        self.cstats = cstats
        self.azure_client_id = azure_client_id
        self.azure_redirect_uri = azure_redirect_uri

    # button to get the next page of servers
    @component_callback("next")
    @trace
    async def next_page(self, ctx: ComponentContext):
        msg = None
        try:
            org = ctx.message

            index, pipeline = await self.messageLib.get_pipe(org)

            await ctx.defer(edit_origin=True)

            self.logger.print("next page called")

            msg = await ctx.edit_origin(
                embed=self.messageLib.standard_embed(
                    title="Loading...",
                    description="Loading...",
                    color=BLUE,
                ),
                components=self.messageLib.buttons(),
                file=File(file="assets/loading.png", file_name="favicon.png"),
            )

            # get the pipeline and index from the message
            total = self.databaseLib.count(pipeline)
            if index + 1 >= total:
                index = 0
            else:
                index += 1

            msg = await msg.edit(
                embed=self.messageLib.standard_embed(
                    title="Loading...",
                    description=f"Loading server {index + 1} of {total}",
                    color=BLUE,
                ),
                components=self.messageLib.buttons(),
                file=None,
            )

            await self.messageLib.async_load_server(
                index=index,
                pipeline=pipeline,
                msg=msg,
            )
        except Exception as err:
            if "403|Forbidden" in str(err):
                await msg.delete(context=ctx)
                return

            self.logger.error(f"Error: {err}\nFull traceback: {traceback.format_exc()}")
            sentry_sdk.capture_exception(err)

            await ctx.send(
                embed=self.messageLib.standard_embed(
                    title="Error",
                    description="An error occurred while trying to get the next page of servers",
                    color=RED,
                ),
                ephemeral=True,
            )

    # button to get the previous page of servers
    @component_callback("previous")
    @trace
    async def previous_page(self, ctx: ComponentContext):
        msg = None
        try:
            org = ctx.message
            index, pipeline = await self.messageLib.get_pipe(org)
            await ctx.defer(edit_origin=True)

            self.logger.print("previous page called")

            msg = await ctx.edit_origin(
                embed=self.messageLib.standard_embed(
                    title="Loading...",
                    description="Loading...",
                    color=BLUE,
                ),
                components=self.messageLib.buttons(),
                file=File(file="assets/loading.png", file_name="favicon.png"),
            )

            # get the pipeline and index from the message
            total = self.databaseLib.count(pipeline)
            if index - 1 >= 0:
                index -= 1
            else:
                index = total - 1

            msg = await msg.edit(
                embed=self.messageLib.standard_embed(
                    title="Loading...",
                    description=f"Loading server {index + 1} of {total}",
                    color=BLUE,
                ),
                components=self.messageLib.buttons(),
                file=None,
            )

            await self.messageLib.async_load_server(
                index=index,
                pipeline=pipeline,
                msg=msg,
            )
        except Exception as err:
            if "403|Forbidden" in str(err):
                await msg.delete(context=ctx)
                return

            self.logger.error(f"Error: {err}\nFull traceback: {traceback.format_exc()}")
            sentry_sdk.capture_exception(err)

            await ctx.send(
                embed=self.messageLib.standard_embed(
                    title="Error",
                    description="An error occurred while trying to get the previous page of servers",
                    color=RED,
                ),
                ephemeral=True,
            )

    # button to send the players that are online
    @component_callback("players")
    @trace
    async def players(self, ctx: ComponentContext):
        try:
            org = ctx.message
            host, port = org.embeds[0].title.split(" ")[1].split(":")
            await ctx.defer(ephemeral=True)

            self.logger.print("players called")

            player_list = await self.playerLib.async_player_list(host, port)

            if player_list is None:
                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="Error",
                        description="An error occurred while trying to get the players (server offline?)",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return

            self.logger.print(f"Found {len(player_list)} players")
            set_tag("players", len(player_list))

            player_groups = [
                list(player_list[i : i + 10]) for i in range(0, len(player_list), 10)
            ]

            players = []
            for player_group in player_groups:
                mbd = self.messageLib.standard_embed(
                    title="Players",
                    description=f"Players on page: {len(player_group)}",
                    color=BLUE,
                )
                for player in player_group:
                    title = player.name
                    if player.lastSeen != 0:
                        title += f" ({datetime.datetime.fromtimestamp(player.lastSeen).strftime('%Y-%m-%d %H:%M')})"

                    body = f"UUID: {player.id}"
                    uuid_int = int(player.id.replace("-", ""), 16)

                    validations = (
                        len(player.name) < 16,
                        len(player.id.replace("-", "")) == 32,
                        "§" not in player.name,
                        uuid_int > 0,
                        player.lastSeen != 0,
                    )

                    is_valid = all(validations)
                    if not is_valid:
                        self.logger.debug(f"Valid: {is_valid} {validations}")

                    body = ansi_block(
                        ansi_format(
                            color=(AnsiColors.GREEN if is_valid else AnsiColors.RED),
                        )
                        + body
                    )

                    mbd.add_field(
                        name=title,
                        value=body,
                        inline=False,
                    )
                players.append(mbd)
            self.logger.debug("Total pages: " + str(len(players)))

            pag = Paginator.create_from_embeds(ctx.bot, *players, timeout=60)
            await pag.send(ctx)
        except Exception as err:
            if "403|Forbidden" in str(err):
                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="An error occurred",
                        description="Wrong channel for this bot",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return

            self.logger.error(f"Error: {err}\nFull traceback: {traceback.format_exc()}")
            sentry_sdk.capture_exception(err)

            await ctx.send(
                embed=self.messageLib.standard_embed(
                    title="Error",
                    description="An error occurred while trying to get the players",
                    color=RED,
                ),
                ephemeral=True,
            )

    # button to jump to a specific index
    @component_callback("jump")
    @trace
    async def jump(self, ctx: ComponentContext):
        org = None
        # when pressed should spawn a modal with a text input and then edit the message with the new index
        try:
            org = ctx.message

            self.logger.print("jump called")
            # get the files attached to the message
            index, pipeline = await self.messageLib.get_pipe(org)

            # get the total number of servers
            total = self.databaseLib.count(pipeline)

            # create the text input
            text_input = ShortText(
                label="Jump to index",
                placeholder=f"Enter a number between 1 and {total}",
                min_length=1,
                max_length=len(str(total)),
                custom_id="jump",
                required=True,
            )

            # create a modal
            modal = Modal(
                text_input,
                title="Jump",
            )

            # send the modal
            await ctx.send_modal(modal)

            try:
                # wait for the response
                modal_ctx = await ctx.bot.wait_for_modal(modal=modal, timeout=60)

                # get the response
                index = int(modal_ctx.responses["jump"])

                # check if the index is valid
                if index < 1 or index > total or not str(index).isnumeric():
                    self.logger.warning(f"Invalid index: {index}")
                    await ctx.send(
                        embed=self.messageLib.standard_embed(
                            title="Error",
                            description=f"Invalid index, must be between 1 and {total}",
                            color=RED,
                        ),
                        ephemeral=True,
                    )
                    return
                else:
                    await modal_ctx.send(
                        embed=self.messageLib.standard_embed(
                            title="Success",
                            description=f"Jumping to index {index}",
                            color=GREEN,
                        ),
                        ephemeral=True,
                    )

                # edit the message
                await self.messageLib.async_load_server(
                    index=index - 1,
                    pipeline=pipeline,
                    msg=org,
                )
            except asyncio.TimeoutError:
                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="Error",
                        description="Timed out",
                        color=RED,
                    ),
                    ephemeral=True,
                )
        except Exception as err:
            if "403|Forbidden" in str(err):
                await org.delete(context=ctx)
                return

            self.logger.error(f"Error: {err}\nFull traceback: {traceback.format_exc()}")
            sentry_sdk.capture_exception(err)

            await ctx.send(
                embed=self.messageLib.standard_embed(
                    title="Error",
                    description="An error occurred while trying to jump to a specific index",
                    color=RED,
                ),
                ephemeral=True,
            )

    # button to change the sort method
    @component_callback("sort")
    @trace
    async def sort(self, ctx: ComponentContext):
        try:
            org = ctx.message

            _, pipeline = await self.messageLib.get_pipe(org)

            self.logger.print("sort called")

            # get the pipeline
            self.logger.print(f"pipeline: {pipeline}")

            # send a message with a string menu that express after 60s
            string_menu = StringSelectMenu(
                StringSelectOption(
                    label="Player Count",
                    value="players",
                ),
                StringSelectOption(
                    label="Sample Count",
                    value="sample",
                ),
                StringSelectOption(
                    label="Player Limit",
                    value="limit",
                ),
                StringSelectOption(
                    label="Server Version ID",
                    value="version",
                ),
                StringSelectOption(
                    label="Last scan",
                    value="last_scan",
                ),
                StringSelectOption(
                    label="Random",
                    value="random",
                ),
                placeholder="Sort the servers by...",
                custom_id="sort_method",
                min_values=1,
                max_values=1,
                disabled=False,
            )

            msg = await ctx.send(
                embed=self.messageLib.standard_embed(
                    title="Sort",
                    description="Sort the servers by...",
                    color=BLUE,
                ),
                components=[
                    ActionRow(
                        string_menu,
                    ),
                ],
                ephemeral=True,
            )

            try:
                # wait for the response
                menu = await ctx.bot.wait_for_component(
                    timeout=60, components=string_menu
                )
            except asyncio.TimeoutError:
                await msg.delete(context=ctx)
                return
            else:
                # get the value
                value = menu.ctx.values[0]
                self.logger.print(f"sort method: {value}")
                sort_method = {}
                extra = []  # used to extra that the sort method exists

                match value:
                    case "players":
                        sort_method = {"$sort": {"players.online": -1}}
                        extra = [{"$match": {"players.online": {"$exists": True}}}]
                    case "limit":
                        sort_method = {"$sort": {"players.max": -1}}
                        extra = [{"$match": {"players.max": {"$exists": True}}}]
                    case "sample":
                        sort_method = {"$sort": {"players.sampleSize": -1}}
                        extra = [
                            {
                                "$match": {
                                    "players.sample": {"$elemMatch": {"$exists": True}}
                                }
                            },
                            {
                                "$addFields": {
                                    "sampleSize": {
                                        "$size": {"$ifNull": ["$players.sample", []]}
                                    }
                                }
                            },
                        ]
                    case "version":
                        sort_method = {"$sort": {"version.id": -1}}
                        extra = [{"$match": {"version.id": {"$exists": True}}}]
                    case "last_scan":
                        sort_method = {"$sort": {"lastSeen": -1}}
                    case "random":
                        sort_method = {"$sample": {"size": 1000}}
                    case _:
                        await ctx.send(
                            embed=self.messageLib.standard_embed(
                                title="Error",
                                description="Invalid sort method",
                                color=RED,
                            ),
                            ephemeral=True,
                        )

                await msg.delete(context=ctx)
                msg = await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="Success",
                        description=f"Sorting by `{value}`",
                        color=GREEN,
                    ),
                    ephemeral=True,
                )

                extra.extend(pipeline)
                pipeline = extra

                # loop through the pipeline and replace the sort method
                for i, pipe in enumerate(pipeline):
                    if "$sort" in pipe or "$sample" in pipe:
                        pipeline[i] = sort_method
                        break
                else:
                    pipeline.append(sort_method)

                # loop through the pipeline and remove the limit
                for i, pipe in enumerate(pipeline):
                    if "$limit" in pipe:
                        pipeline.pop(i)
                        break

                # limit to 1k servers
                pipeline.append({"$limit": 1000})

                # edit the message
                await self.messageLib.async_load_server(
                    index=0,
                    pipeline=pipeline,
                    msg=org,
                )

                await msg.delete(context=ctx)
        except AttributeError:
            self.logger.print("AttributeError")
        except Exception as err:
            if "403|Forbidden" in str(err):
                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="An error occurred",
                        description="Wrong channel for this bot",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return

            self.logger.error(f"Error: {err}\nFull traceback: {traceback.format_exc()}")
            sentry_sdk.capture_exception(err)

            await ctx.send(
                embed=self.messageLib.standard_embed(
                    title="Error",
                    description="An error occurred while trying to sort the servers",
                    color=RED,
                ),
                ephemeral=True,
            )

    # button to update the message
    @component_callback("update")
    @trace
    async def update_command(self, ctx: ComponentContext):
        await ctx.send(
            embed=self.messageLib.standard_embed(
                title="Updating...",
                description="Updating...",
                color=BLUE,
            ),
            ephemeral=True,
            delete_after=2,
        )
        await self.messageLib.update(ctx)

    # button to show mods
    @component_callback("mods")
    @trace
    async def mods(self, ctx: ComponentContext):
        mod_list = []
        try:
            org = ctx.message

            index, pipeline = await self.messageLib.get_pipe(org)

            self.logger.print("mods called")

            await ctx.defer(ephemeral=True)

            # get the pipeline
            self.logger.print(f"pipeline: {pipeline}")

            host = self.databaseLib.get_doc_at_index(pipeline, index)

            if "mods" not in host.keys() or "modpackData" not in host.keys():
                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="Error",
                        description="No mods found",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return

            mod_list = (host["mods"] if "mods" in host.keys() else []) + (
                host["modpackData"]["mods"] if "modpackData" in host.keys() else []
            )

            self.logger.debug(f"Found {len(mod_list)} mods")

            # create a paginator
            pages = []
            for mod in mod_list:
                self.logger.print(mod)
                embed = self.messageLib.standard_embed(
                    title=mod["name"],
                    description=f"Version: {mod['version']}\nModID: {mod['id']}\nRequired: {mod['required']}",
                    color=BLUE,
                )
                pages.append(embed)

            if pages:
                pag = Paginator.create_from_embeds(ctx.bot, *pages, timeout=60)
                await pag.send(ctx)
            else:
                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="Error",
                        description="No mods found",
                        color=RED,
                    ),
                    ephemeral=True,
                )
        except KeyError:
            await ctx.send(
                embed=self.messageLib.standard_embed(
                    title="Error",
                    description="No mods found",
                    color=RED,
                ),
                ephemeral=True,
            )

            if mod_list:
                self.logger.debug(f"Mods: {mod_list}")
        except Exception as err:
            if "403|Forbidden" in str(err):
                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="An error occurred",
                        description="Wrong channel for this bot",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return

            self.logger.error(f"Error: {err}\nFull traceback: {traceback.format_exc()}")
            sentry_sdk.capture_exception(err)

            await ctx.send(
                embed=self.messageLib.standard_embed(
                    title="Error",
                    description="An error occurred while trying to get the players",
                    color=RED,
                ),
                ephemeral=True,
            )

    # button to try and join the server
    @component_callback("join")
    @trace
    async def join(self, ctx: ComponentContext):
        self.logger.print("join called.")

        try:
            # step one get the server info
            org = ctx.message

            pipeline = [
                {
                    "$match": {
                        "$and": [
                            {"ip": org.embeds[0].title.split(" ")[1].split(":")[0]},
                            {
                                "port": int(
                                    org.embeds[0].title.split(" ")[1].split(":")[1]
                                )
                            },
                        ],
                    },
                },
            ]

            self.logger.print("join called")

            await ctx.defer(ephemeral=True)

            # get the pipeline
            self.logger.print(f"pipeline: {pipeline}")

            host = self.databaseLib.get_doc_at_index(pipeline, 0)

            if host["lastSeen"] < time.time() - 300:
                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="Error",
                        description="Server might be offline",
                        color=RED,
                    ),
                    ephemeral=True,
                    delete_after=2,
                )

            # step three it's joining time
            # get the activation code url
            url, vCode = self.mcLib.get_activation_code_url(
                clientID=self.azure_client_id, redirect_uri=self.azure_redirect_uri
            )

            verify_cache[str(org.id)] = TimedCache(
                timeout=280,
                **{
                    "vCode": vCode,
                    "org": org,
                    "pipeline": pipeline,
                    "index": 0,
                    "time": time.perf_counter(),
                },
            )

            # send the url
            embed = self.messageLib.standard_embed(
                title="Sign in to Microsoft to join",
                description=f"Open [this link]({url}) to sign in to Microsoft and join the server, then click the `Submit` button below and paste the provided code",
                color=BLUE,
            )
            embed.set_footer(text=f"org_id {str(org.id)}")
            await ctx.send(
                embed=embed,
                components=[
                    Button(
                        label="Submit",
                        custom_id="submit",
                        style=ButtonStyle.DANGER,
                    )
                ],
                ephemeral=True,
                delete_after=240,
            )
        except Exception as err:
            if "403|Forbidden" in str(err):
                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="An error occurred",
                        description="Wrong channel for this bot",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return

            self.logger.error(f"Error: {err}\nFull traceback: {traceback.format_exc()}")
            sentry_sdk.capture_exception(err)

            await ctx.send(
                embed=self.messageLib.standard_embed(
                    title="Error",
                    description="An error occurred while trying to get the players",
                    color=RED,
                ),
                ephemeral=True,
            )

    # button to try and join the server for realziez
    @component_callback("submit")
    @trace
    async def submit(self, ctx: ComponentContext):
        try:
            org = ctx.message
            org_org_id = org.embeds[0].footer.text.split(" ")[1]
            Oorg = ctx.channel.get_message(org_org_id)
            self.logger.print(f"org: {Oorg}")

            self.logger.print("submit called")
            # get the files attached to the message
            cache = verify_cache[str(Oorg.id)]

            if cache == {}:
                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="Error",
                        description="Timed out",
                        color=RED,
                    ),
                    components=[],
                )
                return

            vCode = cache["vCode"]
            pipeline = cache["pipeline"]
            index = cache["index"]

            # create the text input
            text_input = ShortText(
                label="Activation Code",
                placeholder="A.A0_AA0.0.aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                min_length=40,
                max_length=55,
                custom_id="code",
                required=True,
            )

            # create a modal
            modal = Modal(
                text_input,
                title="Activation Code",
            )

            # send the modal
            await ctx.send_modal(modal)

            # wait for the modal to be submitted
            try:
                # wait for the response
                modal_ctx = await ctx.bot.wait_for_modal(modal=modal, timeout=60)

                # get the response
                code = modal_ctx.responses["code"]
            except asyncio.TimeoutError:
                await ctx.edit_origin(
                    embed=self.messageLib.standard_embed(
                        title="Error",
                        description="Timed out",
                        color=RED,
                    ),
                    components=[],
                )
                return
            else:
                await org.delete(context=ctx)
                await modal_ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="Success",
                        description="Code received",
                        color=GREEN,
                    ),
                    ephemeral=True,
                    delete_after=2,
                )

            # try and get the minecraft token
            try:
                res = await self.mcLib.get_minecraft_token_async(
                    clientID=self.azure_client_id,
                    redirect_uri=self.azure_redirect_uri,
                    act_code=code,
                    verify_code=vCode,
                )

                if res["type"] == "error":
                    self.logger.error(f"Error getting token: {res['error']}")
                    await ctx.send(
                        embed=self.messageLib.standard_embed(
                            title="Error",
                            description="An error occurred while trying to get the token",
                            color=RED,
                        ),
                        ephemeral=True,
                    )
                    return
                else:
                    uuid = res["uuid"]
                    name = res["name"]
                    token = res["minecraft_token"]

                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="Joining...",
                        description=f"Joining the server with the player:\nName: {name}\nUUID: {uuid}",
                        color=BLUE,
                    ),
                    ephemeral=True,
                    delete_after=2,
                )
            except Exception as err:
                self.logger.error(
                    f"Error: {err}\nFull traceback: {traceback.format_exc()}"
                )
                sentry_sdk.capture_exception(err)

                await ctx.send(
                    embed=self.messageLib.standard_embed(
                        title="Error",
                        description="An error occurred while trying to get the token",
                        color=RED,
                    ),
                    ephemeral=True,
                )
                return

            # try and join the server
            host = self.databaseLib.get_doc_at_index(pipeline, index)
            ServerType = self.mcLib.ServerType

            res: ServerType = await self.mcLib.join(
                ip=host["ip"],
                port=host["port"],
                player_username=name,
                version=host["version"]["protocol"],
                mine_token=token,
            )

            await ctx.send(
                embed=self.messageLib.standard_embed(
                    title="Done!",
                    description="The server was of type: " + str(res.status),
                    color=GREEN,
                ),
                ephemeral=True,
            )
        except Exception as err:
            self.logger.error(f"Error: {err}\nFull traceback: {traceback.format_exc()}")
            sentry_sdk.capture_exception(err)

            await ctx.send(
                embed=self.messageLib.standard_embed(
                    title="Error",
                    description="An error occurred while trying to join the server",
                    color=RED,
                ),
                components=[],
                ephemeral=True,
            )

    # button to show streams
    @component_callback("streams")
    @trace
    async def streams(self, ctx: ComponentContext):
        # get the pipeline
        org = ctx.message
        index, pipeline = await self.messageLib.get_pipe(org)

        self.logger.print("streams called")

        await ctx.defer(ephemeral=True)

        data = self.databaseLib.get_doc_at_index(pipeline, index)

        streams = []
        raw_streams = await self.twitchLib.async_get_streamers()

        users_streaming: list[str] = [i["user_name"] for i in raw_streams]
        server_players = [player["name"] for player in data["players"]["sample"]]

        streaming_players = list(
            set(server_players)
            - set(users_streaming).symmetric_difference(set(server_players))
        )
        self.logger.debug(f"Found {len(streaming_players)} streams in server")

        for player in streaming_players:
            stream = raw_streams[users_streaming.index(player)]
            if stream is not None and stream not in streams:
                streams.append(
                    f"{stream['user_name']}: [{stream['title']}](https://twitch.tv/{stream['user_login']})"
                )

            if len(streams) >= len(users_streaming):
                # already added all the streams
                break

        if len(streams) == 0:
            await ctx.send(
                embed=self.messageLib.standard_embed(
                    title="No Streams",
                    description="No active streams found, if this is incorrect please try again in a few minutes",
                    color=RED,
                ),
                ephemeral=True,
            )
            return

        pag = Paginator.create_from_list(ctx.bot, streams, timeout=60)

        await pag.send(ctx)
