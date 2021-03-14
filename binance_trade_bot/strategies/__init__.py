from .default import DefaultStrategy


def get_strategy(name):
    return next((S for S in [DefaultStrategy] if S.__name__ == name), None)
