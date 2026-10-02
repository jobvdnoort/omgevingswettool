"""Logging zonder gevoelige waarden."""
import logging


def configure_logging(debug: bool = False) -> None:
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
