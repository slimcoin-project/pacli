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


def check_current_period(provider, proposal_txid, tx_type, dist_round=None, phase=None, wait=False):
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
    periodvalues = get_startendvalues(provider, proposal_txid, period) # needs to use TrackedTransaction.from_txid.
    startblock = periodvalues["start"]
    endblock = periodvalues["end"]
    startendvalues = "(start: {}, end: {}).".format(startblock, endblock)

    # This loop enables the "wait" option, where the program loops each 15 sec until the period is correctly reached.
    # It will terminate when the block has passed.
    while True:
        current_block = provider.getblockcount()
        print("Current block:", current_block)  

        if startblock <= current_block <= endblock:
            print("Period has been reached", startendvalues)
            return True
        else:


            if current_block < startblock:
                print("Period still not reached", startendvalues)
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

def get_period(provider, proposal_txid, blockheight=None):
    """Provides an user-friendly description of the current period."""

    if not blockheight:
        blockheight = provider.getblockcount()

    proposal_tx = ProposalTransaction.from_txid(proposal_txid, provider)
    deck = proposal_tx.deck
    if blockheight < (proposal_tx.epoch * deck.epoch_length):
        return ("A", 0)
    # TODO: Does not take into account ProposalModifications.
    proposal_state = ProposalState(provider=provider, first_ptx=proposal_tx, valid_ptx=proposal_tx)
    if blockheight < proposal_state.dist_start:
        return ("A", 1)
    secp_1 = proposal_state.dist_start + proposal_state.security_periods[0]
    if blockheight < secp_1:
        return ("B", 0)
    voting_1_end = secp_1 + proposal_state.voting_periods[0]
    if blockheight < voting_1_end:
        return ("B", 1)
    # Slot distribution rounds (Initial phase)
    for rd in range(4):
        if blockheight < proposal_state.round_halfway[rd]:
            return ("C", rd * 10)
        rdend = proposal_state.round_starts[rd] + proposal_state.round_lengths[0]
        if blockheight < rdend:
            return ("C", rd * 10 + 1)
    # Intermediate phase (working)
    startphase2 = proposal_state.end_epoch
    if blockheight < startphase2:
        return ("D", 0)
    # Phase 2
    secp_2_end = startphase2 + proposal_state.security_periods[1]
    if blockheight < secp_2_end:
        return ("E", 0)
    voting_2_end = secp_2_end + proposal_state.voting_periods[0]
    if blockheight < voting_2_end:
        return ("E", 1)
    release_end = voting_2_end + proposal_state.release_period
    if blockheight < release_end:
        return ("E", 1)
    # Slot distribution rounds (Final phase)
    for rd in range(4, 8):
        if blockheight < proposal_state.round_halfway[rd]:
            return ("F", rd * 10)
        rdend = proposal_state.round_starts[rd] + proposal_state.round_lengths[1]
        if blockheight < rdend:
            return ("F", rd * 10 + 1)
    if blockheight < (proposal_state.end_epoch + 1) * deck.epoch_length: # after end of round 7
        return ("G", 0)
    else:
        return ("G", 1)


def printout_period(period):
    if period == ("A", 0):
        return "Period A0: Before the proposal submission (blockchain is probably not completely synced)."
    elif period == ("A", 1):
        return "Period A1: Before the distribution start of the Initial Phase."
    elif period == ("B", 0):
        return "Period B0: Before the distribution start of the Initial Phase (security period)."
    elif period == ("B", 1):
        return "Period B1: Voting Round 1."
    elif period[0] == "C":
        if period[1] % 10 == 0:
             return "Period C{}: Initial Slot Distribution, round {} Signalling Phase.".format(period[1], period[1]//10)
        else:
             return "Period C{}: Initial Slot Distribution, round {} Locking Phase.".format(period[1], period[1]//10)
    elif period == ("D", 0):
        return "Period D0: Working phase (no voting nor slot distribution ongoing)."
    elif period == ("E", 0):
        return "Period E0: Before the distribution start of the Final Phase (security period)."
    elif period == ("E", 1):
        return "Period E1: Voting Round 2."
    elif period == ("E", 2):
        return "Period E2: Donation Release Period."
    elif period[0] == "F":
        if period[1] % 10 == 0:
             return "Period F{}: Final Slot Distribution, round {} Signalling Phase.".format(period[1], period[1]//10)
        else:
             return "Period F{}: Final Slot Distribution, round {} Donation Phase.".format(period[1], period[1]//10)
    elif period == ("G", 0):
        return "Period G0. Proposer Issuance Period"
    elif period == ("G", 1):
        return "Period G1. All distribution phases concluded."
