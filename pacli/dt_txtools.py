# Basic tools for transaction creation

# TODO: check which imports are needed.
from pypeerassets.at.dt_entities import ProposalTransaction, SignallingTransaction, LockingTransaction, DonationTransaction, VotingTransaction, InvalidTrackedTransactionError
from pypeerassets.provider import Provider
from pypeerassets.at.dt_states import ProposalState, DonationState
from pypeerassets.at.dt_parser_state import ParserState
from pypeerassets.networks import net_query
from pypeerassets.at.protobuf_utils import serialize_ttx_metadata, parse_protobuf
from pypeerassets.at.dt_misc_utils import import_p2th_address, create_unsigned_tx, get_proposal_state, sign_p2sh_transaction, sign_mixed_transaction, find_proposal, get_parser_state, sats_to_coins, coins_to_sats
from pypeerassets.at.dt_parser_utils import get_proposal_states, get_marked_txes
from pypeerassets.pautils import read_tx_opreturn, load_deck_p2th_into_local_node
from pypeerassets.kutil import Kutil
from pypeerassets.transactions import sign_transaction, MutableTransaction
from pypeerassets.legacy import is_legacy_blockchain, legacy_import, legacy_mintx
from pacli.utils import (cointoolkit_verify,
                         signtx,
                         sendtx)
from pacli.extended_interface import PacliInputDataError

from decimal import Decimal
from prettyprinter import cpprint as pprint

import pypeerassets as pa
import pypeerassets.at.dt_periods as dp
import pacli.dt_interface as di
import pacli.keystore_extended as ke
import pypeerassets.at.dt_misc_utils as dmu
import pypeerassets.at.constants as c
import pacli.extended_utils as eu
import pacli.extended_interface as ei
import pacli.dt_utils as du


from pacli.provider import provider
from pacli.config import Settings


def create_trackedtransaction(tx_type,
                              proposal_id: str=None,
                              deckid: str=None,
                              dest_label: str=None,
                              dest_address: str=None,
                              change_address: str=None,
                              change_label: str=None,
                              reserve_address: str=None,
                              reserve_label: str=None,
                              req_amount: str=None,
                              periods: int=None,
                              description: str=None,
                              vote: str=None,
                              timelock: int=None,
                              amount: str=None,
                              reserve: str=None,
                              tx_fee: str="0.01",
                              security: int=1,
                              check_round: int=None,
                              new_inputs: bool=False,
                              force: bool=False,
                              verify: bool=False,
                              sign: bool=False,
                              send: bool=False,
                              wait: bool=False,
                              confirm: bool=True,
                              txhex: bool=False,
                              debug: bool=False):
    '''Generic tracked transaction creation.'''

    addresses, labels = (dest_address, reserve_address, change_address), (dest_label, reserve_label, change_label)
    # default values for params
    use_slot, vote_bool = True, True
    cltv_timelock, lockhash_type, public_address, rscript = None, None, None, None

    silent = True if txhex else False

    # enable using own labels for decks and proposals
    if proposal_id:
        proposal_id = eu.search_for_stored_tx_label("proposal", proposal_id, silent=silent)

    if deckid:
        deckid = eu.search_for_stored_tx_label("deck", deckid, silent=silent)

    if tx_type == "proposal":
        if proposal_id is not None: # modifications (refactor better)
            old_proposal_tx = dmu.find_proposal(proposal_id, provider)
            deckid = old_proposal_tx.deck.id
        req_amount = Decimal(str(req_amount))
        periods = int(periods)

    elif tx_type == "voting":
        vote_bool = process_vote(vote)

    elif tx_type == "signalling":
        donor_address_used = du.donor_address_used(dest_address, proposal_id)

    elif tx_type == "locking":
        timelock = int(timelock) if timelock else du.calculate_timelock(proposal_id)
        use_slot = False if force else True
        lockhash_type = 2 # TODO: P2PKH is hardcoded now, but should be done by a check on the submitted addr.
        public_address = dest_address # we need this for the redeem script
        if not txhex:
            print("Locking funds until block", timelock)

            if amount is not None:
                print("Not using slot, instead locking custom amount:", amount)

    elif tx_type == "release":
        use_slot = False if (amount is not None) else True


    basic_tx_data = get_basic_tx_data(tx_type, proposal_id=proposal_id, deckid=deckid, addresses=addresses, labels=labels, input_address=Settings.key.address, new_inputs=new_inputs, use_slot=use_slot, check_round=check_round, wait=wait, security_level=security, silent=silent)

    if tx_type == "release":
        # TODO: in this configuration we can't use origin_label for P2SH. Look if it can be reorganized.
        if new_inputs:
            # p2sh, prv, key, rscript = None, None, None, None
            rscript = None
        else:
            # p2sh = True
            # key = Settings.key # this option should not be given.
            rscript = basic_tx_data.get("redeem_script")

    elif tx_type == "signalling" and not silent:

        di.signalling_info(amount, check_round, basic_tx_data, dest_label=dest_label, donor_address_used=donor_address_used, force=force)


    # maybe integrate this later into basic_tx_data
    # TODO: address is only added to params originally in locking_tx. Is this a problem? (if yes, we can create a different "address" parameter only for locking txes)
    params = create_params(tx_type, proposal_id=proposal_id, deckid=deckid, req_amount=req_amount, epoch_number=periods, description=description, vote=vote_bool, address=public_address, lockhash_type=lockhash_type, timelock=timelock)

    rawtx = create_unsigned_trackedtx(params, basic_tx_data, change_address=change_address, raw_amount=amount, raw_tx_fee=tx_fee, network_name=Settings.network, silent=silent, debug=debug)

    return ei.output_tx(eu.finalize_tx(rawtx, verify, sign, send, redeem_script=rscript, debug=debug, silent=txhex, confirm=confirm), txhex=txhex)


def create_params(tx_type, **kwargs):
    # creates a parameter dict.
    txtype_id = c.get_id(tx_type)
    params = { "id" : txtype_id }
    for arg in kwargs:
        if kwargs[arg] is not None: # TODO recheck if this works right, or if there are None values we need.
            params.update({arg : kwargs[arg]})
    return params


def get_basic_tx_data(tx_type, proposal_id=None, input_address: str=None, dist_round: int=None, deckid: str=None, addresses: list=None, labels: list=None, check_round: int=None, security_level: int=None, wait: bool=False, new_inputs: bool=False, use_slot: bool=False, silent: bool=False, debug: bool=False):
    """Gets basic data for a new TrackedTransaction"""

    # step 1 (new): address/label synchronization
    # [dest_address, reserve_address, change_address] = ke.show_addresses([dest_address, reserve_address, change_address], [dest_label, reserve_label, change_label], Settings.network)
    if (addresses, labels) != (None, None):
        [dest_address, reserve_address, change_address] = ke.show_addresses(addresses, labels, Settings.network)

    tx_data = {"dest_address" : dest_address, "reserve_address" : reserve_address, "change_address" : change_address }

    # step 2: proposal and deck data
    if proposal_id is not None:
        proposal = find_proposal(proposal_id, provider)
        deck = proposal.deck
        tx_data.update({ "proposal_tx" : proposal })
    else:
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

    tx_data.update({"deck" : deck, "input_address" : input_address, "tx_type": tx_type, "provider" : provider })

    # step 3: check period (all except proposals.)
    if (check_round is not None) or (wait == True):
        if not du.check_current_period(proposal_id, deck, tx_type, dist_round=check_round, wait=wait, security_level=security_level):
            raise PacliInputDataError("Transaction created in wrong period.")


    # step 4: input data (only donation and locking)
    if tx_type in ("donation", "locking"):
        dist_round = du.get_dist_round(proposal_id, deck) # TODO: this can be optimized # MODIF: deck added
        if tx_type == "donation" and dist_round in range(4):
            use_locking_slot = True
        else:
            use_locking_slot = False
        tx_data.update({"use_locking_slot" : use_locking_slot})
        try:
            if (not new_inputs) or use_slot:
                tx_data.update(du.get_previous_tx_input_data(input_address, tx_type, proposal_tx=proposal, dist_round=dist_round, use_locking_slot=use_locking_slot, debug=debug, silent=silent))
        except ValueError:
            raise PacliInputDataError("No suitable signalling/reserve transactions found.")

    return tx_data


def create_unsigned_trackedtx(params: dict, basic_tx_data: dict, raw_amount: str=None, dest_address: str=None, change_address: str=None, raw_tx_fee: str=None, cltv_timelock=0, network_name=None, version=1, new_inputs: bool=False, reserve: str=None, reserve_address: str=None, force: bool=False, debug: bool=False, silent: bool=False):
    # This function first prepares a transaction, creating the protobuf string and calculating fees in an unified way,
    # then creates transaction with pypeerassets method.
    # MODIF: addresses can now come from basic_tx_data

    b = basic_tx_data
    # TODO still not perfect, may lead to None values if they're present in b. But this should be slowly replace the old method.
    reserve_address = b["reserve_address"] if "reserve_address" in b else reserve_address
    change_address = b["change_address"] if "change_address" in b else change_address
    dest_address = b["dest_address"] if "dest_address" in b else dest_address
    use_locking_slot = b["use_locking_slot"] if "use_locking_slot" in b else False

    chosen_amount = None if raw_amount is None else coins_to_sats(Decimal(str(raw_amount)), network_name=network_name)
    reserved_amount = None if reserve is None else coins_to_sats(Decimal(str(reserve)), network_name=network_name)

    tx_fee = coins_to_sats(Decimal(str(raw_tx_fee)), network_name=network_name)
    input_txid, input_vout, input_value, available_amount = None, None, None, None

    min_tx_value = legacy_mintx(network_name)
    p2th_fee = min_tx_value if min_tx_value else coins_to_sats(net_query(network_name).from_unit)

    # legacy chains need a minimum transaction value even at OP_RETURN transactions
    op_return_fee = p2th_fee if is_legacy_blockchain(network_name, "nulldata") else 0
    all_fees = tx_fee + p2th_fee + op_return_fee

    if b["tx_type"] in ("donation", "locking"):

        if (not new_inputs) and du.previous_input_unspent(basic_tx_data, silent=silent):
            # new_inputs enables the automatic selection of new inputs for locking and donation transactions.
            # this can be useful if the previous input is too small for the transaction/p2th fees, or in the case of a
            # ProposalModification
            # If new_inputs is chosen or the previous input was spent, then all the following values stay in None.
            input_txid, input_vout, input_value = b["txid"], b["vout"], b["value"]
            available_amount = input_value - all_fees
            if available_amount <= 0:
                raise PacliInputDataError("Insufficient funds in this input to pay all fees. Use --new_inputs to lock or donate this amount.")

        try:
            used_slot = b["slot"] if not use_locking_slot else b["locking_slot"]
            amount = du.calculate_donation_amount(used_slot, chosen_amount, available_amount, network_name, new_inputs, force, silent=silent)
        except KeyError:
            amount = chosen_amount
    else:
        amount = chosen_amount

    # print("Amount:", amount, "available", available_amount, "input value", input_value, "slot", slot)
    # CHANGED TO PROTOBUF
    params["ttx_version"] = 1 # NEW. for future upgradeability.
    data = serialize_ttx_metadata(params=params, network=net_query(provider.network))
    if debug and not silent:
        print("OP_RETURN size: {} bytes".format(len(data)))
    proposal_txid = params.get("proposal_id")


    return create_unsigned_tx(b["deck"], b["provider"], b["tx_type"], proposal_txid=proposal_txid, input_address=b["input_address"], amount=amount, data=data, address=dest_address, network_name=network_name, change_address=change_address, tx_fee=tx_fee, p2th_fee=p2th_fee, input_txid=input_txid, input_vout=input_vout, cltv_timelock=cltv_timelock, reserved_amount=reserved_amount, reserve_address=reserve_address, input_redeem_script=b.get("redeem_script"), silent=silent)


def process_vote(vote: str) -> bool:
    if vote in ("+", "positive", "p", "1", "yes", "y", "true"):
        vote_bool = True
    elif vote in ("-", "negative", "n", "0", "no", "n", "false"):
        vote_bool = False
    else:
        raise PacliInputDataError("Incorrect vote. Vote with 'positive'/'yes' or 'negative'/'no'.")

    return vote_bool
