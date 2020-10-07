from datetime import timedelta

from .api import *

logger = logging.getLogger('big_c')

_INTERNAL_RATE = 0.1

_USER_CHARACTER_THROTTLE_DELTA = timedelta(seconds=2)
_CHARACTER_INFO_THROTTLE_DELTA = timedelta(seconds=2)
_CHARTS_THROTTLE_DELTA = timedelta(seconds=2)
_DEPTH_THROTTLE_DELTA = timedelta(seconds=2)


def _helper_detect_stage(this_stage: str, stage_desc: Union[bool, str]) -> bool:
    if stage_desc is False:
        return False
    if stage_desc is True:
        return True
    try:
        return this_stage in stage_desc
    except TypeError:
        return False


class BigC:
    # user character
    player: Player
    character: int
    bids: List[TBid]
    asks: List[TAsk]
    amount: int
    total_holding: int
    # character info
    name: str
    is_ICO: bool
    is_on_market: bool
    ICO_begin: Optional[datetime]
    ICO_end: Optional[datetime]
    ICO_total_backed: Optional[float]
    ICO_my_backed: Optional[float]
    ICO_users: Optional[int]
    global_holding: Optional[int]
    current_price: Optional[float]
    last_order: Optional[datetime]
    last_deal: Optional[datetime]
    global_sacrifices: Optional[int]
    rate: Optional[float]
    price: Optional[float]
    # charts
    charts: List[TChartum]
    # depth
    bids_all: List[TBid]
    asks_all: List[TAsk]

    _uc_update: Optional[datetime]
    _ci_update: Optional[datetime]
    _ch_update: Optional[datetime]
    _dp_update: Optional[datetime]

    def __init__(self, player: Player, character: int):
        self.player = player
        self.character = character
        self.update(ignore_throttle=True)

    def update(self, **kwargs):
        self.update_user_character(**kwargs)
        self.update_character_info(**kwargs)
        self.update_charts(**kwargs)
        self.update_depth(**kwargs)

    def update_user_character(self, ignore_throttle=False):
        if not ignore_throttle and self._uc_update > datetime.now():
            return
        uc = user_character(self.player, self.character)
        self.bids = uc.bids
        self.asks = uc.asks
        self.amount = uc.amount
        self.total_holding = uc.total_holding
        self._uc_update = datetime.now() + _USER_CHARACTER_THROTTLE_DELTA

    def update_character_info(self, ignore_throttle=False):
        if not ignore_throttle and self._ci_update > datetime.now():
            return
        ci = character_info(self.player, self.character)
        self.name = ci.name
        if isinstance(ci, TICO):
            self.is_ICO = True
            self.is_on_market = False
            self.ICO_begin = ci.begin
            self.ICO_end = ci.end
            self.ICO_total_backed = ci.total
            self.ICO_my_backed = get_my_ico(self.player, ci.id).amount
            self.ICO_users = ci.users
        elif isinstance(ci, TCharacter):
            self.is_ICO = False
            self.is_on_market = True
            self.global_holding = ci.total
            self.current_price = ci.current
            self.last_order = ci.last_order
            self.last_deal = ci.last_deal
            self.global_sacrifices = ci.sacrifices
            self.rate = ci.rate
            self.price = ci.price
        self._ci_update = datetime.now() + _CHARACTER_INFO_THROTTLE_DELTA

    def update_charts(self, ignore_throttle=False):
        if not ignore_throttle and self._ch_update > datetime.now():
            return
        cc = chara_charts(self.player, self.character)
        self.charts = cc
        self._ch_update = datetime.now() + _CHARTS_THROTTLE_DELTA

    def update_depth(self, ignore_throttle=False):
        if not ignore_throttle and self._dp_update > datetime.now():
            return
        the_depth = depth(self.player, self.character)
        self.bids_all = the_depth.bids
        self.asks_all = the_depth.asks
        self._dp_update = datetime.now() + _DEPTH_THROTTLE_DELTA

    @property
    def current_price_rounded(self):
        return round(self.current_price, 2)

    @property
    def initial_price(self):
        return self.charts[0].begin

    @property
    def initial_price_rounded(self):
        return round(self.initial_price, 2)

    @property
    def fundamental(self):
        self.update_character_info()
        return self.rate / _INTERNAL_RATE

    @property
    def fundamental_rounded(self):
        return round(self.fundamental, 2)

    def create_bid(self, bid: TBid, *, force_updates=False):
        result = create_bid(self.player, self.character, bid)
        if force_updates:
            self.update_user_character(ignore_throttle=True)
        return result

    def create_ask(self, ask: TAsk, *, force_updates=False):
        result = create_ask(self.player, self.character, ask)
        if force_updates:
            self.update_user_character(ignore_throttle=True)
        return result

    def cancel_bid(self, bid: TBid, *, force_updates=False):
        result = cancel_bid(self.player, bid)
        if force_updates:
            self.update_user_character(ignore_throttle=True)
        return result

    def cancel_ask(self, ask: TAsk, *, force_updates=False):
        result = cancel_ask(self.player, ask)
        if force_updates:
            self.update_user_character(ignore_throttle=True)
        return result

    def ensure_bids(self, bids: List[TBid], *, force_updates=True):
        self.update_user_character(ignore_throttle=_helper_detect_stage('before', force_updates))
        now_bids = self.bids
        now_bids = sorted(now_bids)
        bids = sorted(bids)
        while now_bids and bids:
            if now_bids[0] < bids[0]:
                logger.info(f"Cancel: {now_bids[0]!r}")
                self.cancel_bid(now_bids.pop(0))
            elif now_bids[0] > bids[0]:
                logger.info(f"Create: {bids[0]!r}")
                self.create_bid(bids.pop(0))
            else:
                logger.info(f"Equals: {now_bids[0]!r}")
                now_bids.pop(0)
                bids.pop(0)

        for now_bid in now_bids:
            self.cancel_bid(now_bid)

        for bid in bids:
            self.create_bid(bid)

        if _helper_detect_stage('after', force_updates):
            self.update_user_character(ignore_throttle=True)

    def ensure_asks(self, asks: List[TAsk], *, force_updates=True):
        self.update_user_character(ignore_throttle=_helper_detect_stage('before', force_updates))
        now_asks = self.asks
        now_asks = sorted(now_asks)
        asks = sorted(asks)
        should_create = []
        while now_asks and asks:
            if now_asks[0] < asks[0]:
                logger.info(f"Cancel: {now_asks[0]!r}")
                self.cancel_ask(now_asks.pop(0))
            elif now_asks[0] > asks[0]:
                logger.info(f"Create: {asks[0]!r}")
                should_create.append(asks.pop(0))
            else:
                logger.info(f"Equals: {now_asks[0]!r}")
                now_asks.pop(0)
                asks.pop(0)

        for now_ask in now_asks:
            self.cancel_ask(now_ask)

        for ask in should_create:
            self.create_ask(ask)

        for ask in asks:
            self.create_ask(ask)

        if _helper_detect_stage('after', force_updates):
            self.update_user_character(ignore_throttle=True)