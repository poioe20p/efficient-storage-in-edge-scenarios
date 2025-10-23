"""Configuration helpers for MongoDB credentials."""

import os
from collections import namedtuple

from dotenv import dotenv_values

try:
	from urllib.parse import quote_plus
except ImportError:  # Python 2 fallback (osrg/ryu container)
	from urllib import quote_plus


ENV_FILE_NAME = ".env-mongo"

MongoConfigTuple = namedtuple(
	"MongoConfigTuple",
	[
		"admin_username",
		"admin_password",
		"database",
		"app_username",
		"app_password",
	],
)


class MongoConfig(MongoConfigTuple):
	"""MongoDB-related configuration loaded from ``.env-mongo``."""

	__slots__ = ()

	@classmethod
	def load(cls, env_path=None):
		"""Load credentials from the supplied env file or the default one."""

		path = env_path or os.path.join(os.path.dirname(__file__), ENV_FILE_NAME)
		values = dotenv_values(path)
		required = (
			"MONGO_ADMIN_USERNAME",
			"MONGO_ADMIN_PASSWORD",
			"MONGO_DATABASE",
			"MONGO_APP_USERNAME",
			"MONGO_APP_PASSWORD",
		)
		missing = [key for key in required if not values.get(key)]
		if missing:
			raise ValueError("Missing MongoDB env vars: %s" % ", ".join(missing))

		host = values.get("MONGO_APP_HOST") or values.get("MONGO_HOST")
		if host:
			os.environ.setdefault("MONGO_APP_HOST", host)
		port = values.get("MONGO_APP_PORT") or values.get("MONGO_PORT")
		if port:
			os.environ.setdefault("MONGO_APP_PORT", str(port))

		return cls(
			values["MONGO_ADMIN_USERNAME"],
			values["MONGO_ADMIN_PASSWORD"],
			values["MONGO_DATABASE"],
			values["MONGO_APP_USERNAME"],
			values["MONGO_APP_PASSWORD"],
		)

	def app_uri(self, host=None, port=None, auth_db=None):
		"""Build a connection string for the application MongoDB user."""

		host = host or os.getenv("MONGO_APP_HOST") or os.getenv("MONGO_HOST") or "localhost"
		port = port or os.getenv("MONGO_APP_PORT") or os.getenv("MONGO_PORT") or "27017"
		if isinstance(port, int):
			port = str(port)
		username = quote_plus(self.app_username)
		password = quote_plus(self.app_password)
		database = quote_plus(auth_db or self.database)
		return "mongodb://%s:%s@%s:%s/%s" % (username, password, host, port, database)

	def admin_uri(self, host="localhost", port=27017):
		"""Build a connection string for the admin MongoDB user."""

		username = quote_plus(self.admin_username)
		password = quote_plus(self.admin_password)
		if isinstance(port, int):
			port = str(port)
		return "mongodb://%s:%s@%s:%s/admin" % (username, password, host, port)


__all__ = ["MongoConfig"]
