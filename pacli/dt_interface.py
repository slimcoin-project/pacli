import itertools
from pypeerassets.at.dt_entities import TrackedTransaction
from pypeerassets.at.dt_states import DonationState
from pypeerassets.protocol import Deck

def printout_period(period: tuple, blockheights: list, show_blockheights: bool=False, blockheights_first: bool=False) -> str:
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
    elif period[0] == "D":
        if period[1] % 10 == 0:
             return "{}Period D{}: Final Slot Distribution, round {} Signalling Phase.{}".format(bf, period[1], period[1]//10, bhs)
        else:
             return "{}Period D{}: Final Slot Distribution, round {} Donation Phase.{}".format(bf, period[1], period[1]//10, bhs)
    elif period == ("D", 50):
        return "{}Period E0. Remaining period of Final Phase.{}".format(bf, bhs)
    elif period == ("E", 0):
        return "{}Period E1. All distribution phases concluded.{}".format(bf, bhs)

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


def prepare_dict(d, only_txids=["all_signalling_txes", "all_locking_txes", "all_donation_txes", "all_voting_txes"]):
    # successor to update2levels
    # prepares a dict with 2 levels like ProposalState for prettyprinting.
    for key, value in d.items():
        # first, rule out special cases where we want a simplified display (only the txid)
        if key in only_txids:
           d[key] = [ t.txid for t in value ]
        else:
           d[key] = dictmod_recursive(value)


def prepare_complete_dict(d):
    # version which shows always all items.
    for key, value in d.items():
        d[key] = show_recursive(value)

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


def wait_for_block(startblock, endblock, wait=False):
    # This function enables the "wait" option. It loops each 15 sec until the targe period is correctly reached.
    # It will terminate and launch the transaction creator when the start block has been reached,
    # or exit without launching if the end block has passed.
    # If "wait" is set to False, then if the blockheight is outside the target period, the function exits after one loop.
    startendvalues = "(start: {}, end: {}).".format(startblock, endblock)
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
                print("Current block:", current_block)
                return False
