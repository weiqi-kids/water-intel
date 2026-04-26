"""
公司新聞爬蟲
"""

from .base import CompanyFetcher, CompanyDocument

from .american_water import AmericanWaterFetcher
from .ao_smith import AoSmithFetcher
from .badger import BadgerFetcher
from .chien_fu import ChienFuFetcher
from .danaher import DanaherFetcher
from .energy_recovery import EnergyRecoveryFetcher
from .essential import EssentialFetcher
from .kurita import KuritaFetcher
from .mueller import MuellerFetcher
from .pentair import PentairFetcher
from .veolia import VeoliaFetcher
from .watts import WattsFetcher
from .xylem import XylemFetcher
from .zhongyu import ZhongyuFetcher

FETCHERS = {
    "american_water": AmericanWaterFetcher,
    "ao_smith": AoSmithFetcher,
    "badger": BadgerFetcher,
    "chien_fu": ChienFuFetcher,
    "danaher": DanaherFetcher,
    "energy_recovery": EnergyRecoveryFetcher,
    "essential": EssentialFetcher,
    "kurita": KuritaFetcher,
    "mueller": MuellerFetcher,
    "pentair": PentairFetcher,
    "veolia": VeoliaFetcher,
    "watts": WattsFetcher,
    "xylem": XylemFetcher,
    "zhongyu": ZhongyuFetcher,
}
