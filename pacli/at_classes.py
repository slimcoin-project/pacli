# at classes

from prettyprinter import cpprint as pprint
from pypeerassets.at.mutable_transactions import TransactionDraft
from decimal import Decimal
from pacli.provider import provider
from pacli.config import Settings
from pacli.dt_utils import finalize_tx # this is not ideal, TODO! maybe rename non-specific utils to extended_utils?
import pacli.at_utils as au

class AT:

    def create_tx(self, address: str, amount: str, input_address: str=Settings.key.address, tx_fee: Decimal=None, change_address: str=None, sign: bool=False, send: bool=False, verify: bool=False, debug: bool=False):

        dec_amount = Decimal(str(amount))
        rawtx = au.create_simple_transaction(amount=dec_amount, dest_address=address, input_address=Settings.key.address, change_address=change_address, debug=debug)

        return finalize_tx(rawtx, verify, sign, send, debug=debug)


    def show_txes(self, address: str=None, deckid: str=None, start: int=0, end: int=None, debug: bool=False):

        # deckid not implemented still

        txes = au.show_txes_by_block(address, startblock=start, endblock=end, debug=debug)
        pprint(txes)


