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


def show_txes_by_block(receiving_address: str=None, sending_address: str=None, deckid: str=None, endblock: int=None, startblock: int=0, silent: bool=False, coinbase: bool=False, advanced: bool=False, debug: bool=False) -> list:

    if not endblock:
        endblock = provider.getblockcount()
    if (not silent) and ((endblock - startblock) > 10000):
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
            if not silent and bh % 100 == 0:
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


def show_txes(receiving_address: str=None, sending_address: str=None, deck: str=None, start: int=0, end: int=None, coinbase: bool=False, advanced: bool=False, silent: bool=False, debug: bool=False, burns: bool=False) -> None:
    '''Show all transactions to a tracked address between two block heights (very slow!).'''

    if burns:
         if not silent:
             print("Using burn address.")
         receiving_address = au.burn_address()

    deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, silent=silent) if deck else None
    txes = ei.run_command(show_txes_by_block, receiving_address=receiving_address, sending_address=sending_address, advanced=advanced, deckid=deckid, startblock=start, endblock=end, coinbase=coinbase, silent=silent, debug=debug)

    return txes

