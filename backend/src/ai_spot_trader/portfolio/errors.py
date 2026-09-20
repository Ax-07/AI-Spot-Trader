class PortfolioLedgerError(Exception):
    """Base error raised when a PAPER portfolio mutation is impossible."""


class UnknownBalanceAssetError(PortfolioLedgerError):
    """Raised when the required settlement balance does not exist."""


class InsufficientBalanceError(PortfolioLedgerError):
    """Raised when a settlement balance cannot cover a PAPER BUY."""


class PositionNotHeldError(PortfolioLedgerError):
    """Raised when a PAPER SELL targets an asset that is not held."""


class InsufficientPositionError(PortfolioLedgerError):
    """Raised when the requested PAPER SELL exceeds the available position."""


class AmbiguousAssetRoleError(PortfolioLedgerError):
    """Raised when an asset would be both a balance and a position."""
