# Prerequisites

* Python>=3.10
* linux (for the botHandler)
* Pre-setup database, instructions can be found [here](database_setup.md)
* Read and understand the [Terms Of Service](https://github.com/MCServerScout/Discord-Bot/blob/master/TOS.md)
* Read and understand the [Privacy Policy](https://github.com/MCServerScout/Discord-Bot/blob/master/PRIVACY.md)

# Automatic Setup

1. Download the file
   named `botHandler` [HERE](https://raw.githubusercontent.com/MCServerScout/Discord-Bot/master/botHandler.pyw)
2. Make your file so that `botHandler.pyw` and `privVars.py` are in the same folder:

```
folderNameHere
│   botHandler.pyw
│   privVars.py
│
└───Discord-Bot
```

3. Create and edit a file named ```privVars.py``` and paste the following text:

```python
# Base Settings (Required)
DISCORD_TOKEN = (
    "Very Secret Token"
)
MONGO_URL = "mongodb://pilot1782:Hunter2@127.0.0.1:27017"

# Database settings
# db_name = "MCSS"
# col_name = "scannedServers"

# DISCORD_WEBHOOK = "..."
# Twitch API settings
# client_id = "..."
# client_secret = "..."
# IPInfo API settings
# IP_INFO_TOKEN = "..."

# Debug settings
# DEBUG = False

# scanner settings
# max_threads = 10
# max_pps = 3000

# fun settings
# cstats = "..."

# Azure AD settings
# azure_client_id = "..."
# azure_redirect_uri = "..."

# error logging
# SENTRY_TOKEN = "..."

# SENTRY_URI = "..."

# handler settings
# dev = True
# target = "scanner"
# autoupdate = True
```

4. Edit the variables such that they contain the correct information.

- Any Variables that are commented out are not required but are recommended for full functionality

5. Run the file `botHandler.pyw` via `python3 botHandler.pyw`

# Manual Setup

1. Clone the repo or download the zip file
2. Run the script 'setup.py' with the following command:

```shell
python3 setup.py
```

## Note:

The command for python might be under a different name, here are the most common names if `python3` doesn't work:

- `python`
- `py`
- `py3`

4. Open the file `setup.py` and edit the variables that have `...` as their value to the correct values

# Running the bot

## Continuous

* Run the file `botHandler.py`

## Once

* Run the file `main.pyw`

# `privVars.py` Additional settings

## General

* `DEBUG = False`
  * Whether to use debugging in the log, this will add a lot more to the log file and can be used if you have issues.
* `cstats: str`
  * Adds a custom field to the stats message

## Database

* `db_name = "MCSS"`
  * The name of the cluster
* `col_name = "scannedServers`
  * The name of the collection

## Twitch API

* Twitch settings, these are not required but add more functionality to the bot
  * `client_id: str`
  * `client_secret: str`

## [IPInfo](https://ipinfo.io) API

* `IP_INFO_TOKEN: str`
  * The token from `ipinfo.io` for location gathering

## Scanner

* `max_threads = 10`
  * Determines the maximum number of threads the scanner can use
* `max_pps = 1000`
  * Determines the maximum number of pings the scanner can send

## Azure Application

* `azure_client_id: str`
* `azure_redirect_uri: str`
  * Both of these are copied from an azure application and are needed to use the `Join` functionality

## Sentry API

* `SENTRY_TOKEN: str`
* `SENTRY_URI: str`
  * Used for implementing error tracking with [Sentry](https://sentry.io)

## Handler

* `dev: bool`
  * Whether or not to use the dev branch instead of the master branch
* `target: str = "scanner" | "bot" | "rescanner"`
  * What the handler should launch
* `autoupdate: bool`
  * Should the handler keep itself up to date