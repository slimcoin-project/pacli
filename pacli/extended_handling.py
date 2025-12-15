# Tools for unified exception and change handling
import sys
from pypeerassets.exceptions import InsufficientFunds
import pacli.extended_txtools as et
import pacli.extended_interface as ei
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

def run_command(c, *args, **kwargs) -> object:
    # Unified handling for exceptions, change etc..

    debug = ("debug" in kwargs and kwargs["debug"]) or ("show_debug_info" in kwargs and kwargs["show_debug_info"])

    try:
        if "change" in kwargs:
            et.set_change_address(kwargs["change"], debug=debug)
            if debug:
                print("Setting change address to:", Settings.change)

        result = c(*args, **kwargs)
        return result

    except KeyboardInterrupt:
        print("Aborted.")
        sys.exit()

    except PacliMainAddressLocked as e:
        print("Pacli wallet locked. Commands accessing the main address or its keys can't be used.")
        print("Use 'pacli address set LABEL' or 'pacli address set -a ADDRESS' to change to an existing address, 'pacli address set LABEL -f' to a completely new address.")
        print("See available addresses with 'pacli address list'")
        #ei.print_red("\nError: {}".format(e.args[0]))
        # print(e.args[0])
        # if debug:
        #    raise
        sys.exit()

    except (PacliDataError, ValueExistsError, InsufficientFunds) as e:

        ei.print_red("\nError: {}".format(e.args[0]))
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

        ei.print_red(err_str)
        if debug:
            raise

        sys.exit()

def confirm_tx(orig_tx: dict, quiet: bool=False) -> None:

    if not quiet:
        print("Transaction created and broadcasted. Confirmation can take several minutes.")
        print("Waiting for first confirmation (abort waiting safely with KeyboardInterrupt, e.g. CTRL-C, command will continue) ...", end='')
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
                    ei.spinner(10)
        except KeyboardInterrupt:
            print("\nConfirmation check aborted. Check confirmation manually.")
            return

# Exceptions


class PacliDataError(Exception):
    # general data error
    pass

class PacliInputDataError(PacliDataError):
    # exception thrown when there is some conflict between the commands the user enters and the blockchain data.
    # e.g. transaction outside of donation rounds, claim before the donation is confirmed, non-existing deck, etc.
    pass

class ValueExistsError(Exception):
    # exception thrown when a key already exists in the extended config file and protected mode is used.
    pass

class PacliGeneralError(Exception):
    # exception to throw the "General Error" error.
    pass

class PacliMainAddressLocked(Exception):
    # exception if address is set to unusable key.
    pass
