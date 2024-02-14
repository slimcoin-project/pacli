import datetime
from typing import Union
import pypeerassets as pa
import pacli.extended_utils as eu
import pacli.extended_interface as ei
import pacli.at_utils as au

from pacli.provider import provider
from pacli.config import Settings

# block exploring utilities are now bundled here


def get_tx_structure(txid: str, human_readable: bool=True, tracked_address: str=None) -> dict:
    """Helper function showing useful values which are not part of the transaction,
       like sender(s) and block height."""
    # TODO: could see an usability improvement for coinbase txes.
    # However, this could lead to side effects.

    tx = provider.getrawtransaction(txid, 1)
    try:
        senders = find_tx_senders(tx)
    except KeyError:
        raise ei.PacliInputDataError("Transaction does not exist or is corrupted.")

    outputs = []
    if "blockhash" in tx:
        height = provider.getblock(tx["blockhash"])["height"]
    elif human_readable:
        height = "unconfirmed"
    else:
        height = None
    value, receivers = None, None
    for output in tx["vout"]:
        try:
            value = output["value"]
        except KeyError:
            value = 0
        try:
            receivers = output["scriptPubKey"]["addresses"]
        except KeyError:
            receivers = []
        outputs.append({"receivers" : receivers, "value" : value})

    if tracked_address:
        outputs_to_tracked = [o for o in outputs if (o.get("receivers") is not None and tracked_address in o["receivers"])]
        sender = senders[0] if len(senders) > 0 else "" # fix for coinbase txes
        return {"sender" : sender, "outputs" : outputs, "height" : height}

    else:
        return {"inputs" : senders, "outputs" : outputs, "blockheight" : height}


def show_txes_by_block(receiving_address: str=None, sending_address: str=None, deckid: str=None, startblock: int=0, endblock: int=None, quiet: bool=False, coinbase: bool=False, advanced: bool=False, debug: bool=False) -> list:

    #if not endblock:
    #    endblock = provider.getblockcount() # goes to show_txes
    if (not quiet) and ((endblock - startblock) > 10000):
        print("""
              NOTE: This commands cycles through all blocks and will take very long
              to finish. It's recommended to use it for block ranges of less than 10000 blocks.
              Abort and get results with CTRL-C.
              """)

    if deckid:
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        try:
            tracked_address = deck.at_address
        except AttributeError:
            raise ei.PacliInputDataError("Deck ID {} does not reference an AT deck.".format(deckid))

    tracked_txes = []
    # all_txes = True if tracked_address is None else False

    for bh in range(startblock, endblock + 1):
        try:
            if not quiet and bh % 100 == 0:
                print("Processing block:", bh)
            blockhash = provider.getblockhash(bh)
            block = provider.getblock(blockhash)

            try:
                block_txes = block["tx"]
            except KeyError:
                print("You have reached the tip of the blockchain.")
                return tracked_txes

            for txid in block_txes:
                if debug:
                    print("Checking TX:", txid)
                try:
                    tx_struct = get_tx_structure(txid)
                except Exception as e:
                    if debug:
                        print("Error", e)
                    continue
                if debug:
                    print("TX layout:", tx_struct)
                if not coinbase and len(tx_struct["inputs"]) == 0:
                    continue
                recv = receiving_address in [r for o in tx_struct["outputs"] for r in o["receivers"]]
                send = sending_address in [s for i in tx_struct["inputs"] for s in i["sender"]]
                # print(recv, send, sending_address, receiving_address)
                # print([o["receivers"] for o in tx_struct["outputs"]])
                if (recv and send) or (recv and sending_address is None) or (send and receiving_address is None) or (sending_address is None and receiving_address is None):
                    if advanced:
                        tx_dict = provider.getrawtransaction(txid, 1)
                    else:
                        tx_dict = {"txid" : txid}
                        tx_dict.update(tx_struct)
                    tracked_txes.append(tx_dict)

        except KeyboardInterrupt:
            break

    return tracked_txes


def find_tx_senders(tx: dict) -> list:
    """Finds all known senders of a transaction."""
    # find_tx_sender from pypeerassets only finds the first sender.
    # this variant returns a list of all input senders.

    senders = []
    for vin in tx["vin"]:
        try:
            sending_tx = provider.getrawtransaction(vin["txid"], 1)
            vout = vin["vout"]
            sender = sending_tx["vout"][vout]["scriptPubKey"]["addresses"]
            value = sending_tx["vout"][vout]["value"]
            senders.append({"sender" : sender, "value" : value})
        except KeyError: # coinbase transactions
            continue
    return senders


def show_txes(receiving_address: str=None, sending_address: str=None, deck: str=None, start: Union[int, str]=0, end: Union[int, str]=None, coinbase: bool=False, advanced: bool=False, quiet: bool=False, debug: bool=False, burns: bool=False) -> None:
    '''Show all transactions to a tracked address between two block heights (very slow!).
       start and end can be blockheights or dates in the format YYYY-MM-DD.'''

    if burns:
         if not quiet:
             print("Using burn address.")
         receiving_address = au.burn_address()
    try:
        last_block = provider.getblockcount()
        last_blocktime = provider.getblock(provider.getblockhash(last_block))["time"]
        last_block_date = datetime.date.fromisoformat(last_blocktime.split(" ")[0])
        startdate, enddate = None, None

        if "-" in str(start):
            startdate = datetime.date.fromisoformat(start)
            startblock = date_to_blockheight(startdate, last_block, debug=debug)
        else:
            startblock = int(start)

        if not end:
            end = provider.getblockcount()

        if "-" in str(end):
            enddate = datetime.date.fromisoformat(end)

            if enddate == last_block_date:
                endblock = last_block
            else:
                # The date_to_blockheight function always returns the first block after the given date
                # so the end block has to be one day later, minus 1 block
                oneday = datetime.timedelta(days=1)
                endblock = date_to_blockheight(enddate + oneday, last_block, startheight=startblock, debug=debug) - 1
        else:
            endblock = int(end)

        if (startdate is not None and startdate > last_block_date) or (enddate is not None and enddate > last_block_date):
            raise ei.PacliInputDataError("Start or end date is in the future.")

        if not quiet:
            print("Ending at block:", endblock)
            print("Starting at block:", startblock)
        if endblock < startblock:
            raise ei.PacliInputDataError("End block or date must be after the start block or date.")
    except (IndexError, ValueError):
        raise ei.PacliInputDataError("At least one of the dates you entered is invalid.")


    deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, quiet=quiet) if deck else None
    txes = ei.run_command(show_txes_by_block, receiving_address=receiving_address, sending_address=sending_address, advanced=advanced, deckid=deckid, startblock=startblock, endblock=endblock, coinbase=coinbase, quiet=quiet, debug=debug)

    return txes


def date_to_blockheight(date: datetime.date, last_block: int, startheight: int=0, debug: bool=False):
    """Returns the first block created after 00:00 UTC the given date.
       This means the block can also be created at a later date (e.g. in testnets with irregular block creation)."""
    # block time format: 2022-04-26 20:31:22 UTC
    blockheight = startheight

    for step in 1000000, 100000, 10000, 1000, 100, 10, 1:
        if step > last_block:
            continue
        for bh in range(blockheight, last_block, step):
            blocktime = provider.getblock(provider.getblockhash(bh))["time"]
            block_date = datetime.date.fromisoformat(blocktime.split(" ")[0])
            if debug:
                print("Checking height", bh)

            if block_date >= date:
                blockheight = bh - step + (step // 10)
                break
        # we also need to reset block height when the loop ends
        else:
            blockheight = bh - step + (step // 10)

        if step == 1 and block_date >= date:
            if debug:
                print("Best block found", bh, blocktime, date)
            break

    return bh

