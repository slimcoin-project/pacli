from pypeerassets.transactions import (MutableTransaction,
                                       sign_transaction
                                       )

from pacli.provider import provider
from pacli.config import Settings
#from provider import provider
#from config import Settings


def cointoolkit_verify(hex: str) -> str:
    '''tailor cointoolkit verify URL'''

    base_url = 'https://indiciumfund.github.io/cointoolkit/'
    if provider.network == "peercoin-testnet":
        mode = "mode=peercoin_testnet"
    if provider.network == "peercoin":
        mode = "mode=peercoin"

    return base_url + "?" + mode + "&" + "verify=" + hex


def signtx(rawtx: MutableTransaction) -> str:
    '''sign the transaction'''

    return sign_transaction(provider, rawtx, Settings.key)


def sendtx(signed_tx: MutableTransaction) -> str:
    '''send raw transaction'''

    provider.sendrawtransaction(signed_tx.hexlify())

    return signed_tx.txid

### AT/DT ###

P2TH_MODIFIER = { "donation" : 1, "signalling" : 2, "proposal" : 3 }

def p2th_id_by_type(deck_id, tx_type):
    # THIS IS PRELIMINARY
    # it is a copy of at_protocol.Deck.derived_id, so it's redundant. # TODO: it was modified, adapt derived_id!
    try:
        int_id = int(deck_id, 16)
        derived_id = int_id - P2TH_MODIFIER[tx_type]
        if derived_id >= 0:
            return '{:064x}'.format(derived_id)

        else:
            # TODO: this is a workaround, should be done better! 
            # (Although it's a theorical problem as there are almost no txids > 3"
            # It abuses that the OverflowError only can be raised because number becomes negative
            # So in theory a donation can be a low number, and signalling/proposal a high one.
            print("Overflow")
            max_id = int('ff' * 32, 16)
            new_id = max_id + derived_id # gives actually a lower number than max_id because derived_id is negative.
            return '{:064x}'.format(new_id)

    except KeyError:
        return None





