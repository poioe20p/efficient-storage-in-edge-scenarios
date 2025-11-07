"""Configuration helpers for MongoDB credentials."""
import os
from collections import namedtuple

from dotenv import dotenv_values
from urllib.parse import quote_plus


ENV_FILE_NAME = ".env-mongo"
DEFAULT_MONGO_HOST_IP = os.getenv("MONGO_HOST_IP", "192.168.100.1")

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

		config = cls(
			values["MONGO_ADMIN_USERNAME"],
			values["MONGO_ADMIN_PASSWORD"],
			values["MONGO_DATABASE"],
			values["MONGO_APP_USERNAME"],
			values["MONGO_APP_PASSWORD"],
		)
		return config

	@property
	def hosts(self):
		return ["10.0.0.4", "10.0.1.4"]

	@property
	def port(self):
		return "27017"

	@property
	def router_host(self):
		return os.getenv("MONGO_ROUTER_HOST", DEFAULT_MONGO_HOST_IP)

	@property
	def router_port(self):
		return os.getenv("MONGO_ROUTER_PORT", "27020")

	@property
	def config_host(self):
		return os.getenv("MONGO_CONFIG_HOST", os.getenv("MONGO_ROUTER_HOST", DEFAULT_MONGO_HOST_IP))

	@property
	def config_port(self):
		return os.getenv("MONGO_CONFIG_PORT", "27019")

	def app_uri(self, host=None, port=None, auth_db=None):
		"""Build a connection string for the application MongoDB user."""
		host = host or self.router_host
		port = port or self.port
		username = quote_plus(self.app_username)
		password = quote_plus(self.app_password)
		database = quote_plus(auth_db or self.database)
		return "mongodb://%s:%s@%s:%s/%s" % (username, password, host, port, database)

	def all_app_uris(self, auth_db=None):
		"""Return a list of URIs for all configured hosts."""
		return [self.app_uri(host=h, port=self.port, auth_db=auth_db) for h in self.hosts]

	def router_app_uri(self, auth_db=None):
		"""Build an application URI that targets the mongos router."""
		return self.app_uri(
			host=self.router_host,
			port=self.router_port,
			auth_db=auth_db,
		)

	def admin_uri(self, host="localhost", port=27017):
		"""Build a connection string for the admin MongoDB user."""
		username = quote_plus(self.admin_username)
		password = quote_plus(self.admin_password)
		if isinstance(port, int):
			port = str(port)
		return "mongodb://%s:%s@%s:%s/admin" % (username, password, host, port)


__all__ = ["MongoConfig"]
