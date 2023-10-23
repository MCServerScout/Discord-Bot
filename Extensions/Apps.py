from interactions import Extension, message_context_menu, ContextMenuContext

from .Colors import *  # skipcq: PYL-W0614


class Apps(Extension):
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

    @message_context_menu(name="Refresh")
    async def refresh(self, ctx: ContextMenuContext):
        """
        Args:
            ctx: Pre given context for an app menu

        Returns:
            None
        """
        await ctx.defer(ephemeral=True)
        if ctx.target is None or ctx.target.embeds is None:
            await ctx.send(
                embed=self.messageLib.standard_embed(
                    title="Error",
                    description="This message does not have an embed",
                    color=RED,
                ),
                ephemeral=True,
            )
        else:
            self.logger.print(
                f"Found {len(ctx.target.attachments)} embeds in message {ctx.target.id}: {ctx.target.attachments}"
            )
            # run the update command
            await self.messageLib.update(ctx)
            await ctx.send(
                embed=self.messageLib.standard_embed(
                    title="Success",
                    description="Updated the embed",
                    color=GREEN,
                ),
                ephemeral=True,
                delete_after=2,
            )
