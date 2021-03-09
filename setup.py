import os
import sys

from setuptools import find_packages
from setuptools import setup
from setuptools_cythonize import get_cmdclass


def _parse_requirements_file(requirements_file):
    parsed_requirements = []
    with open(requirements_file) as rfh:
        for line in rfh.readlines():
            line = line.strip()
            if not line or line.startswith(("#", "-r", "--")):
                continue
            parsed_requirements.append(line)
    return parsed_requirements


# Change to salt source's directory prior to running any command
try:
    SETUP_DIRNAME = os.path.dirname(__file__)
except NameError:
    # We're most likely being frozen and __file__ triggered this NameError
    # Let's work around that
    SETUP_DIRNAME = os.path.dirname(sys.argv[0])

if SETUP_DIRNAME != "":
    os.chdir(SETUP_DIRNAME)

SETUP_DIRNAME = os.path.abspath(SETUP_DIRNAME)

setup(
    name="binance-trade-bot",
    cmdclass=get_cmdclass(),
    setup_requires=["setuptools_scm>=3.4", "setuptools_cythonize"],
    install_requires=_parse_requirements_file(os.path.join(SETUP_DIRNAME, "requirements.txt")),
    packages=find_packages(),
    entry_points={"console_scripts": ["binance-trade-bot = binance_trade_bot.crypto_trading:main"]},
    use_scm_version={
        "root": SETUP_DIRNAME,
        "write_to": "binance_trade_bot/version.py",
        "write_to_template": '__version__ = "{version}"',
    },
)
