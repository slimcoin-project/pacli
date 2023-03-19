import pacli.dex_utils as dxu
import pypeerassets as pa
from decimal import Decimal
from pacli.provider import provider
from pacli.config import Settings

class Dex:

    @classmethod
    def create_offer(self, deckid: str, amount: int, lock: int, lockaddr: str, addrtype: str="p2pkh", absolute: bool=False, sign: bool=False, send: bool=False):
        # create_offer locks the card on the same address than was sent, thus receiver is Settings.key.address
        return dxu.card_lock(deckid=deckid, amount=amount, lock=lock, lockaddr=lockaddr, addrtype=addrtype, absolute=absolute, sign=sign, send=send)

    @classmethod
    def new_exchange(self, deckid: str, partner_address: str, partner_input: str, card_amount: str, coin_amount: str, coinseller_change_address: str=None, sign: bool=False):
        return dxu.build_coin2card_exchange(deckid, partner_address, partner_input, Decimal(str(card_amount)), Decimal(str(coin_amount)), sign=sign, coinseller_change_address=coinseller_change_address)

    @classmethod
    def finalize_exchange(self, txstr: str, send: bool=False):
        return dxu.finalize_coin2card_exchange(txstr, send=send)

    @classmethod
    def show_locks(self, deckid, raw=False):
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        cards = pa.find_all_valid_cards(dxu.provider, deck)
        state = pa.protocol.DeckState(cards, cleanup_height=provider.getblockcount())
        if raw:
            return state.locks
        else:
            return dxu.prettyprint_locks(state.locks)

    @classmethod
    def select_coins(self, amount, address=None, utxo_type="pubkeyhash"):
        # alternative to get_unspent, prints out all suitable utxos.
        if address is None:
            address = Settings.key.address
        return dxu.select_utxos(minvalue=amount, address=address, utxo_type=utxo_type)

