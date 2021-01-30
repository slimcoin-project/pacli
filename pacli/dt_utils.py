from pypeerassets.at.dt_entities import ProposalTransaction, SignallingTransaction, LockingTransaction, DonationTransaction, VotingTransaction 
from pypeerassets.at.dt_states import ProposalState, DonationState
from pypeerassets.at.transaction_formats import P2TH_MODIFIER
from pypeerassets.at.dt_misc_utils import get_startendvalues, import_p2th_address
from pypeerassets.at.dt_parser_utils import deck_from_tx
from pypeerassets.kutil import Kutil
from time import sleep

def p2th_id_by_type(deck_id, tx_type):
    # THIS IS PRELIMINARY
    # it is a copy of at.protocol.Deck.derived_id, so it's redundant. # TODO: it was modified, adapt derived_id!
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


def check_current_period(provider, proposal, tx_type, dist_round=None, phase=None, wait=False):
    # CLI to check the period (phase/round) of a transaction.
    # Only issues the transaction if it is in the correct period (voting / signalling / locking / donation).

    if tx_type in ("donation", "signalling", "locking"):
        if dist_round is None:
            print("No round provided.")
            return False
        elif tx_type in ("donation", "locking"):
            period = ("donation" , dist_round)
        elif tx_type == "signalling":
            period = ("signalling", dist_round)

    elif tx_type == "voting":
        if phase is None:
            print("No phase provided.")
            return False
        period = ("voting", phase)

    
    # current_period = get_current_period(provider, deck, current_block) # perhaps not needed
    periodvalues = get_startendvalues(provider, proposal, period) # needs to use TrackedTransaction.from_txid.
    startblock = periodvalues["start"]
    endblock = periodvalues["end"]
    startendvalues = "(start: {}, end: {}).".format(startblock, endblock)

    # This loop enables the "wait" option, where the program loops each 15 sec until the period is correctly reached.
    # It will terminate when the block has passed.
    while True:
        current_block = provider.getblockcount()
        print("Current block:", current_block)  

        if startblock <= current_block <= endblock:
            print("Period is correct", startendvalues)
            return True
        else:


            if current_block < startblock:
                print("Period still not reached.", startendvalues)
                if not wait:
                    return False
                sleep(15)
            else:
                print("Period deadline has already passed", startendvalues)
                return False


"""
Original function p2th_id_by_type:
            try:
                int_id = int(self.id, 16)
                derived_id = int_id - P2TH_MODIFIER[tx_type]
                return derived_id.to_bytes(32, "big")
            except KeyError:
                return None
            except OverflowError:
                # TODO: this is a workaround, should be done better!
                # It abuses that the OverflowError only can be raised because number becomes negative
                # So in theory a Proposal can be a high number, and signalling/donationtx a low one.
                max_id = int(b'\xff' * 32, 16)
                new_id = max_id - derived_id # TODO won't work as hex() gives strings!
                return new_id.to_bytes(32, "big")"""

def get_proposal_tx_from_txid(provider, txid):
    ptx = ProposalTransaction.from_txid(txid, provider)
    return ptx

def init_dt_deck(provider, network, deckid):
    for tx_type in ("proposal", "signalling", "locking", "donation", "voting"):
        p2th_id = p2th_id_by_type(deckid, tx_type)
        p2th_addr = Kutil(network=network,
                         privkey=bytearray.fromhex(p2th_id)).address
        print("Importing {} P2TH address: {}".format(tx_type, p2th_addr))
        import_p2th_address(provider, p2th_addr)
    # SDP
    deck = deck_from_tx(deckid, provider)
    if deck.sdp_deck:
        p2th_sdp_addr = Kutil(network=network,
                             privkey=bytearray.fromhex(deck.sdp_deck)).address
        print("Importing SDP P2TH address: {}".format(p2th_sdp_addr))
        import_p2th_address(provider, p2th_sdp_addr)
    print("Done.")

