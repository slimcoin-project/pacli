import pypeerassets as pa
from prettyprinter import cpprint as pprint
from decimal import Decimal
from pacli.provider import provider
from pacli.config import Settings
import pacli.extended_utils as eu
import pacli.extended_interface as ei
import pacli.keystore_extended as ke
import pacli.config_extended as ce


class Token:

    # wrappers around Card commands, with usability fixes.
    # TODO: support address labels once the transition from keystore_extended to Tools is complete

    def balances(self, deck: str, silent: bool=False):
        """List all balances of a deck (with support for deck labels).
        --silent suppresses information about the deck when a label is used."""

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent) if deck else None

        from pacli.__main__ import Card
        return Card().balances(deckid)


    def list(self, deck: str, silent: bool=False):
        """List all cards of a deck (with support for deck labels).
        --silent suppresses information about the deck when a label is used."""

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent) if deck else None

        from pacli.__main__ import Card
        return Card().list(deckid)


    def simple_transfer(self, deck: str, receiver: str, amount: str, locktime: int=0, change: str=Settings.change, sign: bool=True, send: bool=True, silent: bool=False, debug: bool=False):
        """Transfer tokens/cards to a single receiver.
        --sign and --send are set true by default."""
        # Not a wrapper, so the signature errors from P2PK are also fixed.

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent)
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        change_address = ke.process_address(change)

        return ei.run_command(eu.advanced_card_transfer, deck,
                                 amount=[Decimal(str(amount))],
                                 receiver=[receiver],
                                 change_address=change_address,
                                 locktime=locktime,
                                 sign=sign,
                                 send=send,
                                 debug=debug
                                 )


    def multi_transfer(self, deck: str, transferlist: str, change: str=Settings.change, locktime: int=0, asset_specific_data: bytes=None, sign: bool=True, send: bool=True, verify: bool=False, silent: bool=False, debug: bool=False):
        """Transfer tokens/cards to multiple receivers in a single transaction.
        The second argument, the transfer list, contains addresses and amounts.
        Individual transfers are separated by a semicolon (;).
        Address and amount are separated by a colon (:).
        The transfer list has to be put between quotes.
        --sign and --send are true by default."""

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent)
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        transfers = transferlist.split(";")
        receivers = [transfer.split(":")[0] for transfer in transfers]
        amounts = [Decimal(str(transfer.split(":")[1])) for transfer in transfers]
        change_address = ke.process_address(change)

        if not silent:
            print("Sending tokens to the following receivers:", receivers)

        return ei.run_command(eu.advanced_card_transfer, deck,
                                 amount=amounts,
                                 receiver=receivers,
                                 change_address=change_address,
                                 locktime=locktime,
                                 asset_specific_data=asset_specific_data,
                                 sign=sign,
                                 send=send,
                                 verify=verify,
                                 debug=debug
                                 )


    # more general Token commands

    def all_my_balances(self, address: str=Settings.key.address, wallet: bool=False, silent: bool=False, extconf: bool=False, no_labels: bool=False, debug: bool=False):
        """Shows all token/card balances on this address.
        --wallet flag allows to show all balances of addresses
        which are part of the wallet."""

        decks = pa.find_all_valid_decks(provider, Settings.deck_version,
                                        Settings.production)
        balances = {}

        if extconf and (not no_labels):
            deck_labels = ce.get_config()["deck"]
        else:
            deck_labels = None

        if wallet:
            addrdict = ke.get_addresses_and_labels(extconf=extconf)

        for deck in decks:
            if debug:
                print("Checking deck:", deck.id)
            try:
                if wallet:
                    # Note: returns a dict, structure of balances var is thus different.
                    balance = eu.get_wallet_token_balances(deck, addrdict, use_addresses=no_labels)
                else:
                    balance = eu.get_address_token_balance(deck, address)
            except KeyError:
                if debug:
                    print("Warning: Omitting not initialized deck:", deck.id)
                continue
            if balance:
                # support for deck labels
                if (deck_labels) and (deck.id in deck_labels.values()):
                    deck_label = [l for l in deck_labels if deck_labels[l] == deck.id][0]
                    balances.update({deck_label : balance})
                else:
                    balances.update({deck.id : balance})

        if silent:
            return balances
        else:
            pprint(balances)


    def my_balance(self, deck: str, address: str=Settings.key.address, wallet: bool=False, extconf: bool=False, no_labels: bool=False, silent: bool=False):
        """Shows the balance of a single token (deck) on the current main address or another address.
        --wallet flag allows to show all balances of addresses
        which are part of the wallet."""

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent) if deck else None
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

        if wallet:
            addrdict = ke.get_addresses_and_labels(extconf=extconf)
            balances = eu.get_wallet_token_balances(deck, addrdict, use_addresses=no_labels)

            if silent:
                return balances
            else:
                pprint(balances)
                return
        else:
            balance = eu.get_address_token_balance(deck, address)

            if silent:
                return balance
            else:
                pprint({address : balance})
