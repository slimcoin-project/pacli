from pypeerassets.at.dt_entities import ProposalTransaction, SignallingTransaction, LockingTransaction, DonationTransaction, VotingTransaction, InvalidTrackedTransactionError
from pypeerassets.provider import Provider
from pypeerassets.at.dt_states import ProposalState, DonationState
from pypeerassets.at.dt_parser_state import ParserState
# from pypeerassets.at.transaction_formats import setfmt
from pypeerassets.networks import net_query
from pypeerassets.at.protobuf_utils import serialize_ttx_metadata, parse_ttx_metadata
from pypeerassets.at.dt_misc_utils import import_p2th_address, create_unsigned_tx, get_proposal_state, sign_p2sh_transaction, sign_mixed_transaction, proposal_from_tx, get_parser_state, sats_to_coins, coins_to_sats
from pypeerassets.at.dt_parser_utils import deck_from_tx, get_proposal_states, get_marked_txes
from pypeerassets.pautils import read_tx_opreturn, load_deck_p2th_into_local_node
from pypeerassets.kutil import Kutil
from pypeerassets.transactions import sign_transaction, MutableTransaction
from pypeerassets.legacy import is_legacy_blockchain, legacy_import
from pacli.utils import (cointoolkit_verify,
                         signtx,
                         sendtx)
from decimal import Decimal
from prettyprinter import cpprint as pprint

import pypeerassets.at.dt_periods as dp
import pacli.dt_interface as di
import pypeerassets.at.dt_misc_utils as dmu

from pacli.provider import provider
from pacli.config import Settings
from pacli.keystore_extended import get_key


def check_current_period(proposal_txid, tx_type, dist_round=None, phase=None, release=False, wait=False):
    # TODO should be reorganized so the ProposalState isn't created 2x! (one time here, the other one in get_period)
    # Isn't the dummy state enough? Should be possible to call the same dummy state in get_period and here.
    # Re-check side effects of get_period change. => Seems OK, but take the change into account.

    current_period, blocks = get_period(proposal_txid)
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
        print(e)
        return False

    print("Target period: {}{}".format(target_period[0],str(target_period[1])))
    proposal_tx = proposal_from_tx(proposal_txid, provider)
    ps = ProposalState(first_ptx=proposal_tx, valid_ptx=proposal_tx)
    startblock, endblock = dp.get_startendvalues(target_period, ps)

    return di.wait_for_block(startblock, endblock, provider, wait)

def get_next_suitable_period(tx_type, period, dist_round=None):
    # TODO: maybe it would be simpler to assign all suitable periods to all tx types,
    # and then iterate over the index.
    if tx_type in ("donation", "signalling", "locking"):
        offset = 0 if tx_type == "signalling" else 1

        if period[0] in ("B", "D") and (10 <= period[1] <= 49):
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
        raise ValueError("No suitable period left for this transaction type.")

def dummy_pstate(proposal_txid):
    """Creates a dummy ProposalState from a ProposalTransaction ID without any parser information."""
    try:
        proposal_tx = proposal_from_tx(proposal_txid, provider)
        ps = ProposalState(proposal_tx, proposal_tx)

    except: # catches mainly AttributeError and DecodeError
        raise ValueError("Proposal or deck spawn transaction in wrong format.")

    return ps

def get_period(proposal_txid, blockheight=None):
    """Provides an user-friendly description of the current period."""
    # MODIFIED. if blockheight not given, query the period corresponding to the next block, not the last recorded block.
    if not blockheight:
        blockheight = provider.getblockcount() + 1
    pdict = get_all_periods(proposal_txid)
    result = dp.period_query(pdict, blockheight)
    return result

def get_dist_round(proposal_id, blockheight=None):
    """Provides the current dist round if blockheight is inside one."""
    period = get_period(proposal_id, blockheight)
    try:
        assert (period[0][0] in ("B", "D")) and (period[0][1] >= 10)
        if period[0][0] == "B":
            return (period[0][1] // 10) - 1
        elif period[0][0] == "D":
            return (period[0][1] // 10) + 4 - 1
    except AssertionError:
        return None


def get_all_periods(proposal_txid):
    # this one gets ALL periods from the current proposal, according to the last modification.
    ps = dummy_pstate(proposal_txid)
    return dp.get_period_dict(ps)


# Proposal and donation states

def get_proposal_state_periods(deckid, block, advanced=False, debug=False):
    # Advanced mode calls the parser, thus much slower, and shows other parts of the state.

    result = {}
    deck = deck_from_tx(deckid, provider)
    try:
       assert deck.at_type == b"DT"
    except (AssertionError, AttributeError):
       raise ValueError("Not a DT Proof of Donation deck.")

    if advanced:
        pst = get_parser_state(provider, deck, force_continue=True, force_dstates=True, debug=debug) # really necessary?
        pstates = pst.proposal_states
    else:
        pstates = get_proposal_states(provider, deck)

    for proposal_txid in pstates:
        ps = pstates[proposal_txid]
        period, blockheights = get_period(proposal_txid, blockheight=block)
        state_data = {"state": ps, "startblock" : blockheights[0], "endblock" : blockheights[1]}

        try:
            result[period].append(state_data)
        except KeyError:
            result.update({period : [state_data]})
    return result

def get_proposal_info(proposal_txid):
    # MODIFIED: state removed, get_proposal_state should be used.
    proposal_tx = proposal_from_tx(proposal_txid, provider)
    return proposal_tx.__dict__

def get_slot(proposal_id, donor_address, dist_round=None):
    dstates = dmu.get_donation_states(provider=provider, proposal_id=proposal_id, donor_address=donor_address)
    if dist_round:
        for state in dstates:
            if state.dist_round == dist_round:
                raw_slot = state.slot
                break
        else:
            raise ValueError("No slot found in round", dist_round)

    else:
        try:
            return dstates[0].slot
        except IndexError:
            raise ValueError("No valid donation process found.")

def select_donation_state(dstates: list, tx_type: str, debug: bool=False):
    # this creates a robust hierarchy to select the correct donation state for a locking/donation transaction.
    # first, sorted by blockheight and blockseq
    # second, distinct assertions exclude certain transactions.
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


    return dstate

def get_previous_tx_input_data(address, tx_type, proposal_id=None, proposal_tx=None, previous_txid=None, dist_round=None, debug=False, use_locking_slot=False):
    # TODO: The previous_txid parameter seems to be unused, check if really needed, because it complicates the code.
    # TODO: "txid" and "vout" could be changed better into "input_txid" and "input_vout", because later it is mixed with data of the actual tx (not only the input tx).
    # TODO: re-check what we really want to achieve with the "address" parameter. could it replaced by the donor address?
    # provides the following data: slot, txid and vout of signalling or locking tx, value of input.
    # starts the parser.
    inputdata = {}
    print("Searching for donation state for this transaction. Please wait.")
    dstates = dmu.get_donation_states(provider, proposal_tx=proposal_tx, tx_txid=previous_txid, donor_address=address, dist_round=dist_round, debug=debug)
    if not dstates:
        raise ValueError("No donation states found.")
    dstate = select_donation_state(dstates, tx_type, debug=debug)

    if (tx_type == "donation") and (dstate.dist_round < 4):

        prev_tx = dstate.locking_tx
        # TODO: this seems to raise an error sometimes when donating in later rounds ...
        # This can in reality only happen if there is an incorrect donation state found.
        inputdata.update({"redeem_script" : prev_tx.redeem_script})
    else:
        # reserve tx has always priority in the case a signalling tx also exists in the same donation state.
        if dstate.reserve_tx is not None:
            prev_tx = dstate.reserve_tx
        else:
            prev_tx = dstate.signalling_tx

    inputdata.update({ "txid" : prev_tx.txid, "vout" : 2, "value" : prev_tx.amount, "slot" : dstate.slot })
    if use_locking_slot and dstate.dist_round < 4:
        inputdata.update({ "locking_slot" : dstate.effective_locking_slot })

    # Output type. This should be always P2PKH or P2SH.
    if prev_tx:
        inputdata.update({ "inp_type" : [prev_tx.outs[2].script_pubkey.type] })

    return inputdata

## Inputs, outputs and Transactions

def get_basic_tx_data(tx_type, proposal_id=None, input_address: str=None, dist_round: int=None, deckid: str=None, new_inputs: bool=False, use_slot: bool=False, use_locking_slot: bool=False, debug: bool=False):
    """Gets basic data for a new TrackedTransaction"""

    if proposal_id is not None:
        proposal = proposal_from_tx(proposal_id, provider)
        deck = proposal.deck
        tx_data = { "proposal_tx" : proposal }
    else:
        deck = deck_from_tx(deckid, provider)
        tx_data = {}

    tx_data.update({"deck" : deck, "input_address" : input_address, "tx_type": tx_type, "provider" : provider })
    if tx_type in ("donation", "locking"):
        try:
            if (not new_inputs) or use_slot:
                tx_data.update(get_previous_tx_input_data(input_address, tx_type, proposal_tx=proposal, dist_round=dist_round, use_locking_slot=use_locking_slot, debug=debug))
        except ValueError:
            raise ValueError("No suitable signalling/reserve transactions found.")

    return tx_data


def calculate_donation_amount(slot: int, chosen_amount: int, available_amount: int, network_name: str, new_inputs: bool=False, force: bool=False):

    raw_slot = sats_to_coins(Decimal(slot), network_name=network_name)
    raw_amount = sats_to_coins(Decimal(chosen_amount), network_name=network_name) if chosen_amount is not None else None

    print("Assigned slot:", raw_slot)

    # You should only be able to use an amount greater than your slot if you use --force.
    if not force:
        effective_slot = min(slot, chosen_amount) if chosen_amount is not None else slot
        amount = min(available_amount, effective_slot) if available_amount else effective_slot
        if amount == 0:
            raise Exception("No slot available for this donation. Transaction will not be created.")
    # elif new_inputs and (chosen_amount is not None):
    elif chosen_amount is not None:
        # effective_slot = None # TODO: Re-check if this solved the "No slot available" error.
        amount = chosen_amount
    elif available_amount is not None:
        amount = available_amount
    else:
        raise ValueError("If you don't use the parent transaction, you must provide an amount and new_inputs.")

    # Interface
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

def create_unsigned_trackedtx(params: dict, basic_tx_data: dict, raw_amount=None, dest_address=None, change_address=None, raw_tx_fee=None, raw_p2th_fee=None, cltv_timelock=0, network_name=None, version=1, new_inputs: bool=False, reserve: str=None, reserve_address: str=None, use_locking_slot: bool=False, force: bool=False, debug: bool=False):
    # This function first prepares a transaction, creating the datastring and calculating fees in an unified way,
    # then creates transaction with pypeerassets method.

    b = basic_tx_data
    chosen_amount = None if raw_amount is None else coins_to_sats(Decimal(raw_amount), network_name=network_name)
    reserved_amount = None if reserve is None else coins_to_sats(Decimal(reserve), network_name=network_name)

    tx_fee = coins_to_sats(Decimal(raw_tx_fee), network_name=network_name)
    p2th_fee = coins_to_sats(Decimal(raw_p2th_fee), network_name=network_name)
    input_txid, input_vout, input_value, available_amount = None, None, None, None

    # legacy chains need a minimum transaction value even at OP_RETURN transactions
    op_return_fee = p2th_fee if is_legacy_blockchain(network_name, "nulldata") else 0
    all_fees = tx_fee + p2th_fee + op_return_fee

    if b["tx_type"] in ("donation", "locking"):

        if (not new_inputs) and previous_input_unspent(basic_tx_data):
            # new_inputs enables the automatic selection of new inputs for locking and donation transactions.
            # this can be useful if the previous input is too small for the transaction/p2th fees, or in the case of a
            # ProposalModification
            # If new_inputs is chosen or the previous input was spent, then all the following values stay in None.
            input_txid, input_vout, input_value = b["txid"], b["vout"], b["value"]
            available_amount = input_value - all_fees
            if available_amount <= 0:
                raise ValueError("Insufficient funds in this input to pay all fees. Use --new_inputs to lock or donate this amount.")

        try:
            used_slot = b["slot"] if not use_locking_slot else b["locking_slot"]
            amount = calculate_donation_amount(used_slot, chosen_amount, available_amount, network_name, new_inputs, force)
        except KeyError:
            amount = chosen_amount
    else:
        amount = chosen_amount

    # print("Amount:", amount, "available", available_amount, "input value", input_value, "slot", slot)
    # CHANGED TO PROTOBUF
    params["ttx_version"] = 1 # NEW. for future upgradeability.
    data = serialize_ttx_metadata(params=params, network=net_query(provider.network))
    proposal_txid = params.get("proposal_id")


    return create_unsigned_tx(b["deck"], b["provider"], b["tx_type"], proposal_txid=proposal_txid, input_address=b["input_address"], amount=amount, data=data, address=dest_address, network_name=network_name, change_address=change_address, tx_fee=tx_fee, p2th_fee=p2th_fee, input_txid=input_txid, input_vout=input_vout, cltv_timelock=cltv_timelock, reserved_amount=reserved_amount, reserve_address=reserve_address, input_redeem_script=b.get("redeem_script"))

def calculate_timelock(proposal_id):
    # returns the number of the block where the working period of the Proposal ends.

    first_proposal_tx = proposal_from_tx(proposal_id, provider)
    # print("first tx info", first_proposal_tx.blockheight, first_proposal_tx.epoch, first_proposal_tx.deck.epoch_length, first_proposal_tx.epoch_number)
    cltv_timelock = (first_proposal_tx.epoch + first_proposal_tx.epoch_number + 1) * first_proposal_tx.deck.epoch_length
    return cltv_timelock

def finalize_tx(rawtx, verify, sign, send, redeem_script=None, label=None, key=None, input_types=None, debug=False):
    # groups the last steps together

    if verify:
        print(
            cointoolkit_verify(rawtx.hexlify())
             )  # link to cointoolkit - verify

    if False in (sign, send):
        print("NOTE: This is a dry run, your transaction will still not be broadcasted.\nAdd --sign --send to the command to broadcast it")

    if sign:

        if redeem_script is not None:
            if debug: print("Signing with redeem script:", redeem_script)
            # TODO: in theory we need to solve inputs from --new_inputs separately from the p2sh inputs.
            # For now we can only use new_inputs OR spend the P2sh.
            # TODO: here we use Settings.key, but give the option to provide different key in donation release command?
            try:
                tx = sign_p2sh_transaction(provider, rawtx, redeem_script, Settings.key)
            except NameError as e:
                print("Exception:", e)
                #    return None

        elif (key is not None) or (label is not None): # sign with a different key
            tx = signtx_by_key(rawtx, label=label, key=key)
            # we need to check the type of the input, as the Kutil method cannot sign P2PK
        else:
            if input_types is None:
                input_types = get_input_types(rawtx)

            if "pubkey" not in input_types:
                tx = sign_transaction(provider, rawtx, Settings.key)
            else:
                tx = sign_mixed_transaction(provider, rawtx, Settings.key, input_types)
            #else:
            #    # fallback, will not always work, try to avoid!
            #    tx = sign_transaction(provider, rawtx, Settings.key)
            #    # tx = signtx(rawtx)

        if send:
            pprint({'txid': sendtx(tx)})
        return {'hex': tx.hexlify()}

    return rawtx.hexlify()

def create_trackedtx(txid=None, txhex=None):
    """Creates a TrackedTransaction object from a raw transaction or txid."""
    # TODO: improve the visualization of metadata. Probably a new protobuf_to_dict method or so is needed.
    if txid:
        raw_tx = provider.getrawtransaction(txid, 1)
        print("Displaying info for transaction", txid)
    elif txhex:
        raw_tx = provider.decoderawtransaction(txhex)
    try:
        opreturn = read_tx_opreturn(raw_tx["vout"][1])
        txident = parse_ttx_metadata(opreturn).id
    except KeyError:
        print("Transaction not found or incorrect format.")

    if txident == b"DL": return LockingTransaction.from_json(raw_tx, provider)
    if txident == b"DS": return SignallingTransaction.from_json(raw_tx, provider)
    if txident == b"DD": return DonationTransaction.from_json(raw_tx, provider)
    if txident == b"DV": return VotingTransaction.from_json(raw_tx, provider)
    if txident == b"DP": return ProposalTransaction.from_json(raw_tx, provider)


def previous_input_unspent(basic_tx_data):
    # P2SH is treated as always unspent.
    if basic_tx_data.get("redeem_script") is not None:
        print("Getting data from P2SH locking transaction.")
        return True
    # checks if previous input in listunspent.
    # print(basic_tx_data)
    provider = basic_tx_data["provider"]
    for input in provider.listunspent():
        if input["txid"] == basic_tx_data["txid"]:
            if input["vout"] == basic_tx_data["vout"]:
                print("Selected input unspent.")
                return True
    print("Selected input spent, searching for another one.")
    return False

def signtx_by_key(rawtx, label=None, key=None):
    # Allows to sign a transaction with a different than the main key.

    if not key:
        try:
           key = get_key(label)
        except ValueError:
           raise ValueError("No key nor key label provided.")

    return sign_transaction(provider, rawtx, key)

def get_input_types(rawtx):
    # gets the types of ScriptPubKey inputs of a transaction.
    # Not ideal in terms of resource consumption/elegancy, but otherwise we would have to change PeerAssets core code,
    # because it manages input selection (RpcNode.select_inputs)
    input_types = []
    try:
        for inp in rawtx.ins:
            prev_tx = provider.getrawtransaction(inp.txid, 1)
            prev_out = prev_tx["vout"][inp.txout]
            input_types.append(prev_out["scriptPubKey"]["type"])

        return input_types

    except KeyError:
        raise ValueError("Transaction data not correctly given.")

def get_all_trackedtxes(proposal_id, include_badtx=False, light=False):
    # This gets all tracked transactions and displays them, without checking validity.
    # An advanced mode could even detect those with wrong format.

    for tx_type in ("voting", "signalling", "locking", "donation"):
        ptx = proposal_from_tx(proposal_id, provider)
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

def get_pod_reward_data(proposal_id, donor_address, donation_state=None, proposer=False, debug=False, network_name=Settings.network):
    """Returns a dict with the amount of the reward and the deckid."""
    # coin = coin_value(network_name=network_name)
    ptx = proposal_from_tx(proposal_id, provider) # ptx is given directly to get_donation_state
    deckid = ptx.deck.id
    decimals = ptx.deck.number_of_decimals
    if proposer:
        if donor_address == ptx.donation_address:
            print("Claiming tokens for the Proposer for missing donations ...")
            pstate = get_proposal_state(provider, proposal_id)
            reward = pstate.proposer_reward
            result = {"donation_txid" : proposal_id}
        else:
            raise Exception("ERROR: Your donor address isn't the Proposer address, so you can't claim their tokens.")

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
            raise Exception("ERROR: No valid donation state found.")

        print("Your donation:", sats_to_coins(Decimal(ds.donated_amount), network_name=network_name), "coins")
        if ds.donated_amount != ds.effective_slot:
            print("Your effective slot value is different:", sats_to_coins(Decimal(ds.effective_slot), network_name=network_name))
            print("The effective slot is taken into account for the token distribution.")
        if (ds.donated_amount > 0) and (ds.effective_slot == 0):
            print("Your slot is 0, there was a problem with your donation.")
        reward = ds.reward
        result = {"donation_txid" : ds.donation_tx.txid}

    if reward < 1:
       raise Exception("ERROR: Reward is zero or lower than one token unit.")

    print("Token reward by distribution period:", ptx.deck.epoch_quantity)

    if (proposer and pstate.dist_factor) or (ds.reward is not None):
        formatted_reward = Decimal(reward) / 10 ** decimals
        print("Your reward:", formatted_reward, "PoD tokens")
    else:
        raise Exception("ERROR: Proposal still not processed completely. Wait for the distribution period to end.")
    result.update({"deckid" : deckid, "reward" : formatted_reward})
    return result
