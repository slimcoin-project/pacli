from pypeerassets.at.dt_entities import ProposalTransaction, SignallingTransaction, LockingTransaction, DonationTransaction, VotingTransaction, TrackedTransaction, InvalidTrackedTransactionError
from pypeerassets.provider import Provider
from pypeerassets.at.dt_states import ProposalState, DonationState
from pypeerassets.at.transaction_formats import P2TH_MODIFIER, PROPOSAL_FORMAT, TX_FORMATS, getfmt, setfmt
from pypeerassets.at.dt_misc_utils import get_startendvalues, import_p2th_address, create_unsigned_tx, get_donation_state, get_proposal_state
from pypeerassets.at.dt_parser_utils import deck_from_tx, get_proposal_states, get_voting_txes, get_marked_txes
from pypeerassets.pautils import read_tx_opreturn
from pypeerassets.kutil import Kutil
from pypeerassets.protocol import Deck
from pypeerassets.transactions import sign_transaction
from pypeerassets.networks import net_query, PeercoinMainnet, PeercoinTestnet
from pacli.utils import (cointoolkit_verify,
                         signtx,
                         sendtx)
from pacli.keystore import get_key
from time import sleep
from decimal import Decimal
from prettyprinter import cpprint as pprint
import itertools, sys, secretstorage, keyring

def check_current_period(provider, proposal_txid, tx_type, dist_round=None, phase=None, release=False, wait=False):
    # CLI to check the period (phase/round) of a transaction.
    # Only issues the transaction if it is in the correct period (voting / signalling / locking / donation).

    if (dist_round, phase) == (None, None):
         # this allows to get the current phase/round from the transaction data.
         period = get_period(provider, proposal_txid)
         print("Current period:", printout_period(period))
         if tx_type in ("donation", "signalling", "locking"):
             if (period[0] == "B") and (10 <= period[1] < 40):
                 dist_round = period[1] // 10 # period[1] is a multiple of the round
             elif (period[0] == "D") and (10 <= period[1] < 40):
                 dist_round = 4 + (period[1] // 10) # adding the 4 rounds of initial phase
             # if no exact match look for next possible rounds
             elif period[:2] in (("A", 0), ("A", 1), ("B", 0), ("B", 1)):
                 dist_round = 0
             elif period[:2] in (("C", 0), ("D", 0), ("D", 1), ("D", 2)):
                 dist_round = 4
             print("Waiting for slot allocation round", dist_round)
                  
         elif tx_type == "voting":
             if period[:2] in (("A", 0), ("A", 1), ("B", 0), ("B", 1)):
                 phase = 0
             elif (period[:2] in (("C", 0), ("D", 0), ("D", 1))) or (period[0] == "B" and period[1] > 1):
                 phase = 1
             print("Waiting for voting phase", phase)

    if tx_type in ("donation", "signalling", "locking"):
        if dist_round is None:
            if not release:
                print("No round provided.")
                return False
            else:
                period = ("release", 0)
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
    oldblock = 0
    while True:
        current_block = provider.getblockcount()
        if current_block == oldblock:
            sleep(15)
            continue

        # We need always to trigger the transaction one block before the begin of the period.
        if (startblock - 1) <= current_block <= (endblock - 1):
            print("Period has been reached", startendvalues)
            print("Transaction will probably be included in block:", current_block + 1, "- current block:", current_block)
            return True
        else:


            if current_block < startblock:
                print("Period still not reached", startendvalues)
                print("Transaction would probably be included in block:", current_block + 1, "- current block:", current_block)
                if not wait:
                    return False
                sleep(15)
                oldblock = current_block
            else:
                print("Period deadline has already passed", startendvalues)
                print("Current block", current_block)
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

    try:
        proposal_tx = ProposalTransaction.from_txid(proposal_txid, provider)
        deck = proposal_tx.deck
        subm_epoch_height = proposal_tx.epoch * deck.epoch_length
    except: # catches mainly AttributeError and DecodeError
        raise ValueError("Proposal or deck spawn transaction in wrong format.")

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

def get_periods(provider, proposal_txid):
    # this one gets ALL periods from the current proposal, according to the last modification.
    pass


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
    deck = deck_from_tx(deckid, provider)
    try:
       assert deck.at_type == "DT"
    except (AssertionError, AttributeError):
       raise ValueError("Not a DT Proof of Donation deck.")
    
    pstates = get_proposal_states(provider, deck)
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

def create_unsigned_trackedtx(provider: Provider, tx_type: str, params: dict, raw_amount=None, dest_address=None, change_address=None, input_address=None, raw_tx_fee=None, raw_p2th_fee=None, cltv_timelock=0, network=PeercoinTestnet, version=1, deckid=None, use_slot=False, new_inputs: bool=False, dist_round: int=None, reserve: str=None, reserve_address: str=None, force: bool=False, debug: bool=False):
    # Creates datastring and (in the case of locking/donations) input data in unified way.
       
    network_params = net_query(network.shortname) # TODO: revise this! The net_query should not be necessary.
    coin = int(1 / network_params.from_unit)

    if raw_amount is not None:
        amount = int(Decimal(raw_amount) * coin)
    else:
        amount = None
    if reserve is not None:
        reserved_amount = int(Decimal(reserve) * coin)
    else:
        reserved_amount = None

    tx_fee = int(Decimal(raw_tx_fee) * coin)
    p2th_fee = int(Decimal(raw_p2th_fee) * coin)

    if (deckid is None) and ("prp" in params.keys()):
        proposal = ProposalTransaction.from_txid(params["prp"], provider)
        deck = proposal.deck
    else:
        deck = deck_from_tx(deckid, provider)

    input_data, input_txid, input_vout, input_value = None, None, None, None
    if tx_type in ("donation", "locking"):
        if not force:
            try:
                input_data = get_previous_tx_input_data(provider, input_address, tx_type, proposal_tx=proposal, dist_round=dist_round, debug=debug)
            except ValueError:
                raise Exception("No suitable signalling/reserve transactions found.")
            slot = input_data["slot"]
        else:
            # force allows to override the ValueError and slot check.
            if new_inputs and amount:
                use_slot = False
            else:
                raise Exception("If you force, you must provide amount and new_inputs.")

        # new_inputs enables the automatic selection of new inputs for locking and donation transactions.
        # this can be useful if the previous input is too small for the transaction/p2th fees, or in the case of a
        # ProposalModification.

        # MODIFIED: we need to test if the signalling input was still unspent. If not, fallback to the "input address mode".
        if (not new_inputs) and previous_input_unspent(provider, input_data):
            input_txid = input_data["txid"]
            input_vout = input_data["vout"]
            input_value = input_data["value"]
            available_amount = input_value - tx_fee - p2th_fee
        else:
            available_amount = None

        if use_slot:
            if available_amount:
                amount = min(available_amount, slot)
            else:
                amount = slot
            print("Using assigned slot:", Decimal(slot) / coin)
    # print("Amount:", amount)

    data = setfmt(params, tx_type=tx_type)

    return create_unsigned_tx(deck, provider, tx_type, amount=amount, data=data, address=dest_address, network=network, change_address=change_address, tx_fee=tx_fee, p2th_fee=p2th_fee, input_txid=input_txid, input_vout=input_vout, input_address=input_address, cltv_timelock=cltv_timelock, reserved_amount=reserved_amount, reserve_address=reserve_address)

def calculate_timelock(provider, proposal_id):
    # returns the number of the block where the working period of the Proposal ends.

    first_proposal_tx = ProposalTransaction.from_txid(proposal_id, provider)
    # print("first tx info", first_proposal_tx.blockheight, first_proposal_tx.epoch, first_proposal_tx.deck.epoch_length, first_proposal_tx.epoch_number)
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

def get_all_labels():
    bus = secretstorage.dbus_init()
    collection = secretstorage.get_default_collection(bus)
    labels = []
    for item in collection.search_items({'application': 'Python keyring library', "service" : "pacli"}):
        # print(item.get_label())
        labels.append(item.get_attributes()["username"])

    return labels

def get_all_keyids():
    return get_all_labels()

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

def create_trackedtx(provider, txid=None, txhex=None):
    if txid:
        raw_tx = provider.getrawtransaction(txid, 1)
        print("Displaying info for transaction", txid)
    elif txhex:
        raw_tx = provider.decoderawtransaction(txhex)
    try:
        opreturn = read_tx_opreturn(raw_tx["vout"][1])
        txident = opreturn[:2]
    except KeyError:
        print("Transaction not found or incorrect format.")

    if txident == b"DL": return LockingTransaction.from_json(raw_tx, provider)
    if txident == b"DS": return SignallingTransaction.from_json(raw_tx, provider)
    if txident == b"DD": return DonationTransaction.from_json(raw_tx, provider)
    if txident == b"DV": return VotingTransaction.from_json(raw_tx, provider)
    if txident == b"DP": return ProposalTransaction.from_json(raw_tx, provider)


def previous_input_unspent(provider, input_data):
    # checks if previous input in listunspent.
    for input in provider.listunspent():
        if input["txid"] == input_data["txid"]:
            if input["vout"] == input_data["vout"]:
                print("Selected input unspent.")
                return True
    print("Selected input spent, searching for another one.")
    return False

def itemprint(lst):
    try:        
        if issubclass(type(lst[0]), TrackedTransaction):
            print([t.txid for t in lst])
        else:
            print(lst)
    except (IndexError, AttributeError):
        print(lst)

def signtx_by_key(provider, rawtx, label=None, key=None):
    # Allows to sign a transaction with a different than the main key.

    if not key:
        try:
           key = get_key(label)
        except ValueError:
           raise ValueError("No key nor key id provided.")

    return sign_transaction(provider, rawtx, key)


def update_2levels(d):
    # prepares a dict with 2 levels like ProposalState for prettyprinting.
    for item in d:
        if type(d[item]) in (list, tuple) and len(d[item]) > 0:
            for i in range(len(d[item])):
                if type(d[item][i]) in (list, tuple) and len(d[item][i]) > 0:
                    if issubclass(type(d[item][i][0]), TrackedTransaction):
                        d[item][i] = [txdisplay(t) for t in d[item][i]]
                    elif type(d[item][i][0]) == DonationState:
                        d[item][i] = [s.__dict__ for s in d[item][i]]
                elif type(d[item][i]) == dict:
                    if len(d[item][i]) > 0 and type(list(d[item][i].values())[0]) == DonationState:
                        d[item][i] = [s.__dict__ for s in d[item][i].values()]
                elif issubclass(type(d[item][0]), TrackedTransaction):
                    d[item] = [txdisplay(t) for t in d[item]]

        elif issubclass(type(d[item]), TrackedTransaction):
            d[item] = d[item].txid
        elif issubclass(type(d[item]), Deck):
            d[item] = d[item].id

def txdisplay(tx, show_items: list=["amount", "address", "reserve_address", "reserved_amount", "proposal_txid"]):
    # displays transactions in a meaningful way without showing the whole dict
    displaydict = { "txid" : tx.txid }
    txdict = tx.__dict__
    for item in txdict:
        if item in show_items:
            displaydict.update({item : txdict[item]})
    return displaydict

def show_stored_key(keyid: str, network: str, pubkey: bool=False, privkey: bool=False, wif: bool=False, json_mode=False):
    # TODO: json_mode (only for addresses)        
    try:
        raw_key = bytearray.fromhex(get_key(keyid))
    except TypeError:
        exc_text = "No key data for key {}".format(keyid)
        raise Exception(exc_text)

    key = Kutil(network=network, privkey=raw_key)

    if privkey:
        return key.privkey
    elif pubkey:
        return key.pubkey
    elif wif:
        return key.wif
    else:
        return key.address

def show_stored_address(keyid: str, network: str, json_mode=False):
    # Safer mode for show_stored_key.
    # TODO: json mode still unfinished.
    return show_stored_key(keyid, network=network, json_mode=json_mode)

def show_addresses(addrlist: list, keylist: list, network: str, debug=False):
    if len(addrlist) != len(addrlist):
        raise ValueError("Both lists must have the same length.")
    result = []
    for kpos in range(len(keylist)):
        if (addrlist[kpos] == None) and (keylist[kpos] is not None):

            adr = show_stored_address(keylist[kpos], network=network)
            if debug: print("Address", adr, "got from key", keylist[kpos])
        else:
            adr = addrlist[kpos]
        result.append(adr)
    return result

def get_deckinfo(deckid, provider):
    d = deck_from_tx(deckid, provider)
    return d.__dict__

def get_all_trackedtxes(provider, proposal_id, include_badtx=False, light=False):
    # This gets all tracked transactions and displays them, without checking validity.
    # An advanced mode could even detect those with wrong format.

    for tx_type in ("voting", "signalling", "locking", "donation"):
        ptx = ProposalTransaction.from_txid(proposal_id, provider)
        p2th = ptx.deck.derived_p2th_address(tx_type)
        txes = get_marked_txes(provider, p2th)
        print(tx_type, ":")
        for txjson in txes:
            try:
                if tx_type == "voting": tx = VotingTransaction.from_json(txjson, provider, deck=ptx.deck)
                elif tx_type == "signalling": tx = SignallingTransaction.from_json(txjson, provider, deck=ptx.deck)
                elif tx_type == "locking": tx = LockingTransaction.from_json(txjson, provider, deck=ptx.deck)
                elif tx_type == "donation": tx = DonationTransaction.from_json(txjson, provider, deck=ptx.deck)
                if tx.proposal_txid == proposal_id:
                    if light:
                        pprint(txdisplay(tx))
                    else:
                        pprint(tx.__dict__)
            except InvalidTrackedTransactionError:
                if include_badtx:
                    try:
                        assert str(read_tx_opreturn(txjson["vout"][1])[2:34].hex()) == proposal_id
                        print("Invalid Transaction:", txjson["txid"])
                    except (KeyError, IndexError, AssertionError):
                        continue
