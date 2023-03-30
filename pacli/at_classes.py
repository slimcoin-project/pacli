# at classes

import pypeerassets as pa
from prettyprinter import cpprint as pprint
from pypeerassets.at.mutable_transactions import TransactionDraft
from pypeerassets.at.at_parser import burn_address
from decimal import Decimal
from pacli.provider import provider
from pacli.config import Settings
import pacli.extended_utils as eu
import pacli.at_utils as au

class ATToken():

    def create_tx(self, address: str, amount: str, input_address: str=Settings.key.address, tx_fee: Decimal=None, change_address: str=None, sign: bool=False, send: bool=False, verify: bool=False, debug: bool=False) -> str:

        dec_amount = Decimal(str(amount))
        rawtx = au.create_simple_transaction(amount=dec_amount, dest_address=address, input_address=Settings.key.address, change_address=change_address, debug=debug)

        return eu.finalize_tx(rawtx, verify, sign, send, debug=debug)

    def show_txes(self, address: str=None, deckid: str=None, start: int=0, end: int=None, debug: bool=False, burns: bool=False) -> None:
        '''show all transactions to a tracked address between two block heights.'''

        if burns:
             print("Using burn address.")
             address = burn_address(network_name=provider.network)

        txes = au.show_txes_by_block(tracked_address=address, deckid=deckid, startblock=start, endblock=end, debug=debug)
        pprint(txes)

    def my_txes(self, address: str=None, deckid: str=None, unclaimed: bool=False) -> None:

        txes = au.show_wallet_txes(tracked_address=address, deckid=deckid, unclaimed=unclaimed)
        pprint(txes)

    @classmethod ### NEW FEATURE - AT ###
    def claim(self, deckid: str, txid: str, receiver: list=None, amount: list=None,
              locktime: int=0, verify: bool=False, sign: bool=False, send: bool=False, debug: bool=False) -> str:
        '''To simplify self.issue, all data is taken from the transaction.'''
        # NOTE: amount is always a list! It is for cases where the claimant wants to send tokens to different addresses.

        #deck = self.__find_deck(deckid)
        deck = pa.find_deck(provider, deckid)

        asset_specific_data, amount, receiver = au.create_at_issuance_data(deck, txid, amount=amount, debug=debug)

        # return self.transfer(deckid=deckid, receiver=receiver, amount=amount, asset_specific_data=asset_specific_data,
        #                     verify=verify, locktime=locktime, sign=sign, send=send)
        issue = pa.card_transfer(provider=provider,
                                 inputs=provider.select_inputs(Settings.key.address, 0.02),
                                 card=card,
                                 change_address=Settings.change,
                                 locktime=locktime
                                 )

class PoBToken(ATToken):

    def create_burn_tx(self, amount: str, input_address: str=Settings.key.address, tx_fee: Decimal=None, change_address: str=None, sign: bool=False, send: bool=False, verify: bool=False, debug: bool=False) -> str:
        # for PoB token, uses automatically the burn address of the network.

        return self.create_tx(address=burn_address(network_name=provider.network), amount=amount, input_address=input_address, tx_fee=tx_fee, change_address=change_address, sign=sign, send=send, verify=verify, debug=debug)

    def my_burns(self, unclaimed: bool=False, wallet: bool=False) -> None:

        input_address = Settings.key.address if not wallet else None
        txes = au.show_wallet_txes(tracked_address=burn_address(network_name=provider.network), unclaimed=unclaimed, burntxes=True, input_address=input_address)
        pprint(txes)
