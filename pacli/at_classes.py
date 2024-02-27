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
from pacli.token_classes import Token

class ATToken(Token):


    def create_tx(self, address: str, amount: str, tx_fee: Decimal=None, change: str=Settings.change, sign: bool=True, send: bool=True, wait_for_confirmation: bool=False, verify: bool=False, quiet: bool=False, debug: bool=False) -> str:
        '''Creates a simple transaction from an address (default: current main address) to another one.
        The purpose of this command is to be able to use the address labels from Pacli,
        above all to make fast transactions to a tracked address of an AT token.

        Usage:
        pacli attoken create_tx ADDRESS AMOUNT

        Args:

          tx_fee: Specify a transaction fee.
          change: Specify a change address.
          sign: Sign the transaction (True by default).
          send: Send the transaction (True by default).
          wait_for_confirmation: Wait and display a message until the transaction is confirmed.
          verify: Verify transaction with Cointoolkit.
          quiet: Suppress output and print it out in a script-friendly way.
          debug: Show additional debug information.'''
        # TODO: this could benefit from a deck parameter, so you could automatically send to the deck's tracked address.

        change_address = ec.process_address(change)

        dec_amount = Decimal(str(amount))
        rawtx = ei.run_command(au.create_simple_transaction, amount=dec_amount, dest_address=address, change_address=change_address, debug=debug)

        return ei.run_command(eu.finalize_tx, rawtx, verify, sign, send, confirm=wait_for_confirmation, quiet=quiet, debug=debug)


    @classmethod
    def claim(self, deck_str: str, txid: str, receivers: list=None, amounts: list=None,
              locktime: int=0, payto: str=None, payamount: str=None, change: str=Settings.change,
              wait_for_confirmation: bool=False, quiet: bool=False, force: bool=False,
              verify: bool=False, sign: bool=True, send: bool=True, debug: bool=False) -> str:
        '''Claims the token reward for a burn transaction (PoB tokens) or a transaction to a tracked address (AT tokens) referenced by a transaction ID.

        Usage options:

        pacli [pobtoken|attoken] claim DECK TXID

        Claim the tokens and store them on the current main address, which has to be the sender of the rewarded transaction.
        TXID is the transaction ID to reference the rewarded transaction (e.g. burn transaction, donation or ICO payment).

        pacli [pobtoken|attoken] claim DECK TXID --payto=ADDRESS --payamount=AMOUNT

        Claim the tokens and make a payment with the issued tokens in the same transaction to one specific address.

        pacli [pobtoken|attoken] claim DECK TXID -r [ADDR1, ADDR2, ...] -a [AM1, AM2, ...]

        Claim the tokens and make a payment with the issued tokens to multiple receivers (put the lists into brackets)

        Args:

          locktime: Lock the transaction until a block or a time.
          tx_fee: Specify a transaction fee.
          change: Specify a change address.
          sign: Sign the transaction (True by default).
          send: Send the transaction (True by default).
          wait_for_confirmation: Wait and display a message until the transaction is confirmed.
          verify: Verify transaction with Cointoolkit.
          payto: Pay to a single address (see above).
          payamount: Pay a single amount (see above).
          amounts: List of amounts (see above) to be paid to multiple receivers.
          receivers: List of receivers (see above).
          quiet: Suppress output and print it out in a script-friendly way.
          debug: Show additional debug information.
          force: Create the transaction even if the reward does not match the transaction (only for debugging!).'''

        if payamount is not None:
            if payto is not None:
                payto = ec.process_address(payto)
            else:
                print("Use --payamount together with --payto to designate a receiver of the payment.\nNo transaction was created.")
                return None

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck_str)
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        dec_payamount = Decimal(str(payamount)) if (payamount is not None) else None
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
                                 confirm=wait_for_confirmation,
                                 debug=debug
                                 )

    @classmethod
    def deck_spawn(self, name, tracked_address, multiplier: int=1, number_of_decimals: int=2, from_block: int=None,
              end_block: int=None, change: str=Settings.change, locktime: int=0, verify: bool=False,
              wait_for_confirmation: bool=False, sign: bool=True, send: bool=True) -> None:
        '''Spawns a new AT deck.

        Usage:

        pacli attoken deck_spawn NAME TRACKED_ADDRESS

        Args:

          multiplier: Specify a multiplier for the reward..
          number_of_decimals: Specify the number of decimals of the token.
          from_block: Specify a start block to track transactions from.
          end_block: Specify an end block to track transactions.
          tx_fee: Specify a transaction fee.
          change: Specify a change address.
          sign: Sign the transaction (True by default).
          send: Send the transaction (True by default).
          wait_for_confirmation: Wait and display a message until the transaction is confirmed.
          verify: Verify transaction with Cointoolkit.'''


        change_address = ec.process_address(change)
        asset_specific_data = ei.run_command(eu.create_deckspawn_data, c.ID_AT, at_address=tracked_address, multiplier=multiplier, startblock=from_block, endblock=end_block)

        return ei.run_command(eu.advanced_deck_spawn, name=name, number_of_decimals=number_of_decimals,
               issue_mode=0x01, locktime=locktime, change_address=change_address, asset_specific_data=asset_specific_data,
               confirm=wait_for_confirmation, verify=verify, sign=sign, send=send)


class PoBToken(ATToken):
    # bundles all PoB-specific functions.

    def deck_spawn(self, name, multiplier: int=1, number_of_decimals: int=2, from_block: int=None,
              end_block: int=None, change: str=Settings.change, verify: bool=False, sign: bool=True,
              wait_for_confirmation: bool=False, send: bool=True, locktime: int=0):

        """Spawn a new PoB token, uses automatically the burn address of the network.

        Usage:

        pacli pobtoken deck_spawn NAME

        Args:

          multiplier: Specify a multiplier for the reward..
          number_of_decimals: Specify the number of decimals of the token.
          from_block: Specify a start block to track transactions from.
          end_block: Specify an end block to track transactions.
          tx_fee: Specify a transaction fee.
          change: Specify a change address.
          sign: Sign the transaction (True by default).
          send: Send the transaction (True by default).
          wait_for_confirmation: Wait and display a message until the transaction is confirmed.
          verify: Verify transaction with Cointoolkit."""

        tracked_address = au.burn_address()
        print("Using burn address:", tracked_address)

        return super().deck_spawn(name, tracked_address, multiplier, number_of_decimals, change=change, startblock=from_block, endblock=end_block, locktime=locktime, confirm=wait_for_confirmation, verify=verify, sign=sign, send=send)


    def burn_coins(self, amount: str, tx_fee: Decimal=None, change: str=Settings.change, wait_for_confirmation: bool=False, sign: bool=True, send: bool=True, verify: bool=False, quiet: bool=False, debug: bool=False) -> str:
        """Burn coins with a controlled transaction from the current main address.

        Usage:

        pacli pobtoken burn_coins AMOUNT

        Args:

          tx_fee: Specify a transaction fee.
          change: Specify a change address.
          sign: Sign the transaction (True by default).
          send: Send the transaction (True by default).
          wait_for_confirmation: Wait and display a message until the transaction is confirmed.
          verify: Verify transaction with Cointoolkit.
          quiet: Suppress output and print it out in a script-friendly way.
          debug: Show additional debug information."""

        return super().create_tx(address=au.burn_address(), amount=amount, tx_fee=tx_fee, change=change, sign=sign, send=send, confirm=wait_for_confirmation, verify=verify, quiet=quiet, debug=debug)
