import itertools, sys
from time import sleep
import pacli.tui as tui
from pacli.provider import provider
from pacli.config import Settings
from pypeerassets.exceptions import InsufficientFunds

def output_tx(txdict: dict, txhex: bool=False) -> object:

    if txhex:
        try:
            return txdict["hex"]
        except KeyError:
            return txdict["raw hex"]
    else:
        return txdict


def print_red(text: str) -> None:
    print("\033[91m {}\033[00m" .format(text))

def run_command(c, *args, **kwargs) -> object:
    # Unified exception handling for PacliInputDataError and other exceptions.

    #try:
    #    warnings.filterwarnings("ignore")
    #except UnboundLocalError:
    #    import warnings
    #    warnings.filterwarnings("ignore") # NOT working

    debug = ("debug" in kwargs.keys() and kwargs["debug"]) or ("show_debug_info" in kwargs.keys() and kwargs["show_debug_info"])

    try:
        result = c(*args, **kwargs)
        return result

    except (PacliInputDataError, ValueExistsError, InsufficientFunds) as e:

        print_red("\nError: {}".format(e.args[0]))
        if debug:
            raise
        sys.exit()

    except (TypeError, KeyError, PacliGeneralError) as e:

        # a TypeError complaining is often raised if a deck wasn't initialized:
        # TypeError: argument of type 'NoneType' is not iterable
        err_str = """\n        General error raised by PeerAssets. Check if your input is correct."""

        err_str2 = """

        If you gave a deck as an argument, a possible reason for this error is that you need to initialize the deck.

        To initialize the default decks, use:

        pacli deck init

        To initialize a single deck, use:

        pacli deck init DECKID
        """

        if "txid" in e.args or ("deck" in kwargs or "deckid" in kwargs):
            err_str += err_str2

        print_red(err_str)
        if debug:
            raise

        sys.exit()


def spinner(duration: int) -> None:
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


def confirm_tx(orig_tx: dict, quiet: bool=False) -> None:

    if not quiet:
        print("Transaction created and broadcasted. Confirmation can take several minutes.")
        print("Waiting for first confirmation (abort waiting with KeyboardInterrupt, e.g. CTRL-C) ...", end='')
        print("(Note: Transactions should have several dozens of confirmations to be considered final.)")
    confirmations = 0
    while confirmations == 0:
        try:
            try:
                tx = provider.getrawtransaction(orig_tx.txid, 1)
            except KeyError:
                raise PacliInputDataError("An unsigned transaction cannot be confirmed. Use --sign and --send to sign and broadcast the transaction.")

            try:
                confirmations = tx["confirmations"]
                if not quiet:
                    print("\nTransaction confirmed.")
                break
            except KeyError:
                if not quiet:
                    spinner(10)
        except KeyboardInterrupt:
            print("\nConfirmation check aborted. Check confirmation manually.")
            return


def format_balances(balancedict: dict, labeldict: dict, network_name: str=Settings.network, suppress_addresses: bool=False):
    # balancedict contains: { address : balance, ... }, labeldict: { full_label : address }
    balances = {}
    for address, balance in balancedict.items():
        for full_label, labeled_addr in labeldict.items():

            if labeled_addr == address:
                prefix = network_name + "_"
                # workaround for keystore_extended
                # remove key_, but only if it's at the start.
                if full_label[:4] == "key_":
                    full_label = full_label[4:]
                label = full_label.replace(prefix, "")

                if label.startswith("(unlabeled"):
                    label = address
                elif not suppress_addresses:
                    label = "{} ({})".format(label, address)
                # Note: else not necessary, only label will be shown.

                balances.update({label : balance})
                break
        else:
            balances.update({address : balance})
    return balances


def add_token_balances(addresses: list, token_identifier: str, token_balances: dict, network_name: str=Settings.network, suppress_addresses: bool=False) -> None:
    # balancedict contains: { address : balance, ... }, labeldict: { full_label : address }
    # TODO in reality this is not a formatting/interface function anymore, consider adding to another module if the part about address labels is transferred to another function.
    # balances = {}
    for address, balance in token_balances.items():
        # for full_label, labeled_addr in labeldict.items():
        for item in addresses:

            if address == item["address"]:
                if "tokens" not in item:
                    item.update({"tokens" : {token_identifier: balance}})
                else:
                    item["tokens"].update({token_identifier: balance})
                # TODO: this should go into another part, it is not consistent to do that update here.
                if "addr_identifier" not in item:
                    if item["label"] in (None, ""): # a label should still be able to be called "0"
                        addr_id = address
                    elif not suppress_addresses:
                        addr_id = "{} ({})".format(item["label"], address)
                    else:
                        addr_id = item["label"]
                    item.update({"addr_identifier" : addr_id})
                break


def confirm_continuation(text: str=None) -> bool:
    """UX element to confirm continuation entering 'yes'."""

    text = "Enter 'yes' to confirm to continue" if text is None else text
    print(text)
    cont = input()
    if cont == "yes":
        return True
    else:
        return False

# Tables


def deck_line_item(deck: dict, show_initialized: bool=False):

    deck_item = [deck["label"],
            deck["id"],
            deck["name"],
            deck["issuer"],
            deck["issue_mode"],
            deck["tx_confirmations"]]
    if show_initialized:
        deck_item.append(deck["initialized"])
    return deck_item

def print_deck_list(decks: list, show_initialized: bool=False, title: str="Decks:"):
    heading = ["Local label", "ID", "Global name", "Issuer", "M", "Conf."]
    if show_initialized:
        heading.append("I")

    tui.print_table(
    title=title,
    heading=heading,
    #data=map(lambda x: deck_line_item(show_initialized=show_initialized), decks)
    data=[deck_line_item(d, show_initialized=show_initialized) for d in decks])


def address_line_item(address: dict, p2th: bool=False):
    item = [address["label"],
             address["address"],
             address["network"],
             address["balance"]]
    if p2th is True:
        item.append(address["account"])
    return item

def print_address_list(addresses: list, p2th: bool=False):
    addr_heading = ["Label", "Address", "Network", "Coin balance"]
    if p2th is True:
        addr_heading.append("P2TH account")

    tui.print_table(
    title="Addresses:",
    heading=addr_heading,
    #data=map(address_line_item(p2th=p2th), addresses)
    data=[address_line_item(a, p2th=p2th) for a in addresses])

def balances_line_item(address: dict):
    return [address["label"],
             address["address"],
             address["coin"],
             address["pob"],
             address["pod"]]

def balances_line_item_onlytokens(address: dict):
    return [address["label"],
             address["address"],
             address["pob"],
             address["pod"]]

def print_default_balances_list(addresses: list, decks: list, network_name: str, only_tokens: bool=False) -> None:
    addr_balances = []
    if only_tokens:
        currencies = {"pob" : decks[0].id, "pod" : decks[1].id}
    else:
        currencies = {"coin": network_name, "pob" : decks[0].id, "pod" : decks[1].id}

    for item in addresses:
        balance = {}
        balance.update({"label" : item["label"] })
        balance.update({"address" : item["address"] })

        for curr_header, curr_id in currencies.items():

            if "tokens" in item and curr_id in item["tokens"]:
                balance_value = item["tokens"][curr_id]
            elif curr_header == "coin":
                balance_value = item["balance"]
            else:
                balance_value = 0
            balance.update({curr_header : balance_value})

        addr_balances.append(balance)

    if only_tokens:
        table_data = map(balances_line_item_onlytokens, addr_balances)
        table_heading = ("Label", "Address", "PoB tokens", "dPoD tokens")
    else:
        table_data = map(balances_line_item, addr_balances)
        table_heading = ("Label", "Address", network_name, "PoB tokens", "dPoD tokens")

    tui.print_table(
    title="Balances of addresses with labels in wallet:",
    heading=table_heading,
    data=table_data)

def card_line_item_bheights(card: tui.CardTransfer):

    c = card.__dict__
    return [c["txid"],
            c["blocknum"],
            c['cardseq'],
            c["sender"],
            c["receiver"][0],
            tui.exponent_to_amount(c["amount"][0], c["number_of_decimals"]),
            c["type"]
            ]


def print_card_list_bheights(cards: list):

    tui.print_table(
            title="Card transfers of deck {deck}:".format(deck=cards[0].deck_id),
            heading=("txid", "height", "seq", "sender", "receiver", "amount", "type"),
            data=map(card_line_item_bheights, cards))





def add_deck_data(decks: list, deck_label_dict: dict, only_named: bool=False, initialized_decks: list=[], debug: bool=False):
    # prepare deck dictionary for inclusion in the table

    deck_list = []
    for deck in decks:
        #if debug:
        #    print("Checking deck", deck.id)
        try:
            matching_labels = [lb for lb, did in deck_label_dict.items() if did == deck.id]
            if matching_labels:
                # label = matching_labels[0]
                label = "\n".join(matching_labels)
            else:
                if only_named:
                    continue
                label = ""

            deck_dict = deck.__dict__
            if deck.id in [d.id for d in initialized_decks]:
                initialized = "+"
                if debug:
                    print("Deck init status added for", deck.id)
            else:
                initialized = ""

            deck_dict.update({"initialized" : initialized})

            if debug:
                print("Label added for", deck.id)
            deck_dict.update({"label" : label})

            deck_list.append(deck_dict)
        except Exception as e:
            if debug:
                print("Stored deck {} is not a valid PeerAssets deck.".format(deck.id))
                print(e)
            continue
    return deck_list

# Exceptions

class PacliInputDataError(Exception):
    # exception thrown when there is some conflict between the commands the user enters and the blockchain data.
    # e.g. transaction outside of donation rounds, claim before the donation is confirmed, non-existing deck, etc.
    pass

class ValueExistsError(Exception):
    # exception thrown when a key already exists in the extended config file and protected mode is used.
    pass

class PacliGeneralError(Exception):
    # exception to throw the "General Error" error.
    pass
