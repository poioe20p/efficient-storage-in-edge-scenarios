# MongoDB debug commands

Quick commands to verify whether the MongoDB container is running with authentication, confirm credentials, and inspect runtime configuration.

## 1. Get a shell inside the MongoDB container

```bash
docker exec -it mongodb bash
```

All commands below assume you are either running them from the host with `docker exec … mongosh`, or after attaching to the container shell.

## 2. Check connectivity without credentials

```bash
mongosh --quiet --eval "db.adminCommand('ping')"
```

- Succeeds only if MongoDB is running without authentication or you are still within the localhost auth bypass window.
- Fails with `Authentication failed` when auth is enforced.

## 3. Check connectivity with application credentials

```bash
mongosh "mongodb://appuser:app.04.app@127.0.0.1:27017/appdb?authSource=appdb" \
  --quiet --eval "db.runCommand({ping:1})"
```

- Replace `appuser`, `app.04.app`, and `appdb` with the values from `.env-mongo` (`MONGO_APP_USERNAME`, `MONGO_APP_PASSWORD`, `MONGO_DATABASE`).
- If this fails, verify the user exists (next section) or that you reset the volume after changing passwords.

## 4. Check connectivity with the root user

```bash
mongosh "mongodb://admin:se.cu.3e@127.0.0.1:27017/admin" \
  --quiet --eval "db.adminCommand('ping')"
```

- Replace credentials with your `MONGO_ADMIN_USERNAME` and `MONGO_ADMIN_PASSWORD`.
- If this succeeds while the app user fails, the app account likely was never created.

## 5. List users to confirm they exist

```bash
mongosh "mongodb://admin:se.cu.3e@127.0.0.1:27017/admin" --quiet <<'JS'
use admin;
print('Admin users:');
printjson(db.getUsers());
use appdb;
print('App DB users:');
printjson(db.getUsers());
JS
```

- Update database names to match your setup if you changed them.

## 6. Inspect runtime flags (is auth enabled?)

```bash
mongosh "mongodb://admin:se.cu.3e@127.0.0.1:27017/admin" --quiet --eval "
  const opts = db.adminCommand({ getCmdLineOpts: 1 });
  printjson(opts.parsed);"
```

Look for `security.authorization: "enabled"` or the presence of `--auth` under `argv`.

## 7. Confirm process flags directly

```bash
ps -ef | grep [m]ongod
```

- If you see `--auth` in the command line, MongoDB was launched with authentication enforced.

## 8. Tail the entrypoint logs for initialization hints

```bash
docker logs mongodb --tail 50
```

- Lines such as `Created root user` and `Starting mongod with authorization enabled...` confirm that the entrypoint processed your init vars.
- If you see `Database appears initialized and no root user provided; starting without auth.`, the data directory already existed when the container started and your env vars were ignored.

## 9. Reset the volume when credentials change

If you ever modify `.env-mongo`, reset the volume so the users are recreated with the new passwords:

```bash
./scripts/reset_mongodb.sh
./scripts/build_setup.sh
```

This drops the `mongodb-data` volume and reprovisions the container with the updated credentials.
