from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus
from dotenv import dotenv_values

ENV_FILE_NAME = ".env-mongo"


@dataclass(frozen=True)
class MongoConfig:
	"""MongoDB-related configuration loaded from ``.env-mongo``."""

	admin_username: str
	admin_password: str
	database: str
	app_username: str
	app_password: str

	@classmethod
	def load(cls, env_path: Optional[str] = None) -> "MongoConfig":
		"""Load credentials from the supplied env file or the default one."""

		path = Path(env_path) if env_path else Path(__file__).with_name(ENV_FILE_NAME)
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
			raise ValueError(f"Missing MongoDB env vars: {', '.join(missing)}")

		return cls(
			admin_username=str(values["MONGO_ADMIN_USERNAME"]),
			admin_password=str(values["MONGO_ADMIN_PASSWORD"]),
			database=str(values["MONGO_DATABASE"]),
			app_username=str(values["MONGO_APP_USERNAME"]),
			app_password=str(values["MONGO_APP_PASSWORD"]),
		)

	def app_uri(self, host: str = "localhost", port: int = 27017, auth_db: Optional[str] = None) -> str:
		"""Build a connection string for the application MongoDB user."""

		username = quote_plus(self.app_username)
		password = quote_plus(self.app_password)
		database = quote_plus(auth_db or self.database)
		return f"mongodb://{username}:{password}@{host}:{port}/{database}"

	def admin_uri(self, host: str = "localhost", port: int = 27017) -> str:
		"""Build a connection string for the admin MongoDB user."""

		username = quote_plus(self.admin_username)
		password = quote_plus(self.admin_password)
		return f"mongodb://{username}:{password}@{host}:{port}/admin"


__all__ = ["MongoConfig"]
