# About

This contains an overview on how the login protocol for minecraft works.

# Prerequisites

## Azure

- Create an azure AD application and save the client id and client secret for
  later [docs](https://learn.microsoft.com/en-us/azure/active-directory/develop/quickstart-register-app)
- start a local webserver that will receive the redirect from the azure login
  page and save the redirect url for later
  - add this url to the list of redirect urls in the azure portal

# Logging in

1. Getting a minecraft token

To get your token, you need to follow these steps:

A. Create a url with the following information substituting and field in brackets, ex: {client_id} ->
1234-1234-1234-1234

```http request
GET https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize

?=client_id={client_id}
&response_type=code
&redirect_uri={redirect_uri}
&response_mode=query
&scope=XboxLive.signin
```

B. Open the url in a browser and login with your microsoft account

this will redirect you to `{redirect_uri}?code={code}`

Ex: `http://localhost:8080/?code=1234-1234-1234-1234`

C. From your webserver that the redirect uri goes to, save the code from the query

D. Make a POST request to redeem for an access token:

```http request
POST https://login.microsoftonline.com/consumers/oauth2/v2.0/token

{
    "client_id": {client_id},
    "scope": XboxLive.signin,
    "code": {code},
    "redirect_uri": {redirect_uri},
    "grant_type": authorization_code,
    "client_secret": {client_secret}
}
```

E. Save the access token from the response

Ex:

```json
{
  "access_token": "...",
  "token_type": "Bearer",
  "expires_in": 3599,
  "scope": "XboxLive.signin",
  "refresh_token": "...",
  "id_token": "..."
}
```

F. Get an xbox live token (POST)

```http request
POST https://user.auth.xboxlive.com/user/authenticate

{
  "Properties": {
    "AuthMethod": "RPS",
    "SiteName": "user.auth.xboxlive.com",
    "RpsTicket": "d={access_token}"
  },
  "RelyingParty": "http://auth.xboxlive.com",
  "TokenType": "JWT"
}
```

Header:

```json
{
  "Content-Type": "application/json",
  "Accept": "application/json"
}
```

G. Save the token from the response

Ex:

```json
{
  "IssueInstant": "2020-10-10T00:00:00.0000000Z",
  "NotAfter": "2020-10-10T00:00:00.0000000Z",
  "Token": "...",
  "DisplayClaims": {
    "xui": [
      {
        "uhs": "..."
      }
    ]
  }
}
```

H. Get an xtxs live token (POST)

```http request
POST https://xsts.auth.xboxlive.com/xsts/authorize

{
  "Properties": {
    "SandboxId": "RETAIL",
    "UserTokens": [
      "{xbox_live_token}"
    ]
  },
  "RelyingParty": "rp://api.minecraftservices.com/",
  "TokenType": "JWT"
}
```

Header:

```json
{
  "Content-Type": "application/json",
  "Accept": "application/json"
}
```

I. Save the token from the response

Ex:

```json
{
  "IssueInstant": "2020-10-10T00:00:00.0000000Z",
  "NotAfter": "2020-10-10T00:00:00.0000000Z",
  "Token": "...",
  "DisplayClaims": {
    "xui": [
      {
        "uhs": "..."
      }
    ]
  }
}
```

J. Get a minecraft token (POST)

```http request
POST https://api.minecraftservices.com/authentication/login_with_xbox

{
  "identityToken": "XBL3.0 x={xbox_live_token}"
}
```

K. Save the token from the response

Ex:

```json
{
  "username": "...",
  "roles": [],
  "access_token": "...",
  "token_type": "Bearer",
  "expires_in": 86399
}
```

L. **OPTIONAL** Check ownership of minecraft (GET)

```http request
GET https://api.minecraftservices.com/entitlements/mcstore
```

Header:

```json
{
  "Authorization": "Bearer {minecraft_token}",
  "Content-Type": "application/json"
}
```

M. **OPTIONAL** Save the response

Ex:

```json
{
  "items": [
    {
      "name": "product_minecraft",
      "signature": "jwt sig"
    },
    {
      "name": "game_minecraft",
      "signature": "jwt sig"
    }
  ]
}
```

2. Getting a minecraft profile

A. Get the profile (GET)

```http request
GET https://api.minecraftservices.com/minecraft/profile
```

Header:

```json
{
  "Authorization": "Bearer {minecraft_token}",
  "Content-Type": "application/json"
}
```

B. Save the response

Ex:

```json
{
  "id": "...",
  "name": "...",
  "skins": [
    {
      "id": "...",
      "state": "ACTIVE",
      "url": "https://texture.minecraft.net/texture/...",
      "variant": "CLASSIC"
    }
  ],
  "capes": [
    {
      "id": "...",
      "state": "ACTIVE",
      "url": "https://texture.minecraft.net/texture/..."
    }
  ]
}
```

3. Start sending packets to the server

A. Handshake (0x00) C->S

```
0x00       ID
47         Protocol Version
localhost  Server Address
25565      Server Port
2          Next State
```

B. Login Start (0x00) C->S

```
0x00        ID
12          Username Length
{username}  Username
```

C. Listen for response S->C

- 0x00: Disconnect
  - Ex: `0x0016{"text":"Disconnected","translate":"disconnect.loginFailedInfo"}`
  - reason is provided as a string in the packet
- 0x01: Encryption Request
  - Ex: `0x010"server id"10"public key (bytes)"10"verify token (bytes)"`
  - serverId is a string (this should be empty)
  - publicKey is a byte array
  - verifyToken is a byte array
- 0x02: Login Success
  - Ex: `0x020"uuid"10"username"...`
  - uuid is a string
  - username is a string
  - THis indicates that the server is 'cracked' and allows non-premium accounts to join
- 0x03: Set Compression
  - Ex: `0x031234`
  - threshold is an integer
  - This indicates that the server will start compressing packets
- 0x...
  - The server responded with an invalid packet id and might be a honeypot

D. Send Authentication request (0x01) C->...

- First create an array of 16 random bytes (shared secret)
- Then create your verify hash:

```python
from hashlib import sha1

server_id = ...
shared_secret = ...
public_key = ...

shaHash = sha1()
shaHash.update(server_id)
shaHash.update(shared_secret)
shaHash.update(public_key)
verify_hash = shaHash.hexdigest()
```

- Now make a POST request to the following url:

```
https://sessionserver.mojang.com/session/minecraft/join
```

```json
{
  "accessToken": "{minecraft_token}",
  "selectedProfile": "{uuid without dashes}",
  "serverId": "{verify hash}"
}
```

E. Listen for response ...->C

- 204: Success
  - This indicates that the server has accepted your login, and you can now send the encryption packets
- 403: Invalid Session
  - This indicates that the server has rejected your login as you don't have a multiplayer or are banned from
    multiplayer
- 503: Service Unavailable
  - This indicates that the server is down or is not accepting logins, try again after a few seconds

F. Send Encryption Response (0x01) C->S

At this point, encrypt the shared secret and verify token with the public key

```
0x01             ID
10               Shared Secret Length
{shared_secret}  Shared Secret
10               Verify Token Length
{verify_token}  Verify Token
```

G. Listen for response S->C

- 0x00: Disconnect
  - Ex: `0x0016{"text":"Disconnected","translate":"disconnect.loginFailedInfo"}`
  - reason is provided as a string in the packet
- 0x03: Set Compression
  - Ex: `0x031234`
  - threshold is an integer
  - This indicates that the server will start compressing packets
- 0x02: Login Success
  - Ex: `0x020"uuid"10"username"...`
  - uuid is a string
  - username is a string
  - This indicates that the server has accepted your login, and you can now send the encryption packets
- 0x04: Load Plugin
  - Ex: `0x04"channel"10"plugin data"`
  - channel is a string
  - plugin data is a byte array
  - Respond with:

```
0x02  ID
5     Message ID from request
1     Successful
```

- 0x... > 50: Play packet
  - The server responded with a packet that might be out of order, ignore and listen again
- 0x... <= 50: Play packet
  - The server responded with a valid packet, and you can now start sending packets to the server
- 0x... < 0: Invalid Packet
  - This is a honeypot and you should disconnect
  - You can also usually tell by checking the players listed in the sample, as they are usually fake

# Full overview

- [X] Client connects to the server
- [X] C→S: Handshake State=2
- [X] C→S: Login Start
- [X] S→C: Encryption Request
- [X] Client auth
- [X] C→S: Encryption Response
- [X] Server auth, both enable encryption
- [X] S → C: Set Compression (Optional, enables compression)
- [X] S → C: Login Success
- [ ] C → S: Login Acknowledged
- [ ] S → C: Login (play)
- [ ] S → C: Plugin Message: minecraft:brand with the server's brand (Optional)
- [ ] S → C: Change Difficulty (Optional)
- [ ] S → C: Player Abilities (Optional)
- [ ] C → S: Plugin Message: minecraft:brand with the client's brand (Optional)
- [ ] C → S: Client Information
- [ ] S → C: Set Held Item
- [ ] S → C: Update Recipes
- [ ] S → C: Update Tags
- [ ] S → C: Entity Event (for the OP permission level; see Entity statuses#Player)
- [ ] S → C: Commands
- [ ] S → C: Recipe
- [ ] S → C: Player Position
- [ ] S → C: Player Info (Add Player action)
- [ ] S → C: Player Info (Update latency action)
- [ ] S → C: Set Center Chunk
- [ ] S → C: Light Update (One sent for each chunk in a square centered on the player's position)
- [ ] S → C: Chunk Data and Update Light (One sent for each chunk in a square centered on the player's position)
- [ ] S → C: Initialize World Border (Once the world is finished loading)
- [ ] S → C: Set Default Spawn Position (“home” spawn, not where the client will spawn on login)
- [ ] S → C: Synchronize Player Position (Required, tells the client they're ready to spawn)
- [ ] C → S: Confirm Teleportation
- [ ] C → S: Set Player Position and Rotation (to confirm the spawn position)
- [ ] C → S: Client Command (sent either before or while receiving chunks, further testing needed, server handles
  correctly if not sent)
- [ ] S → C: inventory, entities, etc
