__version__ = "0.9.0"

import logging
import os
import sys
from pathlib import Path

import colorama
import structlog
from omegaconf import OmegaConf

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
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="%Y%m%dT%H%M%S", utc=True),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
    context_class=dict,
    # Logs go to stderr so script-style `$(uv run python -c '...')` captures
    # stay clean — stdout is reserved for the script's actual output.
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    cache_logger_on_first_use=False,
)
structlog.configure(processors=structlog.get_config()["processors"][:-1] + [cr])
logger = structlog.get_logger()

# Active project is selected via the CERTIFICATE_PROJECT_SLUG env var; per-event
# config + secrets + data + outputs all live under projects/<slug>/. Repo-root
# config.yaml supplies committed defaults that are overlaid by the per-project
# config.yaml. fonts/ + email_templates/ stay repo-wide.
_REPO_ROOT = Path(__file__).parents[1]
_PROJECTS_DIR = _REPO_ROOT / "projects"
_PROJECT_SLUG = os.environ.get("CERTIFICATE_PROJECT_SLUG")
if not _PROJECT_SLUG:
    _available = (
        sorted(p.name for p in _PROJECTS_DIR.iterdir() if p.is_dir())
        if _PROJECTS_DIR.exists()
        else []
    )
    raise SystemExit(
        "CERTIFICATE_PROJECT_SLUG env var is not set.\n"
        f"  Set it to one of: {_available or '(no projects/ subdirectories found)'}\n"
        "  e.g.  export CERTIFICATE_PROJECT_SLUG=<slug>"
    )

PROJECT_DIR = _PROJECTS_DIR / _PROJECT_SLUG
if not PROJECT_DIR.is_dir():
    raise SystemExit(
        f"Project directory not found: {PROJECT_DIR}\n"
        f"  CERTIFICATE_PROJECT_SLUG={_PROJECT_SLUG!r} does not match an existing folder."
    )

_project_config_path = PROJECT_DIR / "config.yaml"
if not _project_config_path.exists():
    raise SystemExit(f"Project config not found: {_project_config_path}")

global_conf = OmegaConf.load(_REPO_ROOT / "config.yaml")
local_conf = OmegaConf.load(_project_config_path)
conf = OmegaConf.merge(global_conf, local_conf)

# Resolve dirs.* into absolute Paths. fonts_dir is repo-wide; everything else
# is project-relative so an event's whole state stays self-contained.
_REPO_RELATIVE_DIR_KEYS = frozenset({"fonts_dir"})
for k, rel_path in conf.dirs.items():
    base = _REPO_ROOT if k in _REPO_RELATIVE_DIR_KEYS else PROJECT_DIR
    conf.dirs[k] = base / rel_path

all_fonts = list(conf.dirs.fonts_dir.rglob("*.ttf"))
logger.debug(f"Found {len(all_fonts)} fonts in {conf.dirs.fonts_dir.name}")

__ALL__ = ["all_fonts", "logger", "conf"]
