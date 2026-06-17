import os
import tomllib
import structlog
from pathlib import Path
from dotenv import load_dotenv
from invoke import task
from invoke.exceptions import Exit

logger = structlog.get_logger()

BASE_DIR = Path(__file__).parent

config_path = BASE_DIR / "config.toml"
if not config_path.exists():
    raise Exit(f"Config {config_path} not found", code = 1)
with open(config_path, "rb") as f:
    config = tomllib.load(f)

HARDWARE = config["hardware"]
TEMPLATES = config["templates"]

load_dotenv(dotenv_path = BASE_DIR / ".env")

@task
def set_root_password(c):
    if not (password := os.os.getenv("ROOT_PASSWORD")):
        raise Exit("ROOT_PASSWORD missing", code = 1)
    logger.info("root password updated")
    c.config.update({"sudo" : {"password" : password}})

@task(pre = [set_root_password])
def setup_system(c):
    print("Hello from uv run inv setup-system")
