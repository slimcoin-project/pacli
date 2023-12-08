from time import sleep
from prettyprinter import cpprint as pprint
from decimal import Decimal
from pypeerassets.at.dt_entities import TrackedTransaction
from pypeerassets.at.dt_states import DonationState
from pypeerassets.at.dt_misc_utils import coins_to_sats
from pypeerassets.protocol import Deck
from pacli.provider import provider
from pacli.config import Settings
from pacli.extended_interface import PacliInputDataError


def printout_period(period: tuple, blockheights: list, show_blockheights: bool=False, blockheights_first: bool=False) -> str:
    # MODIF: changed order to fix bug with period D50.
    [start, end] = blockheights
    if end == None:
        end = "End of chain"
    bhs, bf = "", ""
    if show_blockheights:
        bhs = " (start: {}, end: {})".format(start, end)
    elif blockheights_first:
        bf = "{}-{}: ".format(start, end)
    if period == ("A", 0):
        return "{}Period A0: Before the proposal submission{}.".format(bf, bhs)
    elif period == ("A", 1):
        return "{}Period A1: Before the distribution start of the Initial Phase{}.".format(bf, bhs)
    elif period == ("B", 0):
        return "{}Period B0: Before the distribution start of the Initial Phase (security period){}.".format(bf, bhs)
    elif period == ("B", 1):
        return "{}Period B1: Voting Round 1.".format(bf, bhs)
    elif period[0] == "B":
        if period[1] % 10 == 0:
             return "{}Period B{}: Initial Slot Distribution, round {} Signalling Phase.{}".format(bf, period[1], period[1]//10, bhs)
        else:
             return "{}Period B{}: Initial Slot Distribution, round {} Locking Phase.{}".format(bf, period[1], period[1]//10, bhs)
    elif period == ("C", 0):
        return "{}Period C0: Working phase (no voting nor slot distribution ongoing).{}".format(bf, bhs)
    elif period == ("D", 0):
        return "{}Period D0: Before the distribution start of the Final Phase (security period).{}".format(bf, bhs)
    elif period == ("D", 1):
        return "{}Period D1: Voting Round 2.{}".format(bf, bhs)
    elif period == ("D", 2):
        return "{}Period D2: Donation Release Period.{}".format(bf, bhs)
    elif period == ("D", 50):
        return "{}Period D50. Remaining period of Final Phase (reward claiming still not allowed).{}".format(bf, bhs)
    elif period[0] == "D":
        if period[1] % 10 == 0:
             return "{}Period D{}: Final Slot Distribution, round {} Signalling Phase.{}".format(bf, period[1], period[1]//10, bhs)
        else:
             return "{}Period D{}: Final Slot Distribution, round {} Donation Phase.{}".format(bf, period[1], period[1]//10, bhs)

    elif period == ("E", 0):
        return "{}Period E. Distribution finished (reward claiming allowed if proposal was successful).{}".format(bf, bhs)

## Display info about decks, transactions, proposals etc.

def itemprint(lst):
    try:
        if issubclass(type(lst[0]), TrackedTransaction):
            print([t.txid for t in lst])
        else:
            print(lst)
    except (IndexError, AttributeError):
        print(lst)

def dictmod_recursive(item): # recursive function for test.
    if type(item) == list: # tuples will be returned as they are.
        for index, value in enumerate(item):
            item[index] = dictmod_recursive(value)
    elif type(item) == dict:
        for key, value in item.items():
            item[key] = dictmod_recursive(value)

    elif issubclass(type(item), TrackedTransaction):
        # txid must be done apart as it's private
        item = { "txid" : item.txid, **simpledict(item.__dict__, TrackedTransaction) }
        # item = { "txid" : item.txid } | simpledict(item.__dict__, TrackedTransaction) # once python3.9 is standard this can be used
    elif issubclass(type(item), Deck):
        item = item.id
    elif type(item) == DonationState:
        item = simpledict(item.__dict__, type(item))
    return item

def prepare_dict(d, only_txids=["all_signalling_txes", "all_locking_txes", "all_donation_txes", "all_voting_txes"], only_id=[], only_ids=[]):
    # successor to update2levels
    # prepares a dict with 2 levels like ProposalState for prettyprinting.
    # does not return the dictionary, but modify an existing one.
    for key, value in d.items():
        # first, rule out special cases where we want a simplified display (only the txid)
        if key in only_txids:
           try:
               d[key] = [ t.txid for t in value ]
           except AttributeError: # gets thrown if trying to apply this to a dict instead of an object
               d[key] = [ v.txid for k, v in value.items() ]
        elif key in only_ids: # use for dictionaries
           d[key] = [ v.id for k, v in value.items() ]
        elif key in only_id:
           d[key] = value.id
        else:
           d[key] = dictmod_recursive(value)


def prepare_complete_collection(d):
    if type(d) == dict:
        # version which shows always all items.
        for key, value in d.items():
            d[key] = show_recursive(value)
    if type(d) in (list, tuple, set):
        for i, value in enumerate(d):
            d[i] = show_recursive(value)

def show_recursive(item):
    if type(item) == dict:
        return { key : show_recursive(val) for (key, val) in item.items() } # {key:value for (key,value) in dictonary.items()}
    elif type(item) in (list, tuple, set):
        return [ show_recursive(i) for i in item ]
    elif type(item) in (int, float, str):
        return item
    elif issubclass(type(item), TrackedTransaction):
        return { key : show_recursive(val) for (key, val) in item.__dict__.items() }
    else:
        return str(item)

def simpledict(orig_dict: dict, object_type, show_items: list=None):
    if not show_items:
        if object_type == TrackedTransaction:
            show_items = ["amount", "vote", "vote_weight", "address", "reserve_address", "reserved_amount"]
        elif object_type == DonationState:
            show_items = ["donor_address", "donated_amount", "state" ]
    return { k : orig_dict[k] for k in show_items if k in orig_dict }

def txdisplay(tx, show_items: list=["amount", "address", "reserve_address", "reserved_amount", "proposal_txid"]):
    # displays transactions in a meaningful way without showing the whole dict
    # simpledict => dict comprehension version.
    displaydict = { "txid" : tx.txid }
    txdict = tx.__dict__
    for item in txdict:
        if item in show_items:
            displaydict.update({item : txdict[item]})
    return displaydict

def update_2levels(d): # obsolete, will be replaced by the recursive function.
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

def wait_for_block(startblock: int, endblock: int, provider: object, wait: bool=False, silent: bool=False):
    # This function enables the "wait" option. It loops each 15 sec until the target period is correctly reached.
    # It will terminate and launch the transaction creator when the start block has been reached,
    # or exit without launching if the end block has passed.
    # If "wait" is set to False, then if the blockheight is outside the target period, the function exits after one loop.
    startendvalues = "(between block: {}, and block: {}).".format(startblock, endblock)
    oldblock = 0
    if not silent:
        print("Waiting for target block height", startendvalues)
        print("The target timeframe is influenced by your selected security level.")
    while True:
        current_block = provider.getblockcount()
        if current_block == oldblock:
            sleep(15)
            continue
        # We need always to trigger the transaction one block before the begin of the period.
        next_block = current_block + 1


        if startblock <= next_block <= endblock:
            if not silent:
                print("Next block is inside the target timeframe", startendvalues)
                print("Transaction will probably be included in block:", current_block + 1, "- last block:", current_block)
            return True
        else:

            if next_block < startblock:
                if not silent:
                   print("Current block height:", current_block)
                   # print("Period still not reached", startendvalues)
                   # print("Transaction would probably be included in block:", next_block, "- current block:", current_block)
                if not wait:
                    return False
                sleep(15)
                oldblock = current_block
            else:
                # MODIF: we raise an error here. So we ensure the transaction isn't processed.
                #if not silent:
                #    print("Target deadline has already passed", startendvalues)
                #    print("Current block:", current_block)
                raise PacliInputDataError("Target deadline has already passed {}. Current block: {}".format(startendvalues, current_block))

def get_allowed_states(all: bool, unclaimed: bool, only_incomplete: bool):

    allowed_states = []
    if only_incomplete:
        allowed_states = ["incomplete"]
    elif unclaimed:
        allowed_states = ["complete"]
    else:
        allowed_states = ["incomplete", "complete", "claimed"]
        if all:
            allowed_states.append("abandoned")

    return allowed_states

def signalling_info(amount: str, check_round: int, basic_tx_data: dict, dest_label: str=None, force: bool=False, donor_address_used: bool=False) -> None:

    dest_address = basic_tx_data["dest_address"]
    deck = basic_tx_data["deck"]
    proposal_tx = basic_tx_data["proposal_tx"]
    if donor_address_used:
        raise PacliInputDataError("Your donor address was already used. Choose another one.")
    print("You are signalling {} coins.".format(amount))
    print("Your donation address: {}".format(dest_address))
    if dest_label is not None:
        print("Label: {}".format(dest_label))

    # decimals = basic_tx_data["deck"].number_of_decimals

    reward_units = deck.epoch_quantity
    req_amount = proposal_tx.req_amount
    amount_sats = coins_to_sats(Decimal(str(amount)), provider.network)
    min_reward_amount = req_amount / reward_units
    print("Reward per epoch:", reward_units)
    print("Requested amount:", req_amount)
    print("Amount in sats (minimum units):", amount_sats)

    print("Expected maximum reward:", min(amount_sats / req_amount, 1) * reward_units)

    if (amount_sats > req_amount) and (not force):
        raise PacliInputDataError("You are signalling more coins than the requested amount of the Proposal you would support. Repeat command using --force to override this warning and do it anyway.")
    elif (amount_sats < min_reward_amount):
        raise PacliInputDataError("You are signalling less coins than those necessary for the minimum reward you could get. Transaction aborted.")
    elif (amount_sats < (10 * min_reward_amount)) and (not force):
        raise PacliInputDataError("You are signalling an amount of less than 10 times the minimum reward you could get. If several proposals are approved in the same epoch, you could get no reward. Repeat command using --force to override this warning and use this amount anyway.")

    # WORKAROUND. This should be done with the "legacy" parameter and net_query.

    if Settings.network in ("slm", "tslm"):
        total_tx_fee = 0.03
    elif Settings.network in ("tppc"):
        total_tx_fee = 0.02
    elif Settings.network in ("ppc"):
        total_tx_fee = 0.002

    print("Take into account that releasing the donation requires {} coins for fees.".format(total_tx_fee))
    if (check_round is not None) and (check_round < 4): # TODO this is not good, as it will only appear if check_round is used. Refactor!
        print("Additionally, locking the transaction requires {} coins, so total fees sum up to {}.".format(total_tx_fee, total_tx_fee * 2))

def display_donation_state(dstate: object, mode: str="basic"):

    pprint("ID: {}".format(dstate.id))
    ds_dict = dstate.__dict__

    if mode == "basic":
        for item in ds_dict:
            try:
                value = ds_dict[item].txid
            except AttributeError:
                value = ds_dict[item]
            print(item + ":", value)

    elif mode == "simplified":

        pprint("------------------------------------------------------------")
        print("Proposal: " + dstate.proposal_id)
        print("Round: " + str(dstate.dist_round))
        print("Amount: " + str(dstate.donated_amount))
        print("Donation txid: " + dstate.donation_tx.txid)

    elif mode == "short":

        pprint("Donor address: {}".format(dstate.donor_address))
        pprint("-" * 16)

    else:

        for item in ds_dict:
            if issubclass(type(ds_dict[item]), TrackedTransaction):
                value = ds_dict[item].txid
            else:
                value = ds_dict[item]

            print("{}: {}".format(item, value))

