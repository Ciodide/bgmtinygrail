from ._base import *


class IgnoreStrategy(ABCCharaStrategy):
    strategy = Strategy.IGNORE

    def transition(self):
        from .balance import BalanceStrategy
        if len(self.big_c.asks) == 1 and len(self.big_c.bids) == 1 \
                and self.big_c.asks[0].price == self.big_c.bids[0].price:
            logger.info("already in balance")
            return self._transact(BalanceStrategy)
        if self.big_c.total_holding > 0:
            logger.info("new stock")
            self._fast_seller(low=self._exchange_price)
            if self.big_c.amount or self.big_c.asks:
                return self._transact(BalanceStrategy)
        elif self.big_c.bids and self.big_c.bids[0].price == 2.0 and self.big_c.bids[0].amount == 2:
            logger.info("forced view")
            self._fast_forward(self._exchange_price)
            return self._transact(BalanceStrategy)
        return self

    def output(self):
        self.big_c.ensure_asks([], force_updates='before')
        self.big_c.ensure_bids([], force_updates='after')
