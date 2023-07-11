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
                              proposal: str=None,
                              deck: str=None,
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
    use_slot = False
    lockhash_type, public_address, rscript = None, None, None

    silent = True if txhex else False

    # enable using own labels for decks and proposals
    if proposal:
        proposal_id = eu.search_for_stored_tx_label("proposal", proposal, silent=silent)

    if deck:
        deckid = eu.search_for_stored_tx_label("deck", deck, silent=silent)

    if tx_type == "proposal":
        if proposal_id is not None: # modifications (refactor better)
            old_proposal_tx = dmu.find_proposal(proposal_id, provider)
            deckid = old_proposal_tx.deck.id
        req_amount = Decimal(str(req_amount))
        periods = int(periods)

    elif tx_type == "voting":
        vote = process_vote(vote)

    elif tx_type == "signalling":
        donor_address_used = du.donor_address_used(dest_address, proposal_id)

    elif tx_type == "locking":
        timelock = int(timelock) if timelock is not None else du.calculate_timelock(proposal_id)
        use_slot = False if force else True
        lockhash_type = 2 # TODO: P2PKH is hardcoded now, but should be done by a check on the submitted addr.
        public_address = dest_address # we need this for the redeem script
        if not txhex:
            print("Locking funds until block", timelock)

            if amount is not None:
                print("Not using slot, instead locking custom amount:", amount)

    elif tx_type == "donation":
        use_slot = False if (amount is not None) else True

    # TODO: maybe we could create a basic_tx_data string here with the fixed parameters and only delegate the
    # variable parameters to get_basic_tx_data?
    basic_tx_data = get_basic_tx_data(tx_type, proposal_id=proposal_id, deckid=deckid, addresses=addresses, labels=labels, input_address=Settings.key.address, amount=amount, reserve=reserve, tx_fee=tx_fee, new_inputs=new_inputs, check_round=check_round, wait=wait, security_level=security, silent=silent)

    if tx_type == "donation":
        if new_inputs:
            # p2sh, prv, key, rscript = None, None, None, None
            rscript = None
        else:
            # p2sh = True
            # key = Settings.key # this option should not be given.
            rscript = basic_tx_data["input_data"].get("redeem_script")

    elif tx_type == "signalling" and not silent:

        di.signalling_info(amount, check_round, basic_tx_data, dest_label=dest_label, donor_address_used=donor_address_used, force=force)


    # maybe integrate this later into basic_tx_data
    # TODO: address is only added to params originally in locking_tx. Is this a problem? (if yes, we can create a different "address" parameter only for locking txes)
    params = create_params(tx_type, proposal_id=proposal_id, deckid=deckid, req_amount=req_amount, epoch_number=periods, description=description, vote=vote, address=public_address, lockhash_type=lockhash_type, timelock=timelock)

    rawtx = create_unsigned_trackedtx(params, basic_tx_data, force=force, silent=silent, debug=debug)

    return ei.output_tx(eu.finalize_tx(rawtx, verify, sign, send, redeem_script=rscript, debug=debug, silent=txhex, confirm=confirm), txhex=txhex)


def create_params(tx_type, **kwargs):
    # creates a parameter dict.
    txtype_id = c.get_id(tx_type)
    params = { "id" : txtype_id }
    for arg in kwargs:
        if kwargs[arg] is not None: # TODO recheck if this works right, or if there are None values we need.
            params.update({arg : kwargs[arg]})
    return params


def get_basic_tx_data(tx_type, proposal_id=None, input_address: str=None, dist_round: int=None, deckid: str=None, addresses: list=None, labels: list=None, amount: str=None, tx_fee: str=None, reserve: str=None, check_round: int=None, security_level: int=None, wait: bool=False, new_inputs: bool=False, silent: bool=False, debug: bool=False):
    """Gets basic data for a new TrackedTransaction"""

    # step 1 (new): address/label synchronization
    if (addresses, labels) != (None, None):
        [dest_address, reserve_address, change_address] = ke.show_addresses(addresses, labels, Settings.network)

    tx_data = {"dest_address" : dest_address, "reserve_address" : reserve_address, "change_address" : change_address }

    if amount:
       tx_data.update({"raw_amount": str(amount)})
    if reserve:
       tx_data.update({"reserve": str(reserve)})
    if tx_fee:
       tx_data.update({"tx_fee": str(tx_fee)})

    # step 2: proposal and deck data
    if proposal_id is not None:
        proposal_tx = find_proposal(proposal_id, provider)
        deck = proposal_tx.deck
        tx_data.update({ "proposal_tx" : proposal_tx })
    else:
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

    tx_data.update({"deck" : deck, "input_address" : input_address, "tx_type": tx_type, "provider" : provider })

    # step 3: check period (all except proposals.)
    if (check_round is not None) or wait:
        if not du.check_current_period(proposal_id, deck, tx_type, dist_round=check_round, wait=wait, security_level=security_level):
            raise PacliInputDataError("Transaction created in wrong period.")


    # step 4: input data (only donation and locking)
    if tx_type in ("donation", "locking"):
        if not silent:
            print("Searching for donation state for this transaction. Please wait.")
        try:
            proposal_state = get_proposal_state(provider, proposal_tx=proposal_tx, debug_donations=debug)
        except KeyError:
            raise PacliInputDataError("Proposal not found. Deck is probably not correctly initialized. Initialize it with 'pacli podtoken init_deck {}'.".format(deck.id))
        dstates = dmu.get_dstates_from_donor_address(input_address, proposal_state)
        dstate = du.select_donation_state(dstates, tx_type, debug=debug)
        # dist_round = du.get_dist_round(proposal_id, deck)
        if tx_type == "donation" and dstate.dist_round in range(4):
            used_slot = dstate.effective_locking_slot
        else:
            used_slot = dstate.slot
        tx_data.update({"used_slot" : used_slot})
        try:
            if (not new_inputs): # or use_slot: # MODIF: use_slot here doesn't make sense, as the --force parameter determines if the slot or another amount is used. --force can be used also if the old input is used.

                # MODIF: input_data function was limited to pure input data gathering.
                input_data = du.get_previous_tx_input_data(tx_type, dstate, debug=debug, silent=silent)
                # tx_data.update(input_data)
                tx_data.update({"input_data" : input_data})
        except ValueError:
            raise PacliInputDataError("No suitable signalling/reserve transactions found.")

    return tx_data


def create_unsigned_trackedtx(params: dict, basic_tx_data: dict, version=1, force: bool=False, debug: bool=False, silent: bool=False):

    # This function first prepares a transaction, creating the protobuf string and calculating fees in an unified way,
    # then creates transaction with pypeerassets method.
    # MODIF: addresses now all come from basic_tx_data
    # MODIF: new_inputs now can be ignored, because only no_inputs makes b["input_data"] empty
    # TODO: we may rename force to use_slot again (must be negative, i.e. force = True -> use_slot = False)

    b = basic_tx_data
    network_name = Settings.network
    # TODO still not perfect, may lead to None values if they're present in b. But this should be slowly replace the old method.
    reserve_address = b.get("reserve_address") # if "reserve_address" in b else reserve_address
    change_address = b.get("change_address") # if "change_address" in b else change_address
    dest_address = b.get("dest_address") # if "dest_address" in b else dest_address
    used_slot = b.get("used_slot")
    raw_amount = b.get("raw_amount")
    dec_tx_fee = Decimal(b["raw_tx_fee"]) if "raw_tx_fee" in b else net_query(network_name).min_tx_fee
    reserve = b.get("reserve")

    chosen_amount = None if raw_amount is None else coins_to_sats(Decimal(str(raw_amount)), network_name=network_name)
    reserved_amount = None if reserve is None else coins_to_sats(Decimal(str(reserve)), network_name=network_name)

    # tx_fee = coins_to_sats(Decimal(str(raw_tx_fee)), network_name=network_name)
    tx_fee = coins_to_sats(dec_tx_fee, network_name=network_name)
    input_txid, input_vout, input_value, available_amount = None, None, None, None

    min_tx_value = legacy_mintx(network_name)
    p2th_fee = min_tx_value if min_tx_value else coins_to_sats(net_query(network_name).from_unit)

    # legacy chains need a minimum transaction value even at OP_RETURN transactions
    op_return_fee = p2th_fee if is_legacy_blockchain(network_name, "nulldata") else 0
    all_fees = tx_fee + p2th_fee + op_return_fee

    if b["tx_type"] in ("donation", "locking"):

        if b.get("input_data"):
            redeem_script = b["input_data"].get("redeem_script")
            if debug and redeem_script:
                print("Redeem script:", redeem_script)
            new_inputs = False
            # new_inputs enables the automatic selection of new inputs for locking and donation transactions.
            # this can be useful if the previous input is too small for the transaction/p2th fees, or in the case of a
            # ProposalModification
            # If new_inputs is chosen or the previous input was spent, then all the following values stay in None.
            input_txid, input_vout, input_value = b["input_data"]["txid"], b["input_data"]["vout"], b["input_data"]["value"]
            available_amount = input_value - all_fees
            if available_amount <= 0:
                raise PacliInputDataError("Insufficient funds to pay all fees. Use --new_inputs to lock or donate this amount.")
        else:
            new_inputs = True # try to refactor

        try:
            # used_slot = b["slot"] if not use_locking_slot else b["locking_slot"] # MODIF: this switch is in basic_tx_data
            amount = du.calculate_donation_amount(used_slot, chosen_amount, available_amount, network_name, new_inputs, force, silent=silent)
        except KeyError:
            amount = chosen_amount
    else:
        amount = chosen_amount
        redeem_script = None

    params["ttx_version"] = 1 # NEW. for future upgradeability.

    data = serialize_ttx_metadata(params=params, network=net_query(provider.network))

    if debug:
        print("OP_RETURN size: {} bytes".format(len(data)))

    proposal_txid = params.get("proposal_id")
    cltv_timelock = params.get("timelock")


    return create_unsigned_tx(b["deck"], b["provider"], b["tx_type"], proposal_txid=proposal_txid, input_address=b["input_address"], amount=amount, data=data, address=dest_address, network_name=Settings.network, change_address=change_address, tx_fee=tx_fee, p2th_fee=p2th_fee, input_txid=input_txid, input_vout=input_vout, cltv_timelock=cltv_timelock, reserved_amount=reserved_amount, reserve_address=reserve_address, input_redeem_script=redeem_script, silent=silent)


def process_vote(vote: str) -> bool:
    if vote in ("+", "positive", "p", "1", "yes", "y", "true"):
        vote_bool = True
    elif vote in ("-", "negative", "n", "0", "no", "n", "false"):
        vote_bool = False
    else:
        raise PacliInputDataError("Incorrect vote. Vote with 'positive'/'yes' or 'negative'/'no'.")

    return vote_bool
