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
                cardholders: bool=False,
                advanced: bool=False,
                wallet: bool=False,
                keyring: bool=False,
                no_labels: bool=False,
                only_labels: bool=False,
                quiet: bool=False,
                debug: bool=False):
        """List the token balances of an address, the whole wallet or all users.

        Usage mode:

        pacli token balance DECK [ADDRESS|-w]

        Shows balances of a single token of all addresses (-w flag) or only the specified address.

        pacli token balance [ADDRESS|-w] -a

        Shows balances of all tokens, either on the specified address or on the whole wallet (with -w flag).

        pacli token balance [ADDRESS|-w]

        Shows balances of all tokens, either on the specified address or on the whole wallet (with -w flag).

        pacli token balance DECK -c

        Shows balances of all holders of a token (addresses with cards of this deck). Similar to 'card balances' command.


        Args:

          token_type: In combination with -a, limit results to one of the following token types: PoD, PoB or AT (case-insensitive).
          advanced: See above. Shows balances of all tokens in JSON format.
          cardholders: Show balances of all holders of cards of a token.
          only_labels: In combination with the first or second option, don't show the addresses, only the labels.
          no_labels: In combination with the first or second option, don't show the labels, only the addresses.
          keyring: In combination with the first or second option, use an address stored in the keyring.
          quiet: Suppresses information about the deck when a label is used.
          debug: Display debug info.
          param1: Deck or address. To be used as a positional argument (flag name not necessary).
          param2: Address. To be used as a positional argument (flag name not necessary).
          wallet: Show balances of all addresses in the wallet."""

        # get_deck_type is since 12/23 a function in the constants file retrieving DECK_TYPE enum for common abbreviations.
        # allowed are: "at" / "pob", "dt" / "pod" (in all capitalizations)
        kwargs = locals()
        del kwargs["self"]
        return ei.run_command(self.__balance, **kwargs)

    def __balance(self,
                param1: str=None,
                param2: str=None,
                token_type: str=None,
                cardholders: bool=False,
                advanced: bool=False,
                wallet: bool=False,
                keyring: bool=False,
                no_labels: bool=False,
                only_labels: bool=False,
                quiet: bool=False,
                debug: bool=False):

        if cardholders is True:
            if param1 is None:
                raise ei.PacliInputDataError("Cardholder mode requires a deck.")
            from pacli.__main__ import Card
            deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", param1, quiet=quiet)
            return Card().balances(deckid)
        elif (param1 is not None) and ((param2 is not None) or (wallet is True)): # single token mode
            address = ec.process_address(param2) if param2 is not None else Settings.key.address
            deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", param1, quiet=quiet)
            return tc.single_balance(deck=deckid, address=address, wallet=wallet, keyring=keyring, no_labels=no_labels, quiet=quiet)
        else:
            # TODO seems like label names are not given in this mode if a an address is given.
            if (wallet, param1) == (False, None):
                param1 = Settings.key.address
            if (not wallet):
                advanced = True
            # without advanced flag, advanced mode is only set if the user requires it.
            address = ec.process_address(param1) if wallet is False else None
            deck_type = c.get_deck_type(token_type.lower()) if token_type is not None else None
            return tc.all_balances(address=address, wallet=wallet, keyring=keyring, no_labels=no_labels, only_tokens=True, advanced=advanced, only_labels=only_labels, deck_type=deck_type, quiet=quiet, debug=debug)


    # Enhanced transfer commands


    def transfer(self, deck: str, receiver: str, amount: str, change: str=Settings.change, sign: bool=True, send: bool=True, verify: bool=False, quiet: bool=False, debug: bool=False):
        """Transfer tokens/cards to one or multiple receivers in a single transaction.

        Usage:

        pacli token transfer DECK RECEIVER AMOUNT

        Transfer AMOUNT of a token of deck DECK to a single receiver RECEIVER.

        pacli token transfer DECK [RECEIVER1, RECEIVER2, ...] [AMOUNT1, AMOUNT2, ...]

        Transfer to multiple receivers. AMOUNT1 goes to RECEIVER1 and so on.
        The brackets are mandatory, but they don't have to be escaped.

        Args:

          change: Specify a change address.
          verify: Verify transaction with Cointoolkit.
          quiet: Suppress output and printout in a script-friendly way.
          debug: Show additional debug information.
          sign: Signs the transaction (True by default, use --send=False for a dry run)
          send: Sends the transaction (True by default, use --send=False for a dry run)
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


        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, quiet=quiet)
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        change_address = ec.process_address(change)

        if not quiet:
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

