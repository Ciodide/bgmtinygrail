import logging.config

import click

from .accounts import accounts
from .check_auction_price_value import check_auction_price_value
from .check_cv import check_cv
from .force_view import force_view
from .magic import magic
from .sync_asks_collect import sync_asks_collect


@click.group()
@click.option('-L', '--log-conf', default='logging.conf')
def entry_point(log_conf):
    logging.config.fileConfig(log_conf)


assert isinstance(entry_point, click.Group)

entry_point.add_command(accounts)
entry_point.add_command(check_auction_price_value)
entry_point.add_command(check_cv)
entry_point.add_command(force_view)
entry_point.add_command(magic)
entry_point.add_command(sync_asks_collect)
