import pypeerassets as pa
import pypeerassets.at.constants as c
from prettyprinter import cpprint as pprint
from pypeerassets.at.mutable_transactions import TransactionDraft
from pypeerassets.pautils import exponent_to_amount
from decimal import Decimal
from pacli.provider import provider
from pacli.config import Settings
from pacli.tui import print_deck_list
import pacli.extended_utils as eu
import pacli.extended_interface as ei
import pacli.at_utils as au
import pacli.extended_commands as ec
from pypeerassets.at.dt_misc_utils import list_decks_by_at_type
from pacli.token_extended import Token

class ATToken(Token):


    def create_tx(self, address: str, amount: str, tx_fee: Decimal=None, change: str=Settings.change, sign: bool=True, send: bool=True, confirm: bool=False, verify: bool=False, silent: bool=False, debug: bool=False) -> str:
        '''Creates a simple transaction from an address (default: current main address) to another one.'''

        change_address = ec.process_address(change)

        dec_amount = Decimal(str(amount))
        rawtx = ei.run_command(au.create_simple_transaction, amount=dec_amount, dest_address=address, change_address=change_address, debug=debug)

        return ei.run_command(eu.finalize_tx, rawtx, verify, sign, send, confirm=confirm, silent=silent, debug=debug)

    """def show_txes(self, address: str=None, deckid: str=None, start: int=0, end: int=None, silent: bool=False, debug: bool=False, burns: bool=False) -> None:
        '''Show all transactions to a tracked address between two block heights (very slow!).'''

        if burns:
             print("Using burn address.")
             address = burn_address(network_name=provider.network)

        txes = ei.run_command(au.show_txes_by_block, tracked_address=address, deckid=deckid, startblock=start, endblock=end, silent=silent, debug=debug)
        pprint(txes)

    def my_txes(self, address: str=None, deck: str=None, unclaimed: bool=False, wallet: bool=False, no_labels: bool=False, keyring: bool=False, silent: bool=False, debug: bool=False) -> None:
        '''Shows all transactions from your wallet to the tracked address.'''

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent) if deck else None
        sender = Settings.key.address if not wallet else None
        txes = ei.run_command(au.show_wallet_dtxes, tracked_address=address, deckid=deckid, unclaimed=unclaimed, sender=sender, no_labels=no_labels, keyring=keyring, silent=silent, debug=debug)

        if not silent:
            pprint(txes)
        else:
            print(txes)""" # moved to at_utils

    @classmethod
    def claim(self, deck_str: str, txid: str, receivers: list=None, amounts: list=None,
              locktime: int=0, payto: str=None, payamount: str=None, change: str=Settings.change,
              confirm: bool=False, silent: bool=False, force: bool=False,
              verify: bool=False, sign: bool=True, send: bool=True, debug: bool=False) -> str:
        '''Claims tokens for a transaction to a tracked address.
        The --payamount and --payto options enable a single payment
        to another address in the same transaction.'''
        # NOTE: amounts is always a list! It is for cases where the claimant wants to send tokens to different addresses.

        if payamount:
            if payto:
                payto = ec.process_address(payto)
            else:
                print("Use --payamount together with --payto to designate a receiver of the payment.\nNo transaction was created.")
                return None

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck_str)
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        dec_payamount = Decimal(str(payamount)) if payamount else None
        change_address = ec.process_address(change)

        asset_specific_data, amount, receiver = ei.run_command(au.create_at_issuance_data, deck, txid, Settings.key.address, amounts=amounts, receivers=receivers, payto=payto, payamount=dec_payamount, debug=debug, force=force)

        return ei.run_command(eu.advanced_card_transfer, deck,
                                 amount=amount,
                                 receiver=receiver,
                                 locktime=locktime,
                                 change_address=change_address,
                                 asset_specific_data=asset_specific_data,
                                 sign=sign,
                                 send=send,
                                 verify=verify,
                                 confirm=confirm,
                                 debug=debug
                                 )

    @classmethod
    def deck_spawn(self, name, tracked_address, multiplier: int=1, number_of_decimals: int=2, startblock: int=None,
              endblock: int=None, change: str=Settings.change, version=1, locktime: int=0, verify: bool=False,
              confirm: bool=False, sign: bool=False, send: bool=False) -> None:
        '''Spawns a new AT deck.'''

        change_address = ec.process_address(change)
        asset_specific_data = ei.run_command(eu.create_deckspawn_data, c.ID_AT, at_address=tracked_address, multiplier=multiplier, startblock=startblock, endblock=endblock)

        return ei.run_command(eu.advanced_deck_spawn, name=name, number_of_decimals=number_of_decimals,
               issue_mode=0x01, locktime=locktime, change_address=change_address, asset_specific_data=asset_specific_data,
               confirm=confirm, verify=verify, sign=sign, send=send)


    def deck_info(self, deck: str) -> None:
        '''Prints AT-specific deck info.'''

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck)
        ei.run_command(au.at_deckinfo, deckid)

    @classmethod
    def deck_list(self) -> None:
        '''Prints list of AT decks'''

        ei.run_command(print_deck_list, list_decks_by_at_type(provider, c.ID_AT))

    # Moved to extended_utils, is called from Transaction class (transaction list --claims)
    """def show_claims(self, deck_str: str, address: str=None, wallet: bool=False, full: bool=False, param: str=None):
        '''Shows all valid claim transactions for a deck, rewards and tracked transactions enabling them.'''

        param_names = {"txid" : "TX ID", "amount": "Token amount(s)", "receiver" : "Receiver(s)", "blocknum" : "Block height"}

        if type(self).__name__ == "PoBToken":
            param_names.update({"donation_txid" : "Burn transaction"})
        else:
            param_names.update({"donation_txid" : "Referenced transaction"})

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck_str)
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        raw_claims = ei.run_command(eu.get_valid_cardissues, deck, input_address=address, only_wallet=wallet)
        claim_txids = set([c.txid for c in raw_claims])
        claims = []

        for claim_txid in claim_txids:
            bundle = [c for c in raw_claims if c.txid == claim_txid]
            claim = bundle[0]
            if len(bundle) > 1:
                for b in bundle[1:]:
                    claim.amount.append(b.amount[0])
                    claim.receiver.append(b.receiver[0])
            claims.append(claim)

        for claim in claims:
            if full:
                pprint(claim.__dict__)

            elif param:
                pprint({ claim.txid : claim.__dict__[param] })
            else:

                claim_dict = {param_names["txid"] : claim.txid,
                              param_names["donation_txid"] : claim.donation_txid,
                              param_names["amount"] : [exponent_to_amount(a, claim.number_of_decimals) for a in claim.amount],
                              param_names["receiver"] : claim.receiver,
                              param_names["blocknum"] : claim.blocknum}
                pprint(claim_dict)

    def all_my_balances(self, address: str=Settings.key.address, wallet: bool=False, keyring: bool=False, no_labels: bool=False, only_labels: bool=False, silent: bool=False, advanced: bool=False, debug: bool=False):
        '''Shows all valid AT/PoB token balances, ignoring other deck types.'''

        return super().all_my_balances(address=address, deck_type=c.ID_AT, wallet=wallet, keyring=keyring, no_labels=no_labels, advanced=advanced, only_labels=only_labels, silent=silent, debug=debug)"""




class PoBToken(ATToken):
    # bundles all PoB-specific functions.

    def deck_spawn(self, name, multiplier: int=1, number_of_decimals: int=2, startblock: int=None,
              endblock: int=None, change: str=Settings.change, verify: bool=False, sign: bool=True,
              confirm: bool=False, send: bool=True, locktime: int=0, version=1):
        """Spawn a new PoB token, uses automatically the burn address of the network."""

        tracked_address = au.burn_address()
        print("Using burn address:", tracked_address)

        return super().deck_spawn(name, tracked_address, multiplier, number_of_decimals, change=change, startblock=startblock, endblock=endblock, version=version, locktime=locktime, confirm=confirm, verify=verify, sign=sign, send=send)

    def burn_coins(self, amount: str, tx_fee: Decimal=None, change: str=Settings.change, confirm: bool=False, sign: bool=True, send: bool=True, verify: bool=False, silent: bool=False, debug: bool=False) -> str:
        """Burn coins with a controlled transaction from the current main address."""

        return super().create_tx(address=au.burn_address(), amount=amount, tx_fee=tx_fee, change=change, sign=sign, send=send, confirm=confirm, verify=verify, silent=silent, debug=debug)

    '''def my_burns(self, deck: str=None, unclaimed: bool=False, wallet: bool=False, no_labels: bool=False, keyring: bool=False, silent: bool=False, debug: bool=False) -> None:
        """List all burn transactions, of this address or the whole wallet (--wallet option).
           --unclaimed shows only transactions which haven't been claimed yet."""

        return super().my_txes(address=au.burn_address(), unclaimed=unclaimed, deck=deck, wallet=wallet, no_labels=no_labels, keyring=keyring, silent=silent, debug=debug)'''


    @classmethod
    def deck_list(self):
        '''Prints list of AT decks'''

        ei.run_command(print_deck_list, [d for d in list_decks_by_at_type(provider, c.ID_AT) if d.at_address == au.burn_address()])

    """def show_all_burns(self, start: int=0, end: int=None, deckid: str=None, silent: bool=False, debug: bool=False):
        '''Show all burn transactions of all users. Very slow, use of --start and --end highly recommended.'''
        return super().show_txes(address=au.burn_address(), deckid=deckid, start=start, end=end, silent=silent, debug=debug)"""
