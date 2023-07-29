import pypeerassets as pa
import pypeerassets.at.constants as c
from prettyprinter import cpprint as pprint
from pypeerassets.at.mutable_transactions import TransactionDraft
from decimal import Decimal
from pacli.provider import provider
from pacli.config import Settings
from pacli.tui import print_deck_list
import pacli.extended_utils as eu
import pacli.extended_interface as ei
import pacli.at_utils as au
from pypeerassets.at.dt_misc_utils import list_decks_by_at_type

class ATToken:

    def create_tx(self, address: str, amount: str, input_address: str=Settings.key.address, tx_fee: Decimal=None, change_address: str=None, sign: bool=False, send: bool=False, verify: bool=False, debug: bool=False) -> str:

        dec_amount = Decimal(str(amount))
        rawtx = ei.run_command(au.create_simple_transaction, amount=dec_amount, dest_address=address, input_address=Settings.key.address, change_address=change_address, debug=debug)

        return ei.run_command(eu.finalize_tx, rawtx, verify, sign, send, debug=debug)

    def show_txes(self, address: str=None, deckid: str=None, start: int=0, end: int=None, debug: bool=False, burns: bool=False) -> None:
        '''Show all transactions to a tracked address between two block heights (very slow!).'''

        if burns:
             print("Using burn address.")
             address = burn_address(network_name=provider.network)

        txes = ei.run_command(au.show_txes_by_block, tracked_address=address, deckid=deckid, startblock=start, endblock=end, debug=debug)
        pprint(txes)

    def my_txes(self, address: str=None, deck: str=None, unclaimed: bool=False, wallet: bool=False, silent: bool=False, debug: bool=False) -> None:
        '''Shows all transactions from your wallet to the tracked address.'''

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent) if deck else None
        input_address = Settings.key.address if not wallet else None
        txes = ei.run_command(au.show_wallet_txes, tracked_address=address, deckid=deckid, unclaimed=unclaimed, input_address=input_address, silent=silent, debug=debug)
        if not silent:
            pprint(txes)
        else:
            print(txes)

    @classmethod
    def claim_reward(self, deck_str: str, txid: str, receivers: list=None, amounts: list=None,
              locktime: int=0, payto: str=None, payamount: str=None, verify: bool=False, sign: bool=False, send: bool=False, debug: bool=False, force: bool=False) -> str:
        '''Claims tokens for a transaction to a tracked address.'''
        # NOTE: amount is always a list! It is for cases where the claimant wants to send tokens to different addresses.


        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck_str)
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        dec_payamount = Decimal(str(payamount)) if payamount else None

        asset_specific_data, amount, receiver = ei.run_command(au.create_at_issuance_data, deck, txid, Settings.key.address, amounts=amounts, receivers=receivers, payto=payto, payamount=dec_payamount, debug=debug, force=force)

        return ei.run_command(eu.advanced_card_transfer, deck,
                                 amount=amount,
                                 receiver=receiver,
                                 locktime=locktime,
                                 asset_specific_data=asset_specific_data,
                                 sign=sign,
                                 send=send,
                                 verify=verify,
                                 debug=debug
                                 )

    @classmethod
    def deck_spawn(self, name, tracked_address, multiplier: int=1, number_of_decimals: int=2, startblock: int=None,
              endblock: int=None, version=1, locktime: int=0, verify: bool=False, sign: bool=False,
              send: bool=False) -> None:
        '''Spawns a new AT deck.'''

        asset_specific_data = ei.run_command(eu.create_deckspawn_data, c.ID_AT, at_address=tracked_address, multiplier=multiplier, startblock=startblock, endblock=endblock)

        return ei.run_command(eu.advanced_deck_spawn, name=name, number_of_decimals=number_of_decimals,
               issue_mode=0x01, locktime=locktime, asset_specific_data=asset_specific_data, verify=verify,
               sign=sign, send=send)


    def deck_info(self, deck: str) -> None:
        '''Prints AT-specific deck info.'''

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck)
        ei.run_command(au.at_deckinfo, deckid)

    @classmethod
    def deck_list(self) -> None:
        '''Prints list of AT decks'''

        ei.run_command(print_deck_list, list_decks_by_at_type(provider, c.ID_AT))

    def show_claims(self, deck_str: str, address: str=None, wallet: bool=False, full: bool=False, param: str=None):
        '''Shows all valid claim transactions for a deck, rewards and tracked transactions enabling them.'''

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck_str)
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        claims = ei.run_command(au.get_valid_cardissues, deck, input_address=address, only_wallet=wallet)
        for claim in claims:
            if full:
                pprint(claim.__dict__)
                continue
            elif param:
                params = [param] if type(param) == str else param # .split(",")
            else:
                params = ["txid", "donation_txid", "amount", "blocknum"]

            pprint({p : claim.__dict__[p] for p in params})


class PoBToken(ATToken):
    # bundles all PoB-specific functions.

    def deck_spawn(self, name, multiplier: int=1, number_of_decimals: int=2, startblock: int=None,
              endblock: int=None, verify: bool=False, sign: bool=False,
              send: bool=False, locktime: int=0, version=1):
        """Spawn a new PoB token, uses automatically the burn address of the network."""

        tracked_address = au.burn_address()
        print("Using burn address:", tracked_address)

        return super().deck_spawn(name, tracked_address, multiplier, number_of_decimals, startblock, endblock, version, locktime, verify, sign, send)

    def burn_coins(self, amount: str, from_address: str=Settings.key.address, tx_fee: Decimal=None, change_address: str=None, sign: bool=False, send: bool=False, verify: bool=False, debug: bool=False) -> str:
        """Burn coins with a controlled transaction from the current main address."""

        return super().create_tx(address=au.burn_address(), amount=amount, from_address=from_address, tx_fee=tx_fee, change_address=change_address, sign=sign, send=send, verify=verify, debug=debug)

    def my_burns(self, unclaimed: bool=False, wallet: bool=False, deck: str=None, silent: bool=False, debug: bool=False) -> None:
        """List all burn transactions, of this address or the whole wallet (--wallet option).
           --unclaimed shows only transactions which haven't been claimed yet."""

        return super().my_txes(address=au.burn_address(), unclaimed=unclaimed, deck=deck, wallet=wallet, silent=silent, debug=debug)


    @classmethod
    def deck_list(self):
        '''Prints list of AT decks'''

        ei.run_command(print_deck_list, [d for d in list_decks_by_at_type(provider, c.ID_AT) if d.at_address == au.burn_address()])

    def show_all_burns(self, start: int=None, end: int=None, deckid: str=None, debug: bool=False):
        '''Show all burn transactions of all users. Very slow, use of --start and --end highly recommended.'''
        return super().show_txes(address=au.burn_address(), deckid=deckid, start=start, end=end, debug=debug)
