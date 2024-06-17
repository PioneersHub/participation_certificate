from pathlib import Path
from omegaconf import OmegaConf

import colorama
import structlog

cr = structlog.dev.ConsoleRenderer(
    columns=[
        # Render the timestamp without the key name in yellow.
        structlog.dev.Column(
            "timestamp",
            structlog.dev.KeyValueColumnFormatter(
                key_style=None,
                value_style=colorama.Fore.YELLOW,
                reset_style=colorama.Style.RESET_ALL,
                value_repr=str,
            ),
        ),
        structlog.dev.Column(
            "level",
            structlog.dev.KeyValueColumnFormatter(
                key_style=None,
                value_style=colorama.Fore.BLUE,
                reset_style=colorama.Style.RESET_ALL,
                value_repr=lambda x: f"[{x}]",
            ),
        ),
        # Default formatter for all keys not explicitly mentioned. The key is
        # cyan, the value is green.
        structlog.dev.Column(
            "",
            structlog.dev.KeyValueColumnFormatter(
                key_style=colorama.Fore.CYAN,
                value_style=colorama.Fore.GREEN,
                reset_style=colorama.Style.RESET_ALL,
                value_repr=str,
            ),
        ),
        # Render the event without the key name in bright magenta.
        structlog.dev.Column(
            "event",
            structlog.dev.KeyValueColumnFormatter(
                key_style=None,
                value_style=colorama.Style.BRIGHT + colorama.Fore.MAGENTA,
                reset_style=colorama.Style.RESET_ALL,
                value_repr=str,
            ),
        ),
    ]
)

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="%Y%m%dT%H%M%S", utc=True),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)
structlog.configure(processors=structlog.get_config()["processors"][:-1] + [cr])
logger = structlog.get_logger()

global_conf = OmegaConf.load(Path(__file__).parents[1] / "config.yaml")
local_config_path = Path(__file__).parents[1] / "config_local.yaml"
if not local_config_path.exists():
    with local_config_path.open("w") as f:
        f.write("# Add your local configuration here")
local_conf = OmegaConf.load(local_config_path)
conf = OmegaConf.merge(global_conf, local_conf)

# make dirs in config to Path objects
for k, dir_from_project_root in conf.dirs.items():
    conf.dirs[k] = Path(__file__).parents[1] / dir_from_project_root

all_fonts = list(conf.dirs.fonts_dir.rglob("*.ttf"))
logger.debug(f"Found {len(all_fonts)} fonts in {conf.dirs.fonts_dir.name}")

__ALL__ = ["all_fonts", "logger", "conf"]
