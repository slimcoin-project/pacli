# Basic tools for transaction creation

from pypeerassets.networks import net_query
from pypeerassets.at.protobuf_utils import serialize_ttx_metadata # , parse_protobuf
from pypeerassets.legacy import is_legacy_blockchain, legacy_mintx #  legacy_import,
from pacli.extended_interface import PacliInputDataError
from decimal import Decimal

import pypeerassets as pa
import pacli.dt_interface as di
import pacli.extended_commands as ec
import pypeerassets.at.dt_misc_utils as dmu
import pypeerassets.at.constants as c
import pacli.extended_utils as eu
import pacli.extended_interface as ei
import pacli.dt_utils as du
import pacli.keystore_extended as ke


from pacli.provider import provider
from pacli.config import Settings

# TODO ProposalTX worked, ensure Signalling, Locking, Voting, DonationTxes work!


def create_trackedtransaction(tx_type,
                              proposal: str=None,
                              deck: str=None,
                              destination: str=None,
                              change: str=None,
                              reserve: str=None,
                              req_amount: str=None,
                              periods: int=None,
                              description: str=None,
                              vote: str=None,
                              timelock: int=None,
                              amount: str=None,
                              reserveamount: str=None,
                              tx_fee: str="0.01",
                              security: int=1,
                              check_round: int=None,
                              new_inputs: bool=False,
                              force: bool=False,
                              verify: bool=False,
                              sign: bool=False,
                              send: bool=False,
                              wait: bool=False,
                              wait_for_confirmation: bool=False,
                              txhex: bool=False,
                              debug: bool=False) -> object:
    '''Generic tracked transaction creation.'''

    ke.check_main_address_lock()
    # step 1 (new): address/label synchronization
    change_address = ec.process_address(change) if change is not None else Settings.change
    reserve_address = ec.process_address(reserve)
    dest_address = ec.process_address(destination)

    # default values for params
    use_slot = False
    lockhash_type, public_address, rscript, proposal_tx = None, None, None, None

    quiet = True if txhex else False

    # enable using own labels for decks and proposals
    proposal_id = eu.search_for_stored_tx_label("proposal", proposal, quiet=quiet) if proposal else None
    deckid = eu.search_for_stored_tx_label("deck", deck, quiet=quiet) if deck else None

    if tx_type == "proposal":
        if proposal_id is not None: # modifications (refactor better)
            old_proposal_tx = dmu.find_proposal(proposal_id, provider)
            deckid = old_proposal_tx.deck.id
        req_amount = Decimal(str(req_amount))
        periods = int(periods)
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
    else:
        # step 2: proposal and deck data
        proposal_tx = dmu.find_proposal(proposal_id, provider)
        deck = proposal_tx.deck
        if tx_type == "voting":
            vote = process_vote(vote)
        elif tx_type == "signalling":
            donor_address_used = du.donor_address_used(dest_address, proposal_id)
        elif tx_type == "donation":
            use_slot = False if (amount is not None) else True
        elif tx_type == "locking":
            use_slot = False if force else True

    basic_tx_data = {"dest_address" : dest_address,
                     "reserve_address" : reserve_address,
                     "change_address" : change_address,
                     "deck" : deck,
                     "input_address" : Settings.key.address,
                     "tx_type": tx_type,
                     "provider" : provider}

    if proposal_tx:
       basic_tx_data.update({"proposal_tx" : proposal_tx})
    if amount:
       basic_tx_data.update({"raw_amount": str(amount)})
    if reserveamount:
       basic_tx_data.update({"reserve": str(reserveamount)})
    if tx_fee:
       basic_tx_data.update({"tx_fee": str(tx_fee)})

    # step 2: check period (all except proposals.)
    if (check_round is not None) or wait:
        if not du.check_current_period(proposal_id, deck, tx_type, dist_round=check_round, wait=wait, security_level=security):
            raise PacliInputDataError("Transaction created in wrong period.")

    # basic_tx_data.update(get_basic_tx_data(tx_type, proposal_id=proposal_id, deckid=deckid, input_address=Settings.key.address, amount=amount, reserve=reserve, tx_fee=tx_fee, new_inputs=new_inputs, check_round=check_round, wait=wait, security_level=security, quiet=quiet)) # removed addresses and labels
    if tx_type in ("donation", "locking"):
        basic_tx_data.update(get_donation_state_data(tx_type, proposal_tx=proposal_tx, new_inputs=new_inputs, quiet=quiet)) # removed addresses and labels

    if tx_type == "locking":
        # timelock = int(timelock) if timelock is not None else du.calculate_timelock(proposal_id)
        timelock = int(timelock) if timelock is not None else basic_tx_data["proposal_tx"].req_timelock
        lockhash_type = 2 # TODO: P2PKH is hardcoded now, but should be done by a check on the submitted addr.
        public_address = dest_address # we need this for the redeem script

        if not txhex:
            print("Locking funds until block", timelock)

            if amount is not None:
                print("Not using slot, instead locking custom amount:", amount)

    elif tx_type == "donation":
        if new_inputs:
            rscript = None
        else:
            rscript = basic_tx_data["input_data"].get("redeem_script")

    elif tx_type == "signalling" and not quiet:

        di.signalling_info(amount, check_round, basic_tx_data, dest_label=dest_label, donor_address_used=donor_address_used, force=force)


    # maybe integrate this later into basic_tx_data
    # TODO: address is only added to params originally in locking_tx. Is this a problem? (if yes, we can create a different "address" parameter only for locking txes)
    params = create_params(tx_type, proposal_id=proposal_id, deckid=deckid, req_amount=req_amount, epoch_number=periods, description=description, vote=vote, address=public_address, lockhash_type=lockhash_type, timelock=timelock)

    rawtx = create_unsigned_trackedtx(params, basic_tx_data, force=force, quiet=quiet, debug=debug)

    return ei.output_tx(eu.finalize_tx(rawtx, verify, sign, send, redeem_script=rscript, debug=debug, quiet=txhex, ignore_checkpoint=force, confirm=wait_for_confirmation), txhex=txhex)


def create_params(tx_type: str, **kwargs) -> dict:
    # creates a parameter dict.
    txtype_id = c.get_id(tx_type)
    params = { "id" : txtype_id }
    for arg in kwargs:
        if kwargs[arg] is not None: # TODO recheck if this works right, or if there are None values we need.
            params.update({arg : kwargs[arg]})
    return params


def get_donation_state_data(tx_type: str, proposal_tx: object, dist_round: int=None, input_address: str=None, new_inputs: bool=False, quiet: bool=False, debug: bool=False) -> dict:
    """Gets basic data for a new LockingTransaction or DonationTransaction"""

    if not quiet:
        print("Searching for donation state for this transaction. Please wait.")
    try:
        proposal_state = dmu.get_proposal_state(provider, proposal_tx=proposal_tx, debug_donations=debug)
    except KeyError:
        raise PacliInputDataError("Proposal not found. Deck is probably not correctly initialized. Initialize it with 'pacli podtoken init_deck {}'.".format(deck.id))

    # TODO: re-check if this change is consistent with the rules
    # (oldest valid donation state is always the only valid one per donor address, including abandoned ones)
    dstate = dmu.get_dstates_from_donor_address(input_address, proposal_state)[0]
    # dstates = dmu.get_dstates_from_donor_address(input_address, proposal_state)
    # dstate = du.select_donation_state(dstates, tx_type, debug=debug)

    if tx_type == "donation" and dstate.dist_round in range(4):
        used_slot = dstate.effective_locking_slot
    else:
        used_slot = dstate.slot

    tx_data = {"used_slot" : used_slot}

    try:
        if (not new_inputs):
            input_data = du.get_previous_tx_input_data(tx_type, dstate, debug=debug, quiet=quiet)
            tx_data.update({"input_data" : input_data})
    except ValueError:
        raise PacliInputDataError("No valid signalling/reserve transactions found.")

    return tx_data


def create_unsigned_trackedtx(params: dict, basic_tx_data: dict, version=1, force: bool=False, debug: bool=False, quiet: bool=False) -> object:

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

    chosen_amount = None if raw_amount is None else dmu.coins_to_sats(Decimal(str(raw_amount)), network_name=network_name)
    reserved_amount = None if reserve is None else dmu.coins_to_sats(Decimal(str(reserve)), network_name=network_name)

    tx_fee = dmu.coins_to_sats(dec_tx_fee, network_name=network_name)
    input_txid, input_vout, input_value, available_amount = None, None, None, None

    min_tx_value = legacy_mintx(network_name)
    p2th_fee = min_tx_value if min_tx_value else dmu.coins_to_sats(net_query(network_name).from_unit)

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
            amount = du.calculate_donation_amount(used_slot, chosen_amount, available_amount, network_name, new_inputs, force, quiet=quiet)
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


    return dmu.create_unsigned_tx(b["deck"], b["provider"], b["tx_type"], proposal_txid=proposal_txid, input_address=b["input_address"], amount=amount, data=data, address=dest_address, network_name=Settings.network, change_address=change_address, tx_fee=tx_fee, p2th_fee=p2th_fee, input_txid=input_txid, input_vout=input_vout, cltv_timelock=cltv_timelock, reserved_amount=reserved_amount, reserve_address=reserve_address, input_redeem_script=redeem_script, silent=quiet)


def process_vote(vote: str) -> bool:
    if vote in ("+", "positive", "p", "1", "yes", "y", "true"):
        vote_bool = True
    elif vote in ("-", "negative", "n", "0", "no", "n", "false"):
        vote_bool = False
    else:
        raise PacliInputDataError("Incorrect vote. Vote with 'positive'/'yes' or 'negative'/'no'.")

    return vote_bool
