import itertools, sys
from time import sleep
import pacli.tui as tui
from pacli.provider import provider
from pacli.config import Settings

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
    # Unified exception handling for PacliInputDataError.
    try:
        result = c(*args, **kwargs)
        return result
    except (PacliInputDataError, ValueExistsError) as e:

        print_red("\nError: {}".format(e.args[0]))
        if "debug" in kwargs.keys() and kwargs["debug"]:
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


def confirm_tx(orig_tx: dict, silent: bool=False) -> None:

    if not silent:
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
                if not silent:
                    print("\nTransaction confirmed.")
                break
            except KeyError:
                if not silent:
                    spinner(10)
        except KeyboardInterrupt:
            print("\nConfirmation check aborted. Check confirmation manually.")
            return


def format_balances(balancedict, labeldict: dict, network_name: str=Settings.network, suppress_addresses: bool=False):
    # balancedict contains: { address : balance, ... }
    balances = {}
    for address, balance in balancedict.items():
        for full_label, labeled_addr in labeldict.items():

            if labeled_addr == address:
                prefix = network_name + "_"
                # workaround until keystore_extended is finally removed
                # remove key_, but only if it's at the start.
                if full_label[:4] == "key_":
                    full_label = full_label[4:]
                label = full_label.replace(prefix, "")
                if not suppress_addresses:
                    label = "{} ({})".format(label, address)
                balances.update({label : balance})
                break
        else:
            balances.update({address : balance})
    return balances

def address_line_item(address: dict):
     return [address["label"],
             address["address"],
             address["network"],
             address["balance"]]

def print_address_list(addresses: list):
      tui.print_table(
      title="Addresses with labels in wallet:",
      heading=("Label", "address", "network", "coin balance"),
      data=map(address_line_item, addresses))

# Exceptions

class PacliInputDataError(Exception):
    # exception thrown when there is some conflict between the commands the user enters and the blockchain data.
    # e.g. transaction outside of donation rounds, claim before the donation is confirmed, non-existing deck, etc.
    pass

class ValueExistsError(Exception):
    # exception thrown when a key already exists in the extended config file and protected mode is used.
    pass
