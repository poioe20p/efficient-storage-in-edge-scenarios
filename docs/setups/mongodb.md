# MongoDB container quick auth setup

Authentication is controlled by a single set of five variables:

- `MONGO_ADMIN_USERNAME` — administrator user created in the `admin` database
- `MONGO_ADMIN_PASSWORD` — administrator password
- `MONGO_DATABASE` — application database name (e.g. `appdb`)
- `MONGO_APP_USERNAME` — application user granted `readWrite` on `MONGO_DATABASE`
- `MONGO_APP_PASSWORD` — application user password

## Example: standalone container run

```powershell
docker run -d \
	--name mongo-auth \
	-e MONGO_ADMIN_USERNAME=admin \
	-e MONGO_ADMIN_PASSWORD=se.cu.3e \
	-e MONGO_DATABASE=appdb \
	-e MONGO_APP_USERNAME=appuser \
	-e MONGO_APP_PASSWORD=app.04.app \
	-p 27017:27017 \
	efficient-storage-mongo
```

## Environment file (`.env-mongo`)

Provisioning via `./scripts/build_setup.sh` expects these variables inside an `.env-mongo` file located at the repository root:

```dotenv
MONGO_ADMIN_USERNAME=admin
MONGO_ADMIN_PASSWORD=se.cu.3e
MONGO_DATABASE=appdb
MONGO_APP_USERNAME=appuser
MONGO_APP_PASSWORD=app.04.app
```

If you omit the admin credentials the database will fall back to running without authentication.
