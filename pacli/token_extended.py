import pypeerassets as pa
from prettyprinter import cpprint as pprint
from decimal import Decimal
from pacli.provider import provider
from pacli.config import Settings
import pacli.extended_utils as eu
import pacli.extended_interface as ei


class Token:

    # wrappers around Card commands, with usability fixes.
    # TODO: support address labels once the transition from keystore_extended to Tools is complete

    def balances(self, deck: str, silent: bool=False):

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent) if deck else None

        from pacli.__main__ import Card
        return Card().balances(deckid)


    def list(self, deck: str, silent: bool=False):

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent) if deck else None

        from pacli.__main__ import Card
        return Card().list(deckid)


    def simple_transfer(self, deck: str, receiver: str, amount: str, locktime: int=0, sign: bool=True, send: bool=True, silent: bool=False, debug: bool=False):
        # Not a wrapper, so the signature errors from P2PK are also fixed.

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent)
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

        return ei.run_command(eu.advanced_card_transfer, deck,
                                 amount=[Decimal(str(amount))],
                                 receiver=[receiver],
                                 locktime=locktime,
                                 sign=sign,
                                 send=send,
                                 debug=debug
                                 )


    def multi_transfer(self, deck: str, transferlist: str, locktime: int=0, asset_specific_data: bytes=None, sign: bool=True, send: bool=True, verify: bool=False, silent: bool=False, debug: bool=False):

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent)
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        transfers = transferlist.split(";")
        receivers = [transfer.split(":")[0] for transfer in transfers]
        amounts = [Decimal(str(transfer.split(":")[1])) for transfer in transfers]

        if not silent:
            print("Sending tokens to the following receivers:", receivers)

        return ei.run_command(eu.advanced_card_transfer, deck,
                                 amount=amounts,
                                 receiver=receivers,
                                 locktime=locktime,
                                 asset_specific_data=asset_specific_data,
                                 sign=sign,
                                 send=send,
                                 verify=verify,
                                 debug=debug
                                 )


    # more general Token commands

    def all_balances(self, address: str=Settings.key.address, silent: bool=False, debug: bool=False):
        # shows all balances on this address
        decks = pa.find_all_valid_decks(provider, Settings.deck_version,
                                        Settings.production)
        balances = {}

        for deck in decks:
            if debug:
                print("checking deck:", deck.id)
            try:
                balance = eu.get_address_token_balance(deck, address)
            except KeyError:
                if not silent:
                    print("Warning: Omitting not initialized deck:", deck.id)
                continue
            if balance > 0:
                balances.update({deck.id : balance})

        if silent:
            return balances
        else:
            pprint(balances)


    def my_balance(self, deck: str, address: str=Settings.key.address, silent: bool=False):
        '''Shows the balance of a token (deck) on the current main address or another address.'''

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent) if deck else None
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        balance = eu.get_address_token_balance(deck, address)

        if silent:
            return balance
        else:
            pprint({address : balance})
