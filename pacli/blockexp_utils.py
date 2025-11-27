import datetime
import pypeerassets as pa
import pacli.extended_utils as eu
import pacli.extended_interface as ei
import pacli.blocklocator as loc
from pacli.provider import provider
from pacli.config import Settings

# lower level block exploring utilities are now bundled here

def show_txes_by_block(sending_addresses: list=[],
                       receiving_addresses: list=[],
                       locator_list: list=None,
                       startblock: int=0,
                       endblock: int=None,
                       locator: loc.BlockLocator=None,
                       quiet: bool=False,
                       coinbase: bool=False,
                       advanced: bool=False,
                       advanced_struct: bool=False,
                       require_sender_and_receiver: bool=False,
                       force_storing: bool=False,
                       use_locator: bool=False,
                       store_locator: bool=False,
                       only_store: bool=False,
                       debug: bool=False) -> list:
    """Shows or stores transaction data from the blocks directly."""
    #TODO: specifying a burn address does not restrict the txes to burn transactions.
    # Maybe sending and receiving TXes are connected by OR instead of AND?
    # (i.e. if both are specified, both sending and receiving txes are shown?)

    # NOTE: locator_list parameter only stores the locator

    lastblockheight, lastblockhash = None, None
    all_txes = False

    if locator_list:
        use_locator = True
        store_locator = True

    if (not quiet) and (not use_locator) and ((endblock - startblock) > 10000):
        print("""
              NOTE: This commands cycles through all blocks and will take very long
              to finish. It's recommended to use it for block ranges of less than 10000 blocks.
              Abort and get results with KeyboardInterrupt (e.g. CTRL-C).
              """)

    tracked_txes = []

    if sending_addresses or receiving_addresses:
        address_list = list(set(sending_addresses + receiving_addresses)) # removes overlapping addresses
    elif locator_list:
        address_list = locator_list
    else:
        address_list = None # this means all transactions will be preselected
        if quiet is False and use_locator is True:
            print("Locator mode not supported if no addresses or decks are selected. Locators will not be used.")
        use_locator = False
        store_locator = False
        all_txes = True

    blockrange = range(startblock, endblock + 1)

    if store_locator:
        address_blocks = get_address_blockheights(address_list, locator=locator)

    if use_locator:
        if locator is None:
            locator = get_default_locator()
        loc_blockheights, last_checked_block = locator.get_address_data(address_list, debug=debug)

        if endblock > last_checked_block:

            if startblock <= last_checked_block:
                if debug:
                    if last_checked_block == 0:
                        print("Addresses", address_list, "were not cached. Storing locator data now.")
                    else:
                        print("Endblock {} is higher than the last cached block {}. Storing locator data for blocks after the last checked block.".format(endblock, last_checked_block))

                if only_store:
                    blockheights = blockrange
                else:
                    blockheights = [b for b in loc_blockheights if b >= startblock] + [b for b in blockrange if b > last_checked_block]

            else:
                blockheights = blockrange
                # if it's the first caching process, store anyway.
                if last_checked_block > 0 and not force_storing:
                    if not quiet:
                        print("The start block you provided is above the cached range. Not storing locators to avoid inconsistencies.")
                    store_locator = False


        else:
            if debug:
                print("Only showing already cached blockheights. No caching will be done.")
            blockheights = [b for b in loc_blockheights if (startblock <= b <= endblock)]
            store_locator = False # makes sense here as there are no new blocks cached.

    else:
        blockheights = blockrange

    if not quiet and blockheights: # basic parameters for progress message
        min_height = min(blockheights)
        max_height = max(blockheights)
        checked_range = max_height - min_height
        percent = round(checked_range / 100, 2)
        mbd = 50 # minimum block distance
        last_cycle = 0

    for bh in blockheights:
        try:
            # progress message
            if not quiet and (not use_locator or (bh not in loc_blockheights)):
                rh = bh - min_height # relative height: current height minus minimum height
                if (bh == min_height) or (use_locator and (len(loc_blockheights) > 0 and bh == (max(loc_blockheights) + 1))):
                    if use_locator:
                        print("Processing uncached blocks starting from block {} ...".format(bh))
                    else:
                        print("Processing blocks starting from block {} ...".format(bh))

                elif (bh == max_height) or (int(rh % percent) == 0): # each time a full percentage is recorded
                    percentage = round(rh / percent)
                    if (bh == max_height) or ((rh - last_cycle) >= mbd and (percentage not in (0, 100))):
                        last_cycle = (rh // mbd) * mbd
                        print("Progress: {} %, block: {} ...".format(percentage, bh))

            blockhash = provider.getblockhash(bh)
            block = provider.getblock(blockhash)

            try:
                block_txes = block["tx"]
            except KeyError:
                if not quiet:
                    print("You have reached the tip of the blockchain.")
                if lastblockheight is None:
                    raise ei.PacliInputDataError("Start block is after the current block height.\nIf you didn't specify a start block, this probably means there are no new blocks to cache.")
                else:
                    break

            for txid in block_txes:
                try:
                    txjson = provider.getrawtransaction(txid, 1)
                    # tx_struct = get_tx_structure(txid=txid)
                    tx_struct = get_tx_structure(tx=txjson)
                except Exception as e:
                    if debug:
                        print("TX {} Error: {}".format(txid, e))
                    continue
                #if debug: # enable for deep debugging
                #    print("TX {} struct: {}".format(txid, tx_struct))
                if not coinbase and len(tx_struct["inputs"]) == 0:
                    continue

                sender_present, receiver_present = None, None
                receivers = [r for o in tx_struct["outputs"] for r in o["receivers"]]
                senders = [s for i in tx_struct["inputs"] for s in i["sender"]]

                if locator_list:
                    addr_present = not set(address_list).isdisjoint(set(senders + receivers))
                elif sending_addresses or receiving_addresses: # list mode is probably slower
                    receiver_present = not set(receiving_addresses).isdisjoint(set(receivers))
                    sender_present = not set(sending_addresses).isdisjoint(set(senders))
                    if require_sender_and_receiver:
                        addr_present = sender_present and receiver_present
                    else:
                        addr_present = sender_present or receiver_present # TODO perhaps this line is the problem: it does an OR between senders and receivers.

                if all_txes or addr_present:
                    if advanced:
                        # tx_dict = provider.getrawtransaction(txid, 1)
                        tx_dict = txjson
                    else:
                        tx_dict = {"txid" : txid}
                        tx_dict.update(tx_struct)
                        if advanced_struct:
                            tx_dict.update({"txjson" : txjson})
                        if debug:
                            print("TX detected: {} struct: {}".format(txid, tx_struct))

                    if all_txes or receiver_present or sender_present:
                        tracked_txes.append(tx_dict)

                    # skip blocks which were already stored in the block locators
                    if store_locator and bh not in loc_blockheights:
                       for a in address_list:
                           if ((a in senders) or (a in receivers)) and (bh not in address_blocks[a]):
                               address_blocks[a].append(bh)

            lastblockhash = blockhash
            lastblockheight = bh

        except KeyboardInterrupt:
            if use_locator and bh in loc_blockheights:
                raise ei.PacliInputDataError("Interrupted while initializing blockheights. No block processing was done, so nothing is shown nor stored.")
            else:
                break

    result = {}
    if store_locator is True:
        result.update({"blocks" : address_blocks, "bhash" : lastblockhash, "bheight" : lastblockheight})
    if not only_store:
        result.update({"txes" : tracked_txes})
    return result


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

def get_tx_structure(txid: str=None, tx: dict=None, human_readable: bool=True, add_txid: bool=False, ignore_blockhash: bool=False) -> dict:
    """Helper function showing useful values which are not part of the transaction,
       like sender(s) and block height."""

    if not tx:
        if txid:
            tx = provider.getrawtransaction(txid, 1)
        else:
            return None
    try:
        senders = find_tx_senders(tx)
    except KeyError:
        raise ei.PacliInputDataError("Transaction does not exist or is corrupted.")

    outputs = []
    if "blockhash" in tx and not ignore_blockhash:
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
        receivers = get_utxo_addresses(output)
        outputs.append({"receivers" : receivers, "value" : value})

    if not senders:
        senders = [{"sender" : ["COINBASE"]}]

    #if tracked_address: # TODO: Should be a separate function. This also complicates the use_db option. # TODO where was that one outsourced?
    #    outputs_to_tracked, oindices = [], []
    #    for oindex, o in enumerate(outputs):
    #        if (o.get("receivers") is not None and tracked_address in o["receivers"]):
    #            outputs_to_tracked.append(o)
    #            oindices.append(oindex)

    #    if outputs_to_tracked:
    #        tracked_value = sum([o["value"] for o in outputs_to_tracked])
    #        sender = senders[0] if len(senders) > 0 else "COINBASE" # fix for coinbase txes
    #        result = {"sender" : sender, "outputs" : outputs, "blockheight" : height, "oindices": oindices, "ovalue" : tracked_value}
    #    else:
    #       return None
    # else:
    if ignore_blockhash:
        result = {"inputs" : senders, "outputs" : outputs}
    else:
        result = {"inputs" : senders, "outputs" : outputs, "blockheight" : height}

    if add_txid:
        result.update({"txid" : tx["txid"]})

    return result


def get_default_locator(ignore_orphans: bool=False):
    return loc.BlockLocator.from_file(ignore_orphans=ignore_orphans)

def get_address_blockheights(address_list: list, filename: str=None, locator: loc.BlockLocator=None):
    # this will return blockheights per address, as needed in the address_list.
    if locator is None:
        locator  = loc.BlockLocator.from_file(locatorfilename=filename)
    block_dict = {}
    for addr in address_list:
        if addr is not None:
            loc_addr = locator.get_address(addr)
            block_dict.update({addr : loc_addr.heights})

    return block_dict

def store_locator_data(address_dict: dict, lastblockheight: int, lastblockhash: str, locator: loc.BlockLocator, startheight: int=0, filename: str=None, quiet: bool=False, debug: bool=False):

    for address, values in address_dict.items():
        if address:
            locator.store_blockheights(address, values, lastblockheight, lastblockhash=lastblockhash, startheight=startheight, quiet=quiet, debug=debug)
    locator.store(quiet=quiet, debug=debug)

def erase_locator_entries(addresses: list, quiet: bool=False, filename: str=None, force: bool=False, debug: bool=False) -> None:
    if not quiet:
        print("Deleting block locator entries of addresses:", addresses)
        if not force:
            print("This is a dry run. Use --force to really erase the entry of this address.")

    locator = loc.BlockLocator.from_file(locatorfilename=filename)
    for address in addresses:
        locator.delete_address(address)
    if force:
        locator.store(quiet=quiet, debug=debug)

def prune_orphans_from_locator(cutoff_height: int, quiet: bool=False, debug: bool=False) -> None:
    locator = loc.BlockLocator.from_file(ignore_orphans=True)
    orphans = locator.prune_orphans(cutoff_height, quiet=quiet, debug=debug)
    if orphans > 0:
        locator.store(quiet=quiet, debug=debug)

def autoprune_orphans_from_locator(force: bool=False, quiet: bool=False, debug: bool=False) -> None:
    if not force:
        print("This is a dry run. Use --force to really prune the orphan block heights.")
    locator = loc.BlockLocator.from_file(ignore_orphans=True)
    last_canonical_lastblockheight = sorted([a.lastblockheight for a in locator.addresses.values() if a.lastblockheight is not None], reverse=True)[0]
    if not quiet:
        print("Last processed blockheight with correct hash:", last_canonical_lastblockheight)
    orphans = locator.prune_orphans(last_canonical_lastblockheight, debug=debug)
    if force and orphans > 0:
        locator.store(quiet=quiet, debug=debug)


def display_caching_warnings(address_list: list, locator: loc.BlockLocator, ignore_startblocks: bool=False) -> None:

    discontinuous_list = [a for a in address_list if a in locator.addresses and locator.addresses[a].discontinuous is True]
    startblock_list = [a for a in address_list if a in locator.addresses and locator.addresses[a].startheight] if not ignore_startblocks else []
    if discontinuous_list:
        if len(discontinuous_list) == 1:
            print("WARNING: Address {} was not cached continuously.".format(discontinuous_list[0]))
        else:
            print("WARNING: The following addresses were not cached continuously:", discontinuous_list)
    if startblock_list:
        for a in startblock_list:
            print("Note: Address {} was or will be cached from the block height {} on.".format(a, locator.addresses[a].startheight))


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


def get_utxo_from_data(utxo: object, tx: dict=None, debug: bool=False):

    if type(utxo) == str:
        try:
            utxo_data_raw = utxo.split(":")
            utxo_data = (utxo_data_raw[0], int(utxo_data_raw[1]))
        except Exception as e:
            raise ei.PacliInputDataError("Wrong format of the entered UTXO. Please provide it in the format TXID:OUTPUT.", e)
    elif type(utxo) in (list, tuple):
        utxo_data = utxo
    try:
        if tx is None:
            tx = provider.getrawtransaction(utxo_data[0], 1)
        output = tx["vout"][utxo_data[1]]
    except (KeyError, IndexError):
        raise ei.PacliDataError("Unknown address or non-existent output.")
    return output

def get_utxo_addresses(output: dict):
    try:
        receivers = output["scriptPubKey"]["addresses"]
    except KeyError:
        receivers = []
    return receivers

def utxo_in_tx(utxo: tuple, tx: dict):
    txid, vout = utxo[:]
    for inp in tx["vin"]:
        try:
            assert inp["vout"] == vout
            assert inp["txid"] == txid
            return True
        except (AssertionError, KeyError):
            continue
    return False

