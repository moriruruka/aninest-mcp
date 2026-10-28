"""AniNest MCP server package."""

from .server import mcp
from .version import VERSION

__version__ = VERSION
__all__ = ["mcp", "__version__"]
