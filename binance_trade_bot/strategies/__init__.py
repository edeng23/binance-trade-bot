from .default import DefaultStrategy
from .multiple_coins import MultipleActiveCoinsStrategy


def get_strategy(name):
    return next((S for S in [DefaultStrategy, MultipleActiveCoinsStrategy] if S.__name__ == name), None)
