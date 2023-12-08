import pypeerassets as pa
import pypeerassets.at.constants as c
from prettyprinter import cpprint as pprint
from decimal import Decimal
from pacli.provider import provider
from pacli.config import Settings
from pacli.tui import print_card_list
import pacli.extended_utils as eu
import pacli.extended_interface as ei
import pacli.extended_commands as ec
import pacli.config_extended as ce
import pacli.token_commands as tc
from pypeerassets.at.dt_misc_utils import list_decks_by_at_type


class Token:

    def balance(self,
                param1: str=None,
                param2: str=None,
                token_type: str=None,
                holders: bool=False,
                all: bool=False,
                common: bool=False,
                wallet: bool=False,
                keyring: bool=False,
                no_labels: bool=False,
                only_labels: bool=False,
                silent: bool=False,
                debug: bool=False):
        """List the token balances of an address, the whole wallet or all users.

        Usage options:

        pacli token balance DECK [ADDRESS] [--wallet]

        Shows balances of a single token of all addresses (--wallet flag) or only the specified address.

        pacli token balance [ADDRESS] --all [--wallet]

        Shows balances of all tokens, either on the specified address or on the whole wallet (with --wallet flag).

        pacli token balance DECK --holders

        Shows all balances of all holders of a token (addresses with cards of this deck). Similar to 'card balances' command.


        Other options and flags:

        --token_type: In combination with the second option, limit results to one of the following token types: PoD, PoB or AT (case-insensitive).
        --advanced: In combination with the second option, shows balances of all tokens in JSON format.
        --only_labels: In combination with the first or second option, don't show the addresses, only the labels.
        --no_labels: In combination with the first or second option, don't show the labels, only the addresses.
        --keyring: In combination with the first or second option, use an address stored in the keyring.
        --silent: Suppresses information about the deck when a label is used.
        --debug: Display debug info."""

        # get_deck_type is since 12/23 a function in the constants file retrieving DECK_TYPE enum for common abbreviations.
        # allowed are: "at" / "pob", "dt" / "pod" (in all capitalizations)


        if holders and param1:
            from pacli.__main__ import Card
            deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", param1, silent=silent)
            return Card().balances(deckid)
        elif (all or common):
            if (wallet, param1) == (None, None):
                param1 = Settings.key.address
            # with --all flag, advanced mode is called;
            # with --common flag, advanced mode is set to False (table output similar to address balances)
            address = ec.process_address(param1)
            deck_type = c.get_deck_type(token_type.lower()) if token_type is not None else None
            return tc.all_balances(address=address, wallet=wallet, keyring=keyring, no_labels=no_labels, only_tokens=True, advanced=all, only_labels=only_labels, deck_type=deck_type, silent=silent, debug=debug)
        elif param1:
            address = ec.process_address(param2) if param2 is not None else Settings.key.address
            deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", param1, silent=silent)
            return tc.single_balance(deck=deckid, address=address, wallet=wallet, keyring=keyring, no_labels=no_labels, silent=silent)

        else:
            ei.print_red("You have to provide a deck for this command, or use the --all/--common option.")


    '''def list(self, deck: str, silent: bool=False, valid: bool=False):
        """List all cards of a deck (with support for deck labels).
        --silent suppresses information about the deck when a label is used.
        --valid only shows valid cards according to Proof-of-Timeline rules,
        i.e. where no double spend has been recorded."""

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent) if deck else None

        if valid:
            deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
            cards = pa.find_all_valid_cards(provider, deck)
            valid_cards = pa.protocol.DeckState(cards).valid_cards
            print_card_list(valid_cards)
        else:
            from pacli.__main__ import Card
            return Card().list(deckid)''' # OK, moved to ExtCard / extended_main

    def init_deck(self, deck: str, silent: bool=False):
        """Initializes a standard deck, an AT or a PoB deck and imports its P2TH keys into node.
           Mandatory to be able to use the deck with pacli.
           NOTE: dPoD decks have an own command `podtoken init_deck`

           Usage:

           pacli token init_deck DECK

           Flags:

           --silent: Suppress output."""

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent) if deck else None
        return ei.run_command(eu.init_deck, Settings.network, deckid, silent=silent)


    # Enhanced transfer commands

    '''def simple_transfer(self, deck: str, receiver: str, amount: str, locktime: int=0, change: str=Settings.change, sign: bool=True, send: bool=True, silent: bool=False, debug: bool=False):
        """Transfer tokens/cards to a single receiver.
        --sign and --send are set true by default."""


        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent)
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        change_address = ec.process_address(change)

        return ei.run_command(eu.advanced_card_transfer, deck,
                                 amount=[Decimal(str(amount))],
                                 receiver=[receiver],
                                 change_address=change_address,
                                 locktime=locktime,
                                 sign=sign,
                                 send=send,
                                 debug=debug
                                 )''' # OK, integrated into transfer (ex multi_transfer)


    def transfer(self, deck: str, receiver: str, amount: str, change: str=Settings.change, sign: bool=True, send: bool=True, verify: bool=False, silent: bool=False, debug: bool=False):
        """Transfer tokens/cards to one or multiple receivers in a single transaction.

        Usage:

        pacli token transfer DECK RECEIVER AMOUNT

        Transfer AMOUNT of a token of deck DECK to a single receiver RECEIVER.

        pacli token transfer DECK [RECEIVER1, RECEIVER2, ...] [AMOUNT1, AMOUNT2, ...]

        Transfer to multiple receivers. AMOUNT1 goes to RECEIVER1 and so on.
        The brackets are mandatory, but they don't have to be escaped.

        Options and flags:
        --change: Specify a change address.
        --sign: Signs the transaction (True by default, use --send=False for a dry run)
        --send: Sends the transaction (True by default, use --send=False for a dry run)
        --verify: Verify transaction with Cointoolkit.
        --silent: Suppress output and printout in a script-friendly way.
        --debug: Show additional debug info.
        """
        # NOTE: This is not a wrapper of card transfer, so the signature errors from P2PK are also fixed.

        if type(receiver) == str:
            receiver = [receiver]
        if type(amount) != list:
            amount = [Decimal(str(amount))]
        try:
            assert (type(receiver), type(amount)) == (list, list)
        except AssertionError:
            ei.print_red("The receiver and amount parameters have to be strings/numbers or lists.")


        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent)
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        #transfers = transferlist.split(";")
        #receivers = [transfer.split(":")[0] for transfer in transfers]
        #amounts = [Decimal(str(transfer.split(":")[1])) for transfer in transfers]
        change_address = ec.process_address(change)

        if not silent:
            print("Sending tokens to the following receivers:", receiver)

        return ei.run_command(eu.advanced_card_transfer, deck,
                                 amount=amount,
                                 receiver=receiver,
                                 change_address=change_address,
                                 locktime=0,
                                 asset_specific_data=None,
                                 sign=sign,
                                 send=send,
                                 verify=verify,
                                 debug=debug
                                 )


    # more general Token commands


    '''def _all_balances(self, address: str=Settings.key.address, wallet: bool=False, keyring: bool=False, no_labels: bool=False, only_tokens: bool=False, advanced: bool=False, only_labels: bool=False, deck_type: int=None, silent: bool=False, debug: bool=False):
        """Shows all token/card balances on this address.
        --wallet flag allows to show all balances of addresses
        which are part of the wallet."""


        # TODO deck_type is not userfriendly, perhaps increase friendlyness to allow calling that on CLI
        # with a human_readable type.
        if not advanced:
            # the quick mode displays only default PoB and PoD decks
            decks = [pa.find_deck(provider, self.POB_DEFAULT[Settings.network], Settings.deck_version, Settings.production),
                     pa.find_deck(provider, self.POD_DEFAULT[Settings.network], Settings.deck_version, Settings.production)]

        elif deck_type is not None:
            decks = list_decks_by_at_type(provider, deck_type)
        else:
            decks = pa.find_all_valid_decks(provider, Settings.deck_version,
                                            Settings.production)

        if wallet:
            if not no_labels:
                labeldict = ec.get_labels_and_addresses(keyring=keyring)

        if only_tokens:
            balances = {}
        else:
            # coin balance
            coin_balances = {}
            if wallet:
                labeled_addresses = labeldict.values()
            else:
                labeled_addresses = [address]


            for addr in labeled_addresses:
                balance = float(str(provider.getbalance(addr)))
                coin_balances.update({addr: balance})

            if advanced and (not no_labels):
                coin_balances = ei.format_balances(coin_balances, labeldict, suppress_addresses=only_labels)

            balances = { Settings.network : coin_balances }

        # NOTE: default view needs no deck labels
        if (advanced and not no_labels) and (not silent):
            deck_labels = ce.get_config()["deck"]
        else:
            deck_labels = None

        for deck in decks:
            if debug:
                print("Checking deck:", deck.id)
            try:
                if wallet:
                    # Note: returns a dict, structure of balances var is thus different.
                    balance = eu.get_wallet_token_balances(deck)

                    if advanced and (not no_labels) and (not silent):
                        balance = ei.format_balances(balance, labeldict, suppress_addresses=only_labels)
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
                    if only_labels:
                        balances.update({deck_label : balance})
                    else:
                        balances.update({"{} ({})".format(deck_label, deck.id) : balance})
                else:
                    balances.update({deck.id : balance})

        if silent:
            print(balances)
        elif advanced or (not wallet):
            pprint(balances)
        else:
            ei.print_default_balances_list(balances, labeldict, decks, network_name=Settings.network)'''


    '''def __single_balance(self, deck: str, address: str=Settings.key.address, wallet: bool=False, keyring: bool=False, no_labels: bool=False, silent: bool=False):
        """Shows the balance of a single token (deck) on the current main address or another address.
        --wallet flag allows to show all balances of addresses
        which are part of the wallet."""
        # TODO: also affected by wallet issue.

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent) if deck else None
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

        if wallet:
            wallet_addresses = list(eu.get_wallet_address_set())
            # addrdict = { address : label for label, address in ec.get_labels_and_addresses(keyring=keyring).items() }
            labeldict = ec.get_labels_and_addresses(keyring=keyring)
            balances = eu.get_wallet_token_balances(deck)


            if (not no_labels) and (not silent):
                balances = ei.format_balances(balances, labeldict)


            if silent:
                print(balances)
            else:
                pprint(balances)
                return
        else:
            balance = eu.get_address_token_balance(deck, address)

            if silent:
                print({address : balance})
            else:
                pprint({address : balance})'''
