# Server Scout (Discord Bot)

[![DeepSource](https://app.deepsource.com/gh/MCServerScout/Discord-Bot.svg/?label=resolved+issues&show_trend=true&token=WBeh3kT2daCAxLlfI8PhPJsD)](https://app.deepsource.com/gh/MCServerScout/Discord-Bot/?ref=repository-badge)
[![Qodana](https://github.com/MCServerScout/Discord-Bot/actions/workflows/code_quality.yml/badge.svg)](https://github.com/MCServerScout/Discord-Bot/actions/workflows/code_quality.yml)

This is a Discord bot that I made for my friends and me to use in our Discord server.
It is a work in progress, and I will be adding more features as time goes on.

## TODO

- [ ] Make it work well
- [ ] Make streamers only get servers with a player sample
- [ ] Make streamers more consistent
- [ ] Auto merge dev-builds into master every monday

## Commands

<details>
<summary>Click to show all commands</summary>

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

</details>

## Filters

* `ip` - An ip range in the subnet mask format like `127.0.0.0/32`
* `version` - The version of the server either as a name like `1.16.5` or as an id like `754`
* `max_players` - The maximum number of players the server can hold
* `online_players` - The number of players currently online
* `logged_players` - The number of players that have logged into the server
* `player` - The name or uuid of a player that has logged into the server either as an uuid or name
* `sign` - The text on a sign
* `description` - The text in the description of the server matched via RegEx
* `cracked` - Whether the server is cracked
* `has_favicon` - Whether the server has a favicon
* `country` - The country the server is in

## Documents

The docs are in the following json format:

<details>
  <summary>Click to show example doc</summary>

  ```json
  {
  "_id": {
    "$oid": "1534978d9f542e403cfa5026"
  },
  "description": {
    "text": "A Minecraft Server"
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
        "name": "Player",
        "lastSeen": 1234567890
      }
    ]
  },
  "port": 25567,
  "version": {
    "name": "1.16.5",
    "protocol": 754
  },
  "modpackData": {},
  "preventsChatReports": false,
  "previewsChat": false,
  "forgeData": {},
  "geo": {
    "lat": 0,
    "lon": 0,
    "city": "",
    "country": "",
    "hostname": ""
  }
}
  ```

</details>

## Legal

This project is licensed under the GNU Affero General Public License v3.0. See the [LICENSE](LICENSE) file for more

[Terms of service](TOS.md)

[Privacy Policy](PRIVACY.md)

## Q/A

* Am I sus?
  * Maybe
