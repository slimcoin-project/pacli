import pacli.dex_utils as dxu
import pacli.extended_interface as ei
import pacli.extended_utils as eu
import pypeerassets as pa
import pacli.extended_commands as ec
from decimal import Decimal
from pacli.provider import provider
from pacli.config import Settings

class Dex:

    @classmethod
    def lock(self,
            deck: str,
            amount: int,
            lock: int,
            lockaddr: str,
            receiver: str=None,
            blockheight: bool=False,
            addrtype: str="p2pkh",
            change: str=Settings.change,
            wait_for_confirmation: bool=False,
            sign: bool=False,
            send: bool=False,
            quiet: bool=False):
        """Locks a number of tokens on the receiving address.
        By default, you specify the number of blocks to lock the tokens; with --height you specify the final block height.
        Transfers are only permitted to the Lock Address. This is the condition to avoid scams in the DEX.
        Card default receiver is the sender (the current main address).

        Usage:

        dex lock DECK AMOUNT LOCK_BLOCKS LOCK_ADDRESS [RECEIVER] [--sign --send]

        Args:

          sign: Sign the transaction.
          send: Send the transaction.
          blockheight: Lock to an absolute block height (instead of a relative number of blocks).
          receiver: Specify another receiver (can be only one)
          addrtype: Address type (default: p2pkh)
          change: Specify a custom change address.
          wait_for_confirmation: Wait for the first confirmation of the transaction and display a message.
          quiet: Output only the transaction in hexstring format (script-friendly).
         """

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, quiet=quiet)
        change_address = ec.process_address(change)
        if receiver is None:
            receiver_address = Settings.key.address
        else:
            receiver_address = ec.process_address(receiver)
        return ei.run_command(dxu.card_lock, deckid=deckid, amount=amount, lock=lock, lockaddr=lockaddr, addrtype=addrtype, absolute=blockheight, change_address=change_address, receiver=receiver_address, sign=sign, send=send, confirm=wait_for_confirmation, txhex=quiet)

    @classmethod
    def exchange(self,
                 deck: str,
                 partner_address: str,
                 partner_input: str,
                 card_amount: str,
                 coin_amount: str,
                 coinseller_change_address: str=None,
                 label: str=None,
                 quiet: bool=False,
                 sign: bool=False):
        """Creates a new exchange transaction, signs it partially and outputs it in hex format to be submitted to the exchange partner.

        Usage:

        pacli dex exchange DECK PARTNER_ADDRESS PARTNER_INPUT CARD_AMOUNT COIN_AMOUNT

        PARTNER_ADDRESS and PARTNER_INPUT come from your exchange partner (see manual)

        Args:

          sign: Sign the transaction.
          coinseller_change_address: Specify a change address of the coin seller (default: sender address)
          label: Specify a label to save the transaction hex string with.
          quiet: Suppress output.
        """

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, quiet=quiet)
        return ei.run_command(dxu.build_coin2card_exchange, deckid, partner_address, partner_input, Decimal(str(card_amount)), Decimal(str(coin_amount)), sign=sign, coinseller_change_address=coinseller_change_address, save=label)

    @classmethod
    def finalize_exchange(self, txstr: str, send: bool=True, confirm: bool=False):
        """Signs and broadcasts an exchange transaction.

        Usage:

        pacli dex finalize_exchange TX_HEXSTRING

        TX_HEXSTRING is the partially signed transaction as an hex string.

        Args:

          send: Sends the transaction
          confirm: Waits for the transaction to confirm.
        """
        return ei.run_command(dxu.finalize_coin2card_exchange, txstr, send=send, confirm=confirm)

    @classmethod
    def list_locks(self, deck: str, blockheight: int=None, raw: bool=False, quiet: bool=False):
        """Shows all current locks of a deck.

        Usage:

        pacli dex list_locks DECK

        Args:

          blockheight: Specify a block height to show locks at (BUGGY). To be used as a positional argument (flag name not necessary).
          raw: Don't prettyprint the lock dictionary
          quiet: Suppress output.
        """
        # TODO: blockheight seems not to work.

        blockheight = provider.getblockcount() if blockheight is None else blockheight
        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, quiet=quiet)
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        cards = pa.find_all_valid_cards(dxu.provider, deck)
        state = pa.protocol.DeckState(cards, cleanup_height=blockheight)

        if raw is True:
            return state.locks
        else:
            return dxu.prettyprint_locks(state.locks, blockheight)

    @classmethod
    def select_coins(self, amount, address=Settings.key.address, utxo_type="pubkeyhash"):
        """Prints out all suitable utxos for an exchange transaction.

        Usage:

        pacli dex select_coins AMOUNT [ADDRESS]

        If ADDRESS is not given, the current main address is used.

        Args:

          address: Alternative address to show suitable UTXOs. To be used as a positional argument (flag name not necessary).
          utxo_type: Specify a different UTXO type (default: pubkeyhash)
        """

        addr = ec.process_address(address)
        return ei.run_command(dxu.select_utxos, minvalue=amount, address=addr, utxo_type=utxo_type)

