from pypeerassets.at.dt_entities import ProposalTransaction, SignallingTransaction, LockingTransaction, DonationTransaction, VotingTransaction 
from pypeerassets.provider import Provider
from pypeerassets.at.dt_states import ProposalState, DonationState
from pypeerassets.at.transaction_formats import P2TH_MODIFIER, PROPOSAL_FORMAT, TX_FORMATS, getfmt, setfmt
from pypeerassets.at.dt_misc_utils import get_startendvalues, import_p2th_address, create_unsigned_tx, get_donation_state, get_proposal_state
from pypeerassets.at.dt_parser_utils import deck_from_tx, get_proposal_states, get_voting_txes
from pypeerassets.pautils import read_tx_opreturn
from pypeerassets.kutil import Kutil
from pypeerassets.networks import net_query
from pacli.utils import (cointoolkit_verify,
                         signtx,
                         sendtx)
from time import sleep
from decimal import Decimal
from prettyprinter import cpprint as pprint
import itertools, sys, secretstorage, keyring

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

        # We need always to trigger the transaction one block before the begin of the period.
        if (startblock - 1) <= current_block <= (endblock - 1):
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

def init_dt_deck(provider, network, deckid, rescan=True):
    deck = deck_from_tx(deckid, provider)
    for tx_type in ("proposal", "signalling", "locking", "donation", "voting"):
        p2th_addr= deck.derived_p2th_address(tx_type)
        #p2th_addr = Kutil(network=network,
        #                 privkey=bytearray.fromhex(p2th_id)).address
        print("Importing {} P2TH address: {}".format(tx_type, p2th_addr))
        import_p2th_address(provider, p2th_addr)

    # SDP    
    if deck.sdp_deck:
        p2th_sdp_addr = Kutil(network=network,
                             privkey=bytearray.fromhex(deck.sdp_deck)).address
        print("Importing SDP P2TH address: {}".format(p2th_sdp_addr))
        import_p2th_address(provider, p2th_sdp_addr)
    if rescan:
        print("Rescanning ...")
        provider.rescanblockchain()
    print("Done.")

def get_period(provider, proposal_txid, blockheight=None):
    """Provides an user-friendly description of the current period."""
    # MODIFIED to new code scheme A-E
    # tuple: Epoch, Period, Begin_blockheight, End_blockheight 

    if not blockheight:
        blockheight = provider.getblockcount()

    proposal_tx = ProposalTransaction.from_txid(proposal_txid, provider)
    deck = proposal_tx.deck
    subm_epoch_height = proposal_tx.epoch * deck.epoch_length
    if blockheight < subm_epoch_height:
        return ("A", 0, 0, subm_epoch_height - 1)
    # TODO: Does not take into account ProposalModifications.
    proposal_state = ProposalState(provider=provider, first_ptx=proposal_tx, valid_ptx=proposal_tx)
    if blockheight < proposal_state.dist_start:
        return ("A", 1, subm_epoch_height, proposal_state.dist_start - 1)
    secp_1_end = proposal_state.dist_start + proposal_state.security_periods[0]
    if blockheight < secp_1_end:
        return ("B", 0, proposal_state.dist_start, secp_1_end - 1)
    voting_1_end = secp_1_end + proposal_state.voting_periods[0]
    if blockheight < voting_1_end:
        return ("B", 1, secp_1_end, voting_1_end - 1)
    # Slot distribution rounds (Initial phase)
    for rd in range(4):
        rdstart = proposal_state.round_starts[rd]
        rdhalfway = proposal_state.round_halfway[rd]
        if blockheight < rdhalfway:
            return ("B", rd * 10, rdstart, rdhalfway - 1)
        rdend = rdstart + proposal_state.round_lengths[0]
        if blockheight < rdend:
            return ("B", rd * 10 + 1, rdhalfway, rdend - 1)
    # Intermediate phase (working)
    startphase2 = proposal_state.end_epoch * deck.epoch_length ### ? last one missed
    if blockheight < startphase2:
        return ("C", 0, rdend, startphase2 - 1)
    # Phase 2
    secp_2_end = startphase2 + proposal_state.security_periods[1]
    if blockheight < secp_2_end:
        return ("D", 0, startphase2, secp_2_end - 1)
    voting_2_end = secp_2_end + proposal_state.voting_periods[0]
    if blockheight < voting_2_end:
        return ("D", 1, secp_2_end, voting_2_end - 1)
    release_end = voting_2_end + proposal_state.release_period
    if blockheight < release_end:
        return ("D", 1, voting_2_end, release_end - 1)
    # Slot distribution rounds (Final phase)
    for rd in range(4, 8):
        rdstart = proposal_state.round_starts[rd]
        rdhalfway = proposal_state.round_halfway[rd]
        if blockheight < rdhalfway:
            return ("D", rd * 10, rdstart, rdhalfway - 1)
        rdend = rdstart + proposal_state.round_lengths[1]
        if blockheight < rdend:
            return ("D", rd * 10 + 1, rdhalfway, rdend - 1)
    dist_end = (proposal_state.end_epoch + 1) * deck.epoch_length
    if blockheight < dist_end: # after end of round 7
        return ("E", 0, rdend, dist_end - 1)
    else:
        return ("E", 1, dist_end, None)


def printout_period(period_tuple, show_blockheights=False):
    period = period_tuple[:2]
    if show_blockheights:
       bhs = "(start: {}, end: {})".format(period_tuple[2], period_tuple[3])
    else:
       bhs = ""
    if period == ("A", 0):
        return "Period A0: Before the proposal submission (blockchain is probably not completely synced)." + bhs
    elif period == ("A", 1):
        return "Period A1: Before the distribution start of the Initial Phase." + bhs
    elif period == ("B", 0):
        return "Period B0: Before the distribution start of the Initial Phase (security period)." + bhs
    elif period == ("B", 1):
        return "Period B1: Voting Round 1." + bhs
    elif period[0] == "B":
        if period[1] % 10 == 0:
             return "Period B{}: Initial Slot Distribution, round {} Signalling Phase.".format(period[1], period[1]//10)  + bhs
        else:
             return "Period B{}: Initial Slot Distribution, round {} Locking Phase.".format(period[1], period[1]//10)  + bhs
    elif period == ("C", 0):
        return "Period C0: Working phase (no voting nor slot distribution ongoing)."  + bhs
    elif period == ("D", 0):
        return "Period D0: Before the distribution start of the Final Phase (security period)."  + bhs
    elif period == ("D", 1):
        return "Period D1: Voting Round 2." + bhs
    elif period == ("D", 2):
        return "Period D2: Donation Release Period." + bhs
    elif period[0] == "D":
        if period[1] % 10 == 0:
             return "Period D{}: Final Slot Distribution, round {} Signalling Phase.".format(period[1], period[1]//10) + bhs
        else:
             return "Period D{}: Final Slot Distribution, round {} Donation Phase.".format(period[1], period[1]//10) + bhs
    elif period == ("E", 0):
        return "Period E0. Proposer Issuance Period" + bhs
    elif period == ("E", 1):
        return "Period E1. All distribution phases concluded." + bhs


def get_proposal_state_periods(provider, deckid, block):
    result = {}
    pstates = get_proposal_states(provider, deck_from_tx(deckid, provider))
    #print(pstates)
    for proposal_txid in pstates:
        ps = pstates[proposal_txid]
         
        period = get_period(provider, proposal_txid, blockheight=block)
        try:
            result[period].append(proposal_txid)
        except KeyError:
            result.update({period : [proposal_txid] })
    return result

def spinner(duration):
    '''Prints a "spinner" for a defined duration in seconds.'''

    animation = [
    "‐          ",
    " ‑         ",
    "  ‒        ",
    "   –       ",
    "    —      ",
    "     ―     ",
    "      —    ",
    "       –   ",
    "        ‒  ",
    "         ‑ ",
    "          ‐",
    "         ‑ ",
    "        ‒  ",
    "       –   ",
    "      —    ",
    "     ―     ",
    "   –       ",
    "  ‒        ",
    " ‑         ",
    "‐          ",
    ]

    spinner = itertools.cycle(animation)
    for i in range(duration * 20):
        sys.stdout.write(next(spinner))   # write the next character
        sys.stdout.flush()                # flush stdout buffer (actual character display)
        sys.stdout.write('\b\b\b\b\b\b\b\b\b\b\b') # erase the last written chars
        sleep(0.1)

def get_deckid_from_proposal(provider, proposal_txid):
    try:
        opreturn_out = provider.getrawtransaction(proposal_txid, 1)["vout"][1]
    except IndexError:
        raise ValueError("Incorrect proposal transaction format.")
    except KeyError:
        print(provider.getrawtransaction(proposal_txid, 1))        

    opreturn = read_tx_opreturn(opreturn_out)
    deck_bytes = getfmt(opreturn, PROPOSAL_FORMAT, "dck")
    return str(deck_bytes.hex())

def get_proposal_info(provider, proposal_txid, state=False):
    proposal_tx = ProposalTransaction.from_txid(proposal_txid, provider)
    if not state:
        return proposal_tx.__dict__

def get_previous_tx_input_data(provider, address, tx_type, proposal_id=None, proposal_tx=None, previous_txid=None, dist_round=None, debug=False):
    # provides the following data: slot, txid and vout of signalling or locking tx, value of input.
    # starts the parser.
    print("Searching for signalling or reserve transaction. Please wait.")
    dstate = get_donation_state(provider, proposal_tx=proposal_tx, tx_txid=previous_txid, address=address, dist_round=dist_round, debug=debug, pos=0)
    if not dstate:
        raise ValueError("No donation states found.")
    if (tx_type == "donation") and (dstate.dist_round < 4):
        
        prev_tx = dstate.locking_tx
    else:
        # reserve tx has always priority in the case a signalling tx also exists in the same donation state.
        if dstate.reserve_tx is not None:
            prev_tx = dstate.reserve_tx
        else:
            prev_tx = dstate.signalling_tx
    
    inputdata = { "txid" : prev_tx.txid, "vout" : 2, "value" : prev_tx.amount, "slot" : dstate.slot }
    return inputdata

def get_donation_states(provider, proposal_id, address=None, debug=False):
    return get_donation_state(provider, proposal_id, address=address, debug=debug) # this returns a list of multiple results

def create_unsigned_trackedtx(provider: Provider, tx_type: str, params: dict, raw_amount=None, dest_address=None, change_address=None, input_address=None, raw_tx_fee=None, raw_p2th_fee=None, cltv_timelock=0, network="tppc", version=1, deckid=None, use_slot=False, new_inputs: bool=False, dist_round: int=None, debug: bool=False):
    # Creates datastring and (in the case of locking/donations) input data in unified way.
       
    network_params = net_query(network)
    coin = int(1 / network_params.from_unit)

    if raw_amount is not None:
        amount = int(Decimal(raw_amount) * coin)
    else:
        amount = None
    tx_fee = int(Decimal(raw_tx_fee) * coin)
    p2th_fee = int(Decimal(raw_p2th_fee) * coin)

    if (deckid is None) and ("prp" in params.keys()):
        proposal = ProposalTransaction.from_txid(params["prp"], provider)
        deck = proposal.deck
    else:
        deck = deck_from_tx(deckid, provider)

    input_data, input_txid, input_vout, input_value = None, None, None, None
    if tx_type in ("donation", "locking"):
        try:
            input_data = get_previous_tx_input_data(provider, input_address, tx_type, proposal_tx=proposal, dist_round=dist_round, debug=debug)
        except ValueError:
            raise Exception("No suitable signalling/reserve transactions found.")
        slot = input_data["slot"]
        # new_inputs enables the automatic selection of new inputs for locking and donation transactions.
        # this can be useful if the previous input is too small for the transaction/p2th fees, or in the case of a
        # ProposalModification.
        if not new_inputs:
            input_txid = input_data["txid"]
            input_vout = input_data["vout"]
            input_value = input_data["value"]
            available_amount = input_value - tx_fee - p2th_fee

        if use_slot:
            amount = min(available_amount, slot)
            print("Using assigned slot:", slot)

    data = setfmt(params, tx_type=tx_type)

    return create_unsigned_tx(deck, provider, tx_type, amount=amount, data=data, address=dest_address, network=network, change_address=change_address, tx_fee=tx_fee, p2th_fee=p2th_fee, input_txid=input_txid, input_vout=input_vout, input_address=input_address, cltv_timelock=cltv_timelock)

def calculate_timelock(provider, proposal_id):
    # returns the number of the block where the working period of the Proposal ends.
    first_proposal_tx = ProposalTransaction.from_txid(proposal_id, provider)
    cltv_timelock = (first_proposal_tx.epoch + first_proposal_tx.epoch_number + 1) * first_proposal_tx.deck.epoch_length
    return cltv_timelock

def finalize_tx(rawtx, verify, sign, send):
    # groups the last steps together

    if verify:
        print(
            cointoolkit_verify(rawtx.hexlify())
             )  # link to cointoolkit - verify

    if sign:
        tx = signtx(rawtx)
        if send:
            pprint({'txid': sendtx(tx)})
        return {'hex': tx.hexlify()}

    return rawtx.hexlify()

def get_all_keyids():
    bus = secretstorage.dbus_init()
    collection = secretstorage.get_default_collection(bus)
    keys = []
    for item in collection.search_items({'application': 'Python keyring library', "service" : "pacli"}):
        # print(item.get_label())
        keys.append(item.get_attributes()["username"])

    return keys

def show_votes_by_address(provider, deckid, address):
    # shows all valid voting transactions from a specific address.
    # Does not show the weight (this would require the parser).
    pprint("Votes cast from address: " + address)
    vote_readable = { b'+' : 'Positive', b'-' : 'Negative' }
    deck = deck_from_tx(deckid, provider)
    vtxes = get_voting_txes(provider, deck)
    for proposal in vtxes:
        for outcome in ("positive", "negative"):
            if outcome not in vtxes[proposal]: 
                continue
            for vtx in vtxes[proposal][outcome]:
                
                inp_txid = vtx.ins[0].txid
                inp_vout = vtx.ins[0].txout
                inp_tx = provider.getrawtransaction(inp_txid, 1)
                addr = inp_tx["vout"][inp_vout]["scriptPubKey"]["addresses"][0]
                if addr == address:
                    pprint("-----------------------------------------")
                    pprint("Vote: " + vote_readable[vtx.vote])
                    pprint("Proposal: " + proposal)
                    pprint("Vote txid: " + vtx.txid)


