from .base import DataProvider
from .mock_provider import MockDataProvider
from .pipeline import run_analysis_cycle

try:
    from .oanda_provider import OandaDataProvider, load_credentials
except ImportError:
    # `requests` not installed yet — everything else still works fine
    # with MockDataProvider; install `requests` when you're ready to
    # connect to real OANDA data.
    OandaDataProvider = None
    load_credentials = None

__all__ = [
    "DataProvider",
    "MockDataProvider",
    "OandaDataProvider",
    "load_credentials",
    "run_analysis_cycle",
]
