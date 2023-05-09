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


## Commands

### Find

`/find <filter>:<value>`

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


## Filters

* `version` - The version of the server either as a name like `1.16.5` or as an id like `754`
* `max_players` - The maximum number of players the server can hold
* `online_players` - The number of players currently online
* `logged_players` - The number of players that have logged into the server
* `player` - The name or uuid of a player that has logged into the server either as an uuid or name
* `sign` - The text on a sign
* `description` - The text in the description of the server matched via RegEx
* `cracked` - Whether the server is cracked
* `has_favicon` - Whether the server has a favicon


## Documents

The docs are in the following json format:

```json
{
  "_id": {
    "$oid": "1534978d9f542e403cfa5026"
  },
  "description": {
    "extra": [
      {
        "color": "white",
        "text": "A Minecraft Server"
      }
    ],
    "text": ""
  },
  "enforcesSecureChat": null,
  "hasFavicon": false,
  "hasForgeData": true,
  "ip": "127.0.0.1",
  "lastSeen": 1682995170,
  "cracked": false,
  "players": {
    "max": 20,
    "online": 1,
    "sample": [
      {
        "id": "c0a80001-0000-0000-0000-000000000000",
        "name": "Player"
      }
    ]
  },
  "port": 25567,
  "version": {
    "name": "1.16.5",
    "protocol": 754
  }
}
```

## Credits

* Pilot1782 - Creator

## Legal

This project is licensed under the GNU Affero General Public License v3.0. See the [LICENSE](LICENSE.md) file for more

[Terms of service](TOS.md)

[Privacy Policy](PRIVACY.md)
