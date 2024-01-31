from pypeerassets.at.dt_entities import ProposalTransaction, SignallingTransaction, LockingTransaction, DonationTransaction, VotingTransaction, InvalidTrackedTransactionError
from pypeerassets.provider import Provider
from pypeerassets.at.dt_states import ProposalState, DonationState
from pypeerassets.at.dt_parser_state import ParserState
from pypeerassets.networks import net_query
from pypeerassets.at.protobuf_utils import parse_protobuf
from pypeerassets.at.dt_misc_utils import get_proposal_state, find_proposal, get_parser_state, sats_to_coins, coins_to_sats
from pypeerassets.at.dt_parser_utils import get_proposal_states, get_marked_txes
from pypeerassets.pautils import read_tx_opreturn
from pacli.extended_interface import PacliInputDataError

from decimal import Decimal
from prettyprinter import cpprint as pprint

import pypeerassets as pa
import pypeerassets.at.dt_periods as dp
import pacli.dt_interface as di
import pypeerassets.at.dt_misc_utils as dmu
import pypeerassets.at.constants as c
import pacli.extended_utils as eu


from pacli.provider import provider
from pacli.config import Settings


# Decks

def deck_from_ttx_txid(txid: str, tx_type: str, provider: object, debug: bool=False) -> object:
    """Returns a deck object, given a TrackedTransaction TXID."""
    try:
        ttx = provider.getrawtransaction(txid, 1)
        return dmu.deck_from_p2th(ttx, tx_type, provider)
    except ValueError:
        raise PacliInputDataError("Incorrect input, no deck found based on this transaction or proposal ID.")

# Proposal states and periods

def check_current_period(proposal_txid: str, deck: object, tx_type: int, dist_round: int=None, phase: int=None, release: bool=False, wait: bool=False, security_level: int=1, quiet: bool=False) -> None:
    """Checks the current period of a proposal, and waits until a target period is reached if used with the 'wait' flag."""

    # TODO: Re-check side effects of get_period change. => Seems OK, but take the change into account.

    current_period, blocks = get_period(proposal_txid, deck)
    if not quiet:
        print("Current period:", di.printout_period(current_period, blocks))
    try:
        if dist_round is None:
            target_period = get_next_suitable_period(tx_type, current_period, dist_round=dist_round)
        else:
            # TODO: re-check the dist_round index in humanreadable_to_periodcode.
            # Currently the index there seems to start at 1 instead of 0.
            # This is more human-readable but it must be consistent system-wide.
            # until then, we calculate the value manually here.
            # target_period = dp.humanreadable_to_periodcode(tx_type, dist_round + 1)
            (period_phase, rd) = ("D", dist_round - 4) if dist_round > 3 else ("B", dist_round)
            offset = 1 if tx_type in ("donation", "locking") else 0
            target_period = (period_phase, 10*(1 + rd) + offset)
    except ValueError as e:
        raise PacliInputDataError(e)

    if not quiet:
        print("Target period: {}{}".format(target_period[0],str(target_period[1])))
    proposal_tx = find_proposal(proposal_txid, provider)
    ps = ProposalState(first_ptx=proposal_tx, valid_ptx=proposal_tx)
    startblock, endblock = dp.get_startendvalues(target_period, ps)
    # MODIF: security level, added targetblock
    target, end_target = eu.get_safe_block_timeframe(startblock, endblock, security_level)

    return di.wait_for_block(target, end_target, provider, wait, quiet=quiet)

def get_next_suitable_period(tx_type, period, dist_round=None):
    """Takes a TrackedTransaction type and a period and calculates the next period
       this type of transaction can be released."""
    # TODO: maybe it would be simpler to assign all suitable periods to all tx types,
    # and then iterate over the index.
    if tx_type in ("donation", "signalling", "locking"):
        offset = 0 if tx_type == "signalling" else 1

        if period[0] in ("B", "D") and (10 <= period[1] <= 41):
            # the original code gives always the next period
            # target_period = (period[0], (period[1] // 10 + 1) * 10 + offset)
            # new code: gives current period if current one is suitable, otherwise the next one.
            # with the modulo we know if we are in a signalling (0) or donation/locking period.
            if period[1] % 10 == offset:
               target_period = period
            else:
               target_period = (period[0], (period[1] // 10 + 1) * 10 + offset)

        elif period in (("A", 0), ("A", 1), ("B", 0), ("B", 1)):
            target_period = ("B", 10 + offset)
        elif period in (("C", 0), ("D", 0), ("D", 1), ("D", 2)):
            target_period = ("D", 10) if tx_type == "signalling" else ("D", 2)

    elif tx_type == "voting":
        if period in (("A", 0), ("A", 1), ("B", 0), ("B", 1)):
            target_period = ("B", 1)
        elif (period[0] in ("B", "C")) or (period == ("D", 0)):
            target_period = ("D", 1)

    try:
        return target_period
    except UnboundLocalError:
        raise PacliInputDataError("No suitable period left for this transaction type.")

def find_basic_proposal_state_data(proposal_id, deck):
    """Gets a basic proposal state given the ID and the deck.
    The parser is called to create the list of states."""

    pstates = get_proposal_states(provider, deck)
    try:
        return pstates[proposal_id]
    except KeyError:
        raise PacliInputDataError("This Proposal ID does not correspond to a Proposal State.")


def get_period(proposal_id: str, deck: object, blockheight=None):
    """Provides the period of a proposal, given a block height (default: next block to current block)."""
    # MODIFIED. if blockheight not given, query the period corresponding to the next block, not the last recorded block.
    if not blockheight:
        blockheight = provider.getblockcount() + 1
    pdict = get_all_periods(proposal_id, deck)
    result = dp.period_query(pdict, blockheight)
    return result


def get_dist_round(proposal_id: str, deck: object, blockheight: int=None, period: tuple=None):
    """Provides the dist round for a blockheight, if it corresponds to one."""

    if not period:
        period = get_period(proposal_id, deck, blockheight=blockheight)
    try:
        assert (period[0][0] in ("B", "D")) and (period[0][1] >= 10)
        if period[0][0] == "B":
            return (period[0][1] // 10) - 1
        elif period[0][0] == "D":
            return (period[0][1] // 10) + 4 - 1
    except AssertionError:
        return None


def get_all_periods(proposal_id: str, deck: object) -> dict:
    """Returns a dict of all periods from a given proposal, according to the last modification."""
    ps = find_basic_proposal_state_data(proposal_id, deck)
    return dp.get_period_dict(ps)

def get_proposal_state_periods(deckid: str, block: int, advanced: bool=False, debug: bool=False) -> dict:
    """Returns all proposals of a deck (with data of the proposal state) and the period they're in.
      Used mainly in 'proposal list' command."""
    # Advanced mode calls the parser, thus much slower, and shows other parts of the state.

    result = {}
    deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
    try:
       assert deck.at_type == c.DT_ID
    except (AssertionError, AttributeError):
       raise PacliInputDataError("Not a valid DT Proof of Donation deck. Proposals could not be retrieved.")

    if advanced:
        pst = get_parser_state(provider, deck, force_continue=True, force_dstates=True, debug=debug) # really necessary?
        pstates = pst.proposal_states
    else:
        pstates = get_proposal_states(provider, deck)

    for proposal_txid in pstates:
        ps = pstates[proposal_txid]
        period, blockheights = get_period(proposal_txid, deck, blockheight=block)
        state_data = {"state": ps, "startblock" : blockheights[0], "endblock" : blockheights[1]}

        try:
            result[period].append(state_data)
        except KeyError:
            result.update({period : [state_data]})
    return result


# Donation states and slots

def get_slot(proposal_id: str, donor_address: str, dist_round: int=None, quiet: bool=False):
    """Given a proposal, a donor address, and the dist_round, returns the slot.
       If no dist_round is given, show the slot of the first Donation state the donor address participated.."""
    dstates = dmu.get_donation_states(provider=provider, proposal_id=proposal_id, donor_address=donor_address)

    if dist_round:
        for state in dstates:
            if state.dist_round == dist_round:
                raw_slot = state.slot
                return {"round" : dist_round, "slot" : raw_slot}
        else:
            if quiet:
                return {"round" : dist_round, "slot" : None}
            else:
                raise PacliInputDataError("No slot found in round {}".format(dist_round))

    else:
        try:
            return {"round" :dstates[0].dist_round, "slot" : dstates[0].slot}

        except IndexError:
            raise PacliInputDataError("No valid donation process found.")

# TODO: removed from only use case (dt_txtools.get_donation_state_data) but re-check.
# Should be possible to be removed, becuase there is only 1 state per donor address/proposal allowed.
'''def select_donation_state(dstates: list, tx_type: str, debug: bool=False):
    """Creates a hierarchy to select the correct donation state for a locking/donation transaction.
    first, sorted by blockheight and blockseq
    second, distinct assertions exclude certain transactions."""
    # TODO: isn't that obsolete after the protocol overhaul?
    # Should be possible to be removed, becuase there is only 1 state per donor address/proposal allowed.

    for dstate in sorted(dstates, key=lambda x: (x.origin_tx.blockheight, x.origin_tx.blockseq)):
        if debug: print("Donation state found:", dstate.id)
        if debug and (dstate.signalling_tx is not None): print("Signalling tx:", dstate.signalling_tx.txid)
        if debug and (dstate.reserve_tx is not None): print("Reserve tx:", dstate.reserve_tx.txid)
        if debug and (dstate.locking_tx is not None): print("Locking tx:", dstate.locking_tx.txid)
        if debug: print("Slot distribution round:", dstate.dist_round)
        if debug: print("Effective locking slot:", dstate.effective_locking_slot)

        try:

            assert dstate.state == "incomplete"
            assert dstate.slot > 0
            if tx_type == "locking":
                assert dstate.locking_tx is None
                # TODO: this check should be done elsewhere
                # assert dstate.locking_tx.ins[0].txid == dstate.origin_tx.txid
            if tx_type == "donation":
                if dstate.dist_round <= 3:
                    assert dstate.locking_tx is not None
                if dstate.dist_round > 3:
                    pass

        except AssertionError:
            continue


    return dstate'''

def find_donation_state_by_string(searchstring: str, only_start: bool=False):
    """Returns a list of donation states including a certain string in its txid."""

    try:
        txids = eu.find_transaction_by_string(searchstring, only_start=only_start)
        return [dmu.get_dstate_from_origin_tx(txid, provider) for txid in txids]
    except Exception:
        raise PacliInputDataError("No matching donation state found.")

def find_proposal_state_by_string(searchstring: str, advanced: bool=False, shortid: bool=False, require_state: bool=False):
    """Returns proposal states including a certain string in its txid or description."""

    matching_proposals = []

    try:
        for deck in dmu.list_decks_by_at_type(provider, c.ID_DT):
            if advanced:
                pstates = get_parser_state(provider, deck, force_continue=True).proposal_states
            else:
                pstates = get_proposal_states(provider, deck)
            for proposal in pstates.values():
                if shortid:
                    if proposal.id.startswith(searchstring):
                        matching_proposals.append(proposal)
                elif searchstring in proposal.first_ptx.description:
                    matching_proposals.append(proposal)
        if require_state:
            assert matching_proposals
    except (KeyError, IndexError, AssertionError):
        raise PacliInputDataError("Proposal state not found.")
    return matching_proposals

## Selection and processing of inputs of previous transactions in the same DonationState

def previous_input_unspent(input_txid: str, input_vout: int, redeem_script: object=None, quiet: bool=False) -> bool:
    """Returns a bool to know if an input was spent."""
    # P2SH is treated as always unspent.
    if redeem_script is not None:
        if not quiet:
            print("Getting data from P2SH locking transaction.")
        return True
    # checks if previous input in listunspent.
    for inp in provider.listunspent():
        if inp["txid"] == input_txid: # basic_tx_data["txid"]:
            if inp["vout"] == input_vout: # basic_tx_data["vout"]:
                if not quiet:
                    print("Selected input unspent.")
                return True
    return False

def get_previous_tx_input_data(tx_type: str, dstate: object, debug=False, quiet=False) -> dict:
    """Analyzes the donation state and provides the inputs for the transaction to create.
       It provides also: slot, type of input, and redeem script of locking tx.
       Only used if the transaction does not use --new_inputs."""
       # Used only in dt_txtools.get_basic_tx_data

    inputdata = {}

    if (tx_type == "donation") and (dstate.dist_round < 4):

        try:
            # An error can appear when donating in later rounds,
            # can probably only happen if there is an incorrect donation state found.
            prev_tx = dstate.locking_tx
            redeem_script = prev_tx.redeem_script
        except Exception:
            raise PacliInputDataError("Error during the input selection. The donation state is probably invalid due to corrupted data in the previous transaction.\nYou can try to save the donation state using the command with the --new_inputs flag.")
        inputdata.update({"redeem_script" : redeem_script})
    else:
        # reserve tx has always priority in the case a signalling tx also exists in the same donation state.
        # TODO: maybe this not always makes sense. It could make sense to add an option for this.
        redeem_script = None
        if dstate.reserve_tx is not None:
            prev_tx = dstate.reserve_tx
        else:
            prev_tx = dstate.signalling_tx

    inputdata.update({ "txid" : prev_tx.txid, "vout" : 2, "value" : prev_tx.amount})

    # Output type. This should be always P2PKH or P2SH.
    inputdata.update({ "inp_type" : [prev_tx.outs[2].script_pubkey.type] })

    if not previous_input_unspent(prev_tx.txid, 2 , quiet=quiet, redeem_script=redeem_script):
        raise PacliInputDataError("Input of previous transaction was already spent. Use --new_inputs to create the transaction.")

    return inputdata

def calculate_donation_amount(slot: int, chosen_amount: int, available_amount: int, network_name: str, new_inputs: bool=False, force: bool=False, quiet: bool=False) -> int:
    """Calculates the amount which will be locked or donated."""

    raw_slot = sats_to_coins(Decimal(slot), network_name=network_name)
    raw_amount = sats_to_coins(Decimal(chosen_amount), network_name=network_name) if chosen_amount is not None else None

    if not quiet:
        print("Assigned slot:", raw_slot)

    # You should only be able to use an amount greater than your slot if you use --force.
    if not force:
        effective_slot = min(slot, chosen_amount) if chosen_amount is not None else slot
        amount = min(available_amount, effective_slot) if available_amount else effective_slot
        if amount == 0:
            raise PacliInputDataError("No slot available for this donation. Transaction will not be created.")
    # elif new_inputs and (chosen_amount is not None):
    elif chosen_amount is not None:
        amount = chosen_amount
    elif available_amount is not None:
        amount = available_amount
    else:
        raise PacliInputDataError("If you don't use the parent transaction, you must provide an amount and new_inputs.")

    # Interface
    if quiet:
        return amount

    if amount == slot:
        print("Using assigned slot.")
    elif amount < slot:
        if chosen_amount is not None:
            print("Using custom amount {} smaller than the assigned slot of {}".format(raw_amount, raw_slot))
        else:
            print("Using available amount {}, smaller than the assigned slot of {}".format(sats_to_coins(Decimal(available_amount), network_name=network_name), raw_slot))
    elif (slot > amount) and not force:
        print("Chosen custom amount {} is higher than the slot {}, so we use the slot.".format(raw_amount, raw_slot))
    elif amount == available_amount:
        print("FORCING to use full available amount {}, higher than the assigned slot.".format(sats_to_coins(Decimal(available_amount), network_name=network_name)))
    else:
        print("FORCING custom amount {} higher than the assigned slot.".format(raw_amount))

    return amount

# Transaction information (check_tx command)

def get_trackedtx(txid=None, txhex=None):
    """Creates a TrackedTransaction object from a raw transaction or txid."""
    # TODO: improve the visualization of metadata. Probably a new protobuf_to_dict method or so is needed.
    if txid:
        raw_tx = provider.getrawtransaction(txid, 1)
        print("Displaying info for transaction", txid)
    elif txhex:
        raw_tx = provider.decoderawtransaction(txhex)
    try:
        opreturn = read_tx_opreturn(raw_tx["vout"][1])
        txident = parse_protobuf(opreturn, "ttx")["id"]
    except KeyError:
        raise PacliInputDataError("Transaction not found or incorrect format.")

    if txident == c.ID_LOCKING: return LockingTransaction.from_json(raw_tx, provider)
    if txident == c.ID_SIGNALLING: return SignallingTransaction.from_json(raw_tx, provider)
    if txident == c.ID_DONATION: return DonationTransaction.from_json(raw_tx, provider)
    if txident == c.ID_VOTING: return VotingTransaction.from_json(raw_tx, provider)
    if txident == c.ID_PROPOSAL: return ProposalTransaction.from_json(raw_tx, provider)


def get_all_trackedtxes(proposal_id, include_badtx=False, light=False):
    """Gets all tracked transactions and displays them, without checking validity."""
    # An advanced mode could detect those with wrong format.

    for tx_type in ("voting", "signalling", "locking", "donation"):
        ptx = find_proposal(proposal_id, provider)
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
                        pprint(di.txdisplay(tx))
                    else:
                        pprint(tx.__dict__)
            except InvalidTrackedTransactionError:
                if include_badtx:
                    try:
                        assert str(read_tx_opreturn(txjson["vout"][1])[2:34].hex()) == proposal_id
                        print("Invalid Transaction:", txjson["txid"])
                    except (KeyError, IndexError, AssertionError):
                        continue

# Reward calculation

def get_pod_reward_data(proposal_id: str, donor_address: str, donation_state: object=None, proposer: bool=False, debug: bool=False, quiet: bool=False, network_name: str=Settings.network) -> dict:
    """Returns a dict with the amount of the reward and the deckid."""

    ptx = find_proposal(proposal_id, provider) # ptx is given directly to get_donation_state
    deckid = ptx.deck.id
    decimals = ptx.deck.number_of_decimals
    if proposer:
        if donor_address == ptx.donation_address:
            if not quiet:
                print("Claiming tokens for the Proposer for missing donations ...")
            pstate = get_proposal_state(provider, proposal_id)
            reward = pstate.proposer_reward
            result = {"donation_txid" : proposal_id}
        else:
            raise PacliInputDataError("Your donor address isn't the Proposer address, so you can't claim their tokens.")

    else:
        dstates = dmu.get_donation_states(provider, proposal_tx=ptx, donor_address=donor_address, phase=1, debug=debug)

        for ds in dstates:
            if ds.state != "complete":
                if debug: print("Ignoring incomplete or abandoned donation state.")
                continue
            if donation_state is not None:
                if donation_state == ds.id:
                    break
            else:
                if ds.donor_address == donor_address:
                    break # this selects always the first completed state. Otherwise you have to provide the id.
        else:
            raise PacliInputDataError("No valid donation state found.")

        if not quiet:
            print("Your donation:", sats_to_coins(Decimal(ds.donated_amount), network_name=network_name), "coins")
            if ds.donated_amount != ds.effective_slot:
                print("Your effective slot value is different:", sats_to_coins(Decimal(ds.effective_slot), network_name=network_name))
                print("The effective slot is taken into account for the token distribution.")
        if (ds.donated_amount > 0) and (ds.effective_slot == 0):
            raise PacliInputDataError("Your slot is 0, your donation was probably too low.")
        reward = ds.reward
        result = {"donation_txid" : ds.donation_tx.txid}

    if reward < 1:
       raise PacliInputDataError("Reward is zero or lower than one token unit.")

    if not quiet:
        print("Token reward by distribution period:", ptx.deck.epoch_quantity)

    if (proposer and pstate.dist_factor) or (ds.reward is not None):
        formatted_reward = Decimal(reward) / 10 ** decimals
        if not quiet:
            print("Your reward:", formatted_reward, "PoD tokens")
    else:
        raise PacliInputDataError("Proposal still not processed completely. Claim your reward when the current distribution period has ended.")
    result.update({"deckid" : deckid, "reward" : formatted_reward})
    return result

def donor_address_used(donor_address: str, proposal_id: str) -> bool:
   """Checks if a donor address was already used for a proposal (only once is allowed)."""
   # TODO: could go into pypeerassets?

   used_donor_addresses = [d.donor_address for d in dmu.get_donation_states(provider, proposal_id)]
   return (donor_address in used_donor_addresses)



