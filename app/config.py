import os
import yaml


class Config:
    def __init__(self, env: str = None, config_path: str = None):
        env = env or os.getenv("ENV", "dev")
        config_path = config_path or os.getenv(
            "CONFIG_PATH",
            os.path.join(os.path.dirname(__file__), "..", "household-finances-config.yaml")
        )

        config_path = os.path.abspath(config_path)

        with open(config_path, "r") as f:
            all_config = yaml.safe_load(f)

        self._config = all_config.get("default", {})
        self._config.update(all_config.get(env, {}))
        self.env = env

    def get(self, key: str, default=None):
        return self._config.get(key, default)

    def __getitem__(self, key):
        return self._config[key]

    def __str__(self):
        return f"Config(env={self.env}, keys={list(self._config.keys())})"


# Global config object you can import anywhere
config = Config()
