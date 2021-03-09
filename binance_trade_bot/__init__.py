try:
    from .version import __version__
except ImportError:  # pragma: no cover
    from pkg_resources import get_distribution, DistributionNotFound

    try:
        __version__ = get_distribution(__name__).version
    except DistributionNotFound:
        # package is not installed
        __version__ = "0.0.0.not-installed"
