from pypeerassets.at.dt_entities import ProposalTransaction, SignallingTransaction, LockingTransaction, DonationTransaction, VotingTransaction, InvalidTrackedTransactionError
from pypeerassets.provider import Provider
from pypeerassets.at.dt_states import ProposalState, DonationState
from pypeerassets.at.dt_parser_state import ParserState
from pypeerassets.at.transaction_formats import P2TH_MODIFIER, PROPOSAL_FORMAT, TX_FORMATS, getfmt, setfmt
from pypeerassets.at.dt_misc_utils import import_p2th_address, create_unsigned_tx, get_proposal_state, sign_p2sh_transaction, proposal_from_tx, get_parser_state, coin_value, sats_to_coins, coins_to_sats
from pypeerassets.at.dt_parser_utils import deck_from_tx, get_proposal_states, get_marked_txes
from pypeerassets.pautils import read_tx_opreturn, load_deck_p2th_into_local_node
from pypeerassets.kutil import Kutil
from pypeerassets.transactions import sign_transaction, MutableTransaction
from pypeerassets.networks import net_query, PeercoinMainnet, PeercoinTestnet
from pypeerassets.legacy import is_legacy_blockchain, legacy_import
from pacli.utils import (cointoolkit_verify,
                         signtx,
                         sendtx)
from pacli.keystore import get_key
from decimal import Decimal
from prettyprinter import cpprint as pprint
# import keyring
import pypeerassets.at.dt_periods as dp
import pacli.dt_interface as di
import pypeerassets.at.dt_misc_utils as dmu

from pacli.provider import provider
from pacli.config import Settings


def check_current_period(proposal_txid, tx_type, dist_round=None, phase=None, release=False, wait=False):
    # TODO should be reorganized so the ProposalState isn't created 2x!
    # Re-check side effects of get_period change. => Seems OK, but take the change into account.

    current_period, blocks = get_period(proposal_txid)
    print("Current period:", di.printout_period(current_period, blocks))
    try:
        target_period = get_next_suitable_period(tx_type, current_period)
    except ValueError as e:
        print(e)
        return False

    proposal_tx = proposal_from_tx(proposal_txid, provider)
    ps = ProposalState(first_ptx=proposal_tx, valid_ptx=proposal_tx, provider=provider)
    startblock, endblock = dp.get_startendvalues(target_period, ps)

    return di.wait_for_block(startblock, endblock, provider, wait)

def get_next_suitable_period(tx_type, period):
    # TODO: maybe it would be simpler to assign all suitable periods to all tx types,
    # and then iterate over the index.
    print("Period", period, tx_type)
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
        assert (period[0] in ("B", "D")) and (period[1] > 10)
        if period[0] == "B":
            return (period[1] // 10) - 1
        elif period[0] == "D":
            return (period[1] // 10) + 4 - 1
    except AssertionError:
        return None


def get_all_periods(proposal_txid):
    # this one gets ALL periods from the current proposal, according to the last modification.
    ps = dummy_pstate(proposal_txid)
    return dp.get_period_dict(ps)


def init_deck(network, deckid, rescan=True):
    deck = deck_from_tx(deckid, provider)
    if deckid not in provider.listaccounts():
        provider.importprivkey(deck.p2th_wif, deck.id, rescan)
        print("Importing P2TH address from deck.")
    check_addr = provider.validateaddress(deck.p2th_address)
    print(check_addr)
        # load_deck_p2th_into_local_node(provider, deck) # we don't use this here because it doesn't provide the rescan option



def init_dt_deck(network_name, deckid, rescan=True):
    # MODIFIED: added support for legacy blockchains
    deck = deck_from_tx(deckid, provider)
    legacy = is_legacy_blockchain(network_name)
    if deck.id not in provider.listaccounts():
        print("Importing main key from deck.")
        load_deck_p2th_into_local_node(provider, deck)

    for tx_type in ("proposal", "signalling", "locking", "donation", "voting"):
        p2th_addr = deck.derived_p2th_address(tx_type)
        print("Importing {} P2TH address: {}".format(tx_type, p2th_addr))
        if legacy:
            p2th_wif = deck.derived_p2th_wif(tx_type)
            legacy_import(provider, p2th_addr, p2th_wif, rescan)
        else:
            import_p2th_address(provider, p2th_addr)

    # SDP
    if deck.sdp_deckid is not None:
        p2th_sdp_addr = Kutil(network=network_name,
                             privkey=bytearray.fromhex(deck.sdp_deckid)).address
        print(deck.sdp_deckid)
        print("Importing SDP P2TH address: {}".format(p2th_sdp_addr))

        if legacy:
            p2th_sdp_wif = Kutil(network=network_name,
                             privkey=bytearray.fromhex(deck.sdp_deckid)).wif
            legacy_import(provider, p2th_sdp_addr, p2th_sdp_wif, rescan)
        else:
            import_p2th_address(provider, p2th_sdp_addr)
    if rescan:
        if not legacy:
            print("Rescanning ...")
            provider.rescanblockchain()
    print("Done.")

# Proposal and donation states

def get_proposal_state_periods(deckid, block, advanced=False, debug=False):
    # MODIFIED: whole state is returned, not only id.
    # Advanced mode calls the parser, thus much slower, and shows other parts of the state.

    result = {}
    deck = deck_from_tx(deckid, provider)
    try:
       assert deck.at_type == "DT"
    except (AssertionError, AttributeError):
       raise ValueError("Not a DT Proof of Donation deck.")

    if advanced:
        pst = get_parser_state(provider, deck, force_continue=True, force_dstates=True, debug=debug) # really necessary?
        pstates = pst.proposal_states
    else:
        pstates = get_proposal_states(provider, deck)

    for proposal_txid in pstates:
        print("proposal:", proposal_txid)
        ps = pstates[proposal_txid]
        period, blockheights = get_period(proposal_txid, blockheight=block)
        state_data = {"state": ps, "startblock" : blockheights[0], "endblock" : blockheights[1]}
        #period_data = get_period(proposal_txid, blockheight=block)
        #period = period_data[:2] # MODIFIED: this orders the list only by the letter code, not by start/end block!
        #state_data = {"state": ps, "startblock" : period_data[2], "endblock" : period_data[3]}

        try:
            result[period].append(state_data)
        except KeyError:
            result.update({period : [state_data]})
    return result

def get_proposal_info(proposal_txid):
    # MODIFIED: state removed, get_proposal_state should be used.
    proposal_tx = proposal_from_tx(proposal_txid, provider)
    return proposal_tx.__dict__

def get_previous_tx_input_data(address, tx_type, proposal_id=None, proposal_tx=None, previous_txid=None, dist_round=None, debug=False, use_slot=True):
    # TODO: The previous_txid parameter seems to be unused, check if really needed, because it complicates the code.
    # provides the following data: slot, txid and vout of signalling or locking tx, value of input.
    # starts the parser.
    inputdata = {}
    print("Searching for signalling or reserve transaction. Please wait.")
    dstate = dmu.get_donation_states(provider, proposal_tx=proposal_tx, tx_txid=previous_txid, address=address, dist_round=dist_round, debug=debug, pos=0) # MODIFIED: removed unused parameter only_signalling=True
    if not dstate:
        raise ValueError("No donation states found.")
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

    inputdata.update({ "txid" : prev_tx.txid, "vout" : 2, "value" : prev_tx.amount, "slot" : dstate.slot})

    # Output type. This should be always P2PKH or P2SH.
    if prev_tx:
        inputdata.update({ "inp_type" : [prev_tx.outs[2].script_pubkey.type] })
    #if use_slot:
    #    inputdata.update({"slot" : dstate.slot}) # added slot mandatorily, TODO: re-check if this change does not have side effects!
    return inputdata

def get_pod_reward_data(proposal_id, donor_address, proposer=False, debug=False, network_name="tppc"):
    # VERSION with donation states. better because simplicity (proposal has to be inserted), and the convenience to use directly the get_donation_state function.
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

        try:
            ds = dmu.get_donation_states(provider, proposal_tx=ptx, address=donor_address, phase=1, debug=debug)[0]
        except IndexError:
            raise Exception("ERROR: No valid donation state found.")

        # print("Your donation:", Decimal(ds.donated_amount) / coin, "coins")
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

## Inputs, outputs and Transactions

def get_basic_tx_data(tx_type, proposal_id=None, input_address: str=None, dist_round: int=None, deckid: str=None, new_inputs: bool=False, use_slot: bool=False, debug: bool=False):
    """Gets basic data for a new TrackedTransaction"""
    # TODO: maybe change "txid" and "vout" to "input_txid" and "input_vout"

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
                tx_data.update(get_previous_tx_input_data(input_address, tx_type, proposal_tx=proposal, dist_round=dist_round, debug=debug, use_slot=use_slot))
        except ValueError:
            raise ValueError("No suitable signalling/reserve transactions found.")

    return tx_data


def calculate_donation_amount(slot: int, chosen_amount: int, available_amount: int, network_name: str, new_inputs: bool=False, force: bool=False):

    raw_slot = sats_to_coins(Decimal(slot), network_name=network_name)
    raw_amount = sats_to_coins(Decimal(chosen_amount), network_name=network_name) if chosen_amount is not None else None

    print("Assigned slot:", raw_slot)
    print("slot", slot, "raw_slot", raw_slot, "chosen_amount", chosen_amount, "raw_amount", raw_amount)

    # You should only be able to use an amount greater than your slot if you use --force.
    if not force:
        effective_slot = min(slot, chosen_amount) if chosen_amount is not None else slot
        amount = min(available_amount, effective_slot) if available_amount else effective_slot
        if amount == 0:
            raise Exception("No slot available for this donation. Transaction will not be created.")
    elif new_inputs and (chosen_amount is not None):
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

def create_unsigned_trackedtx(params: dict, basic_tx_data: dict, raw_amount=None, dest_address=None, change_address=None, raw_tx_fee=None, raw_p2th_fee=None, cltv_timelock=0, network_name=None, version=1, new_inputs: bool=False, reserve: str=None, reserve_address: str=None, force: bool=False, debug: bool=False):
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

        amount = calculate_donation_amount(b["slot"], chosen_amount, available_amount, network_name, new_inputs, force)

    else:
        amount = chosen_amount

    # print("Amount:", amount, "available", available_amount, "input value", input_value, "slot", slot)

    data = setfmt(params, tx_type=b["tx_type"])

    return create_unsigned_tx(b["deck"], b["provider"], b["tx_type"], input_address=b["input_address"], amount=amount, data=data, address=dest_address, network_name=network_name, change_address=change_address, tx_fee=tx_fee, p2th_fee=p2th_fee, input_txid=input_txid, input_vout=input_vout, cltv_timelock=cltv_timelock, reserved_amount=reserved_amount, reserve_address=reserve_address, input_redeem_script=b.get("redeem_script"))

def calculate_timelock(proposal_id):
    # returns the number of the block where the working period of the Proposal ends.

    first_proposal_tx = proposal_from_tx(proposal_id, provider)
    # print("first tx info", first_proposal_tx.blockheight, first_proposal_tx.epoch, first_proposal_tx.deck.epoch_length, first_proposal_tx.epoch_number)
    cltv_timelock = (first_proposal_tx.epoch + first_proposal_tx.epoch_number + 1) * first_proposal_tx.deck.epoch_length
    return cltv_timelock

def finalize_tx(rawtx, verify, sign, send, redeem_script=None, label=None, key=None, input_types=None):
    # groups the last steps together

    if verify:
        print(
            cointoolkit_verify(rawtx.hexlify())
             )  # link to cointoolkit - verify

    if sign:
        if redeem_script is not None:
            # TODO: in theory we need to solve inputs from --new_inputs separately from the p2sh inputs.
            # For now we can only use new_inputs OR spend the P2sh.
            try:
                # tx = signtx_p2sh(provider, rawtx, redeem_script, key)
                tx = sign_p2sh_transaction(provider, rawtx, redeem_script, Settings.key)
            except NameError as e:
                print("Exception:", e)
                #    return None

        elif ((key is not None) or (label is not None)) and (provider is not None): # sign with a different key
            tx = signtx_by_key(rawtx, label=label, key=key)
            # we need to check the type of the input, as the Kutil method cannot sign P2PK
        elif input_types is not None:
            print("Input types", input_types)
            if "p2pk" not in input_types:
                tx = sign_transaction(provider, rawtx, Settings.key)
            else:
                tx = sign_mixed_transaction(provider, rawtx, Settings.key, input_types)
        else:
            # fallback, will not always work, try to avoid!
            tx = sign_transaction(provider, rawtx, Settings.key)
            # tx = signtx(rawtx)



        if send:
            pprint({'txid': sendtx(tx)})
        return {'hex': tx.hexlify()}

    return rawtx.hexlify()

def create_trackedtx(txid=None, txhex=None):
    """Creates a TrackedTransaction object from a raw transaction or txid."""
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
           raise ValueError("No key nor key id provided.")

    return sign_transaction(provider, rawtx, key)

#def signtx_p2sh(provider, raw_tx, redeem_script, key):
#    return sign_p2sh_transaction(provider, raw_tx, redeem_script, key)
# ### unnecessary as it's not called from __main__ anymore ###

## Keys and Addresses

def get_all_labels(prefix):
    # returns all labels corresponding to a network shortname (the prefix)
    # does currently NOT support Windows Credential Locker nor KDE.
    # Should work with Gnome Keyring, KeepassXC, and KSecretsService.
    import secretstorage
    bus = secretstorage.dbus_init()
    collection = secretstorage.get_default_collection(bus)
    labels = []
    for item in collection.search_items({'application': 'Python keyring library', "service" : "pacli"}):
        # print(item.get_label())
        label = item.get_attributes()["username"]
        if prefix in label:
            labels.append(label)

    return labels

def show_stored_key(label: str, network_name: str, pubkey: bool=False, privkey: bool=False, wif: bool=False, json_mode=False, legacy=False):
    # TODO: json_mode (only for addresses)
    if legacy:
       fulllabel = "key_bak_" + label
    else:
       fulllabel = "key_" + network_name + "_" + label
    try:
        raw_key = bytearray.fromhex(get_key(fulllabel))
    except TypeError:
        exc_text = "No key data for key {}".format(fulllabel)
        raise Exception(exc_text)

    key = Kutil(network=network_name, privkey=raw_key)

    if privkey:
        return key.privkey
    elif pubkey:
        return key.pubkey
    elif wif:
        return key.wif
    else:
        return key.address

def show_stored_address(keyid: str, network_name: str, json_mode=False):
    # Safer mode for show_stored_key.
    # TODO: json mode still unfinished.
    return show_stored_key(keyid, network_name=network_name, json_mode=json_mode)

def show_addresses(addrlist: list, keylist: list, network: str, debug=False):
    if len(addrlist) != len(keylist):
        raise ValueError("Both lists must have the same length.")
    result = []
    for kpos in range(len(keylist)):
        if (addrlist[kpos] == None) and (keylist[kpos] is not None):

            adr = show_stored_address(keylist[kpos], network_name=network)
            if debug: print("Address", adr, "got from key", keylist[kpos])
        else:
            adr = addrlist[kpos]
        result.append(adr)
    return result

def get_deckinfo(deckid):
    d = deck_from_tx(deckid, provider)
    return d.__dict__

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

def show_votes_by_address(deckid, address):
    # shows all valid voting transactions from a specific address.
    # Does not show the weight (this would require the parser).
    pprint("Votes cast from address: " + address)
    vote_readable = { b'+' : 'Positive', b'-' : 'Negative' }
    deck = deck_from_tx(deckid, provider)
    # TODO: incompatible with new ParserState.get_voting_txes solution.
    # we create a dummy ParserState object without cards.
    ps = ParserState(deck, [], provider)
    vtxes = ps.get_voting_txes()
    # vtxes = get_voting_txes(provider, deck)
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


