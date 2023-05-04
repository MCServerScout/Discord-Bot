# Dollar Tree Copenheimer (Discord Bot)

This is a Discord bot that I made for my friends and I to use in our Discord server. It is a work in progress, and I
will be adding more features as time goes on.

## TODO

- [X] Access a database of the servers
- [X] Have filters to sort through
- [X] Sort through the servers
  - [X] players online
  - [X] max players
  - [X] version id
  - [X] random
- [X] Get info about a selected server
- [X] Get a player list
- [ ] Make it work well

- Filters
  - Version, name or id
  - Player count
  - Player limit
  - Player by name or uuid
  - Sign text
  - Motd
  - Cracked

----

## Commands

### Find

`/find <filter> <value>`

This command will find a server based on the filter and value you give it.
You can use multiple filters at once, and the bot will find a server that matches all of them.

### Stats

`/stats`

This command gives stats about the database

### Streamers

`/streamers`

This command will show you a list of all the streamers that are currently streaming on a server in the database.

### Ping

`/ping`

This command will show you information about a provided server.

### Help

`/help`

This command will show you a list of all the commands and how to use them.