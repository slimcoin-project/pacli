import pypeerassets as pa
import pypeerassets.at.constants as c
from prettyprinter import cpprint as pprint
from pypeerassets.at.mutable_transactions import TransactionDraft
from decimal import Decimal
from pacli.provider import provider
from pacli.config import Settings
from pacli.tui import print_deck_list
import pacli.extended_utils as eu
import pacli.at_utils as au
from pypeerassets.at.dt_misc_utils import list_decks_by_at_type

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

    @classmethod
    def claim(self, deckid: str, txid: str, receiver: list=None, amount: list=None,
              locktime: int=0, verify: bool=False, sign: bool=False, send: bool=False, debug: bool=False) -> str:
        '''To simplify self.issue, all data is taken from the transaction.'''
        # NOTE: amount is always a list! It is for cases where the claimant wants to send tokens to different addresses.

        #deck = self.__find_deck(deckid)
        deck = pa.find_deck(provider, deckid)

        asset_specific_data, amount, receiver = au.create_at_issuance_data(deck, txid, amount=amount, debug=debug)

        # return self.transfer(deckid=deckid, receiver=receiver, amount=amount, asset_specific_data=asset_specific_data,
        #                     verify=verify, locktime=locktime, sign=sign, send=send)
        issue = eu.advanced_card_transfer(provider=provider,
                                 inputs=provider.select_inputs(Settings.key.address, 0.02),
                                 card=card,
                                 change_address=Settings.change,
                                 locktime=locktime
                                 )
    @classmethod
    def deck_spawn(self, name, tracked_address, multiplier: int=1, number_of_decimals: int=2, startblock: int=None,
              endblock: int=None, version=1, locktime: int=0, verify: bool=False, sign: bool=False,
              send: bool=False) -> None:
        '''Wrapper to facilitate addresstrack spawns without having to deal with asset_specific_data.'''

        asset_specific_data = eu.create_deckspawn_data(c.ID_AT, at_address=tracked_address, multiplier=multiplier, startblock=startblock, endblock=endblock)

        return eu.advanced_deck_spawn(name=name, number_of_decimals=number_of_decimals, issue_mode=0x01, locktime=locktime,
                          asset_specific_data=asset_specific_data, verify=verify, sign=sign, send=send)


    def deck_info(self, deckid: str):
        '''Prints AT-specific deck info.'''

        au.at_deckinfo(deckid)

    @classmethod
    def deck_list(self):
        '''Prints list of AT decks'''

        print_deck_list(list_decks_by_at_type(provider, c.ID_AT))


    #@classmethod
    #def claim_bulk(self, deckid: str, number: int, start: int=0) -> str:
    #    '''this function checks all transactions from own address to tracked address and then issues tx.'''
    #
    #    deck = pa.find_deck(provider, deckid)
    #    tracked_address = deck.donation_txid
    #     # UNFINISHED #

class PoBToken(ATToken):
    # bundles all PoB-specific functions.

    def deck_spawn(self, name, multiplier: int=1, number_of_decimals: int=2, startblock: int=None,
              endblock: int=None, verify: bool=False, sign: bool=False,
              send: bool=False, locktime: int=0, version=1):
        """Spawn a new PoB token, uses automatically the burn address of the network."""

        tracked_address = au.burn_address()
        print("Using burn address:", tracked_address)

        return super().deck_spawn(name, tracked_address, multiplier, number_of_decimals, startblock, endblock, version, locktime, verify, sign, send)

    def create_burn_tx(self, amount: str, input_address: str=Settings.key.address, tx_fee: Decimal=None, change_address: str=None, sign: bool=False, send: bool=False, verify: bool=False, debug: bool=False) -> str:
        """Burn coins with a controlled transaction from the current main address."""

        return self.create_tx(address=au.burn_address(), amount=amount, input_address=input_address, tx_fee=tx_fee, change_address=change_address, sign=sign, send=send, verify=verify, debug=debug)

    def my_burns(self, unclaimed: bool=False, wallet: bool=False) -> None:
        """List all burn transactions, of this address or the whole wallet (--wallet option).
           --unclaimed shows only transactions which haven't been claimed yet."""

        input_address = Settings.key.address if not wallet else None
        txes = au.show_wallet_txes(tracked_address=au.burn_address(), unclaimed=unclaimed, burntxes=True, input_address=input_address)
        pprint(txes)
