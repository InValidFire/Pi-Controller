import core.common as common
import core.embed as ebed


class BotError(Exception):
    "Base Exception Class"
    pass


class UserNotFoundError(BotError):
    """Raised when the user is not found."""
    pass
