# Setting up a mongodb database

## Prerequisites

- Choose if you want to host a database yourself or use a cloud service

## Using a cloud service (Atlas) (recommended)

1. [Register here](https://www.mongodb.com/cloud/atlas/register)
2. You will be prompted to create a 'cluster,' choose the free tier
3. For an authentication method, choose 'Username/Password,' copy the password and select 'Create User'
4. In the connection, choose 'My Local environment' and click 'Add Your Current IP Address'
5. Now select 'Finish and Close'
6. Now on the left side, select 'Database'
7. Wait for the database to load and select 'Browse Collections'
8. Select 'Add My Own Data'
9. For database name, enter 'MCSS'
10. For collection name enter 'scannedServers'
11. Now select 'Create'
12. On the left, select 'Database' again
13. Now select 'Connect'
14. Select 'Drivers' -> 'Python' -> '3.12 or later'
15. Scroll down and copy the connection string
    ex: `mongodb+srv://pilot1782:Hunter2@mongo.com/test?retryWrites=true&w=majority`
16. Now paste the connection string into the `MONGO_URL` variable in `privVars.py`

## Hosting a database yourself

1. Follow [this guide](https://www.prisma.io/dataguide/mongodb/setting-up-a-local-mongodb-database)
2. Open the cli to mongosh
3. Run `use MCSS` to create the MCSS database
4. Run `db.createCollection("scannedServers")` to create the scannedServers collection
5. Now paste the connection string into the `MONGO_URL` variable in `privVars.py`
