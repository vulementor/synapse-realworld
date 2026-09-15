from synapse_realworld.cli import app
from synapse_realworld.cli_market import register_market_commands

register_market_commands(app)

__all__ = ["app"]
