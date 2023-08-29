import pacli.dex_utils as dxu
import pacli.extended_interface as ei
import pypeerassets as pa
import pacli.extended_commands as ec
from decimal import Decimal
from pacli.provider import provider
from pacli.config import Settings

class Dex:

    @classmethod
    def create_offer(self, deck: str, amount: int, lock: int, lockaddr: str, receiver: str=None, addrtype: str="p2pkh", absolute: bool=False, change: str=Settings.change, confirm: bool=False, sign: bool=False, send: bool=False, silent: bool=False, txhex: bool=False):
        """Locks the card on the receiving address. Card default receiver is the sender (the current main address)."""

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent)
        change_address = ec.process_address(change)
        if receiver is None:
            receiver_address = Settings.key.address
        else:
            receiver_address = ec.process_address(receiver)
        return ei.run_command(dxu.card_lock, deckid=deckid, amount=amount, lock=lock, lockaddr=lockaddr, addrtype=addrtype, absolute=absolute, change_address=change_address, receiver=receiver_address, sign=sign, send=send, confirm=confirm, txhex=txhex)

    @classmethod
    def new_exchange(self, deck: str, partner_address: str, partner_input: str, card_amount: str, coin_amount: str, coinseller_change_address: str=None, save: str=None, silent: bool=False, sign: bool=False):
        """Creates a new exchange transaction, signs it partially and outputs it in hex format to be submitted to the exchange partner."""

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent)
        return ei.run_command(dxu.build_coin2card_exchange, deckid, partner_address, partner_input, Decimal(str(card_amount)), Decimal(str(coin_amount)), sign=sign, coinseller_change_address=coinseller_change_address, save=save)

    @classmethod
    def finalize_exchange(self, txstr: str, send: bool=True, confirm: bool=False):
        """Signs and broadcasts an exchange transaction."""
        return ei.run_command(dxu.finalize_coin2card_exchange, txstr, send=send, confirm=confirm)

    @classmethod
    def show_locks(self, deck: str, raw: bool=False, silent: bool=False):
        """Shows all current locks of a deck."""

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent)
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        cards = pa.find_all_valid_cards(dxu.provider, deck)
        state = pa.protocol.DeckState(cards, cleanup_height=provider.getblockcount())
        if raw:
            return state.locks
        else:
            return dxu.prettyprint_locks(state.locks)

    @classmethod
    def select_coins(self, amount, address=Settings.key.address, utxo_type="pubkeyhash"):
        """Prints out all suitable utxos for an exchange transaction."""

        addr = ec.process_address(address)
        return ei.run_command(dxu.select_utxos, minvalue=amount, address=addr, utxo_type=utxo_type)

