from pacli.extended_utils import PacliInputDataError
from pacli.provider import provider

def output_tx(txdict: dict, txhex: bool=False, confirm: bool=True):

    try:
        if confirm: # without sign, txdict["txid"] doesn't work
            if not txhex:
                print("Waiting for confirmation (this can take several minutes) ...", end='')
            confirmations = 0
            while confirmations == 0:
                try:
                    tx = provider.getrawtransaction(txdict["txid"], 1)
                except KeyError:
                    break # this happens when the tx is unsigned.
                #tx = provider.getrawtransaction(rawtx.txid, 1)
                try:
                    confirmations = tx["confirmations"]
                    print("\nTransaction confirmed.")
                    break
                except KeyError:
                    spinner(10)

        if txhex:
            try:
                return txdict["hex"]
            except KeyError:
                return txdict["raw hex"]
        else:
            return txdict

    except PacliInputDataError as e:
        print_red("Error:", e)

def print_red(text):
    print("\033[91m {}\033[00m" .format(text))

def run_command(command):
    # Unified exception handling for PacliInputDataError.
    try:
        return command
    except PacliInputDataError as e:
        print_red("Error:", e)

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
