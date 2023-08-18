import itertools, sys
from time import sleep
from pacli.provider import provider

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
    except PacliInputDataError as e:

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
        print("Waiting for confirmation (this can take several minutes) ...", end='')
    confirmations = 0
    while confirmations == 0:
        try:
            tx = provider.getrawtransaction(orig_tx.txid, 1)
        except KeyError:
            raise PacliInputDataError("An unsigned transaction cannot be confirmed. Use --sign and --send to sign and broadcast the transaction.")
        # this happens when the tx is unsigned.
        #tx = provider.getrawtransaction(rawtx.txid, 1)
        try:
            confirmations = tx["confirmations"]
            if not silent:
                print("\nTransaction confirmed.")
            break
        except KeyError:
            if not silent:
                spinner(10)


class PacliInputDataError(Exception):
    # exception thrown when there is some conflict between the commands the user enters and the blockchain data.
    # e.g. transaction outside of donation rounds, claim before the donation is confirmed, non-existing deck, etc.
    pass

