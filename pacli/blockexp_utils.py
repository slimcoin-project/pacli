import datetime
import pypeerassets as pa
import pacli.extended_utils as eu
import pacli.extended_interface as ei
import pacli.extended_commands as ec
import pacli.blocklocator as loc
from pacli.provider import provider
from pacli.config import Settings

# lower level block exploring utilities are now bundled here

def show_txes_by_block(receiving_address: str=None, sending_address: str=None, locator_list: list=None, deckid: str=None, startblock: int=0, endblock: int=None, quiet: bool=False, coinbase: bool=False, advanced: bool=False, use_locator: bool=False, store_locator: bool=False, only_store: bool=False, debug: bool=False) -> list:

    # TODO: probably this would work better as a generator.
    # NOTE: show_locator_txes was removed, is not used anymore.

    # locator_list parameter only stores the locator
    # locator call: (locator_list=addresses, startblock=start_block, endblock=end_block, quiet=quiet, debug=debug)

    lastblockheight, lastblockhash = None, None

    if locator_list:
        use_locator = True
        store_locator = True

    if (not quiet) and (not use_locator) and ((endblock - startblock) > 10000):
        print("""
              NOTE: This commands cycles through all blocks and will take very long
              to finish. It's recommended to use it for block ranges of less than 10000 blocks.
              Abort and get results with KeyboardInterrupt (e.g. CTRL-C).
              """)

    if deckid:
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        try:
            receiving_address = deck.at_address # was originally tracked_address, but that was probably a bug.
        except AttributeError:
            raise ei.PacliInputDataError("Deck ID {} does not reference an AT deck.".format(deckid))

    tracked_txes = []

    # address_list -> list of all addresses to query. Will be created always, with the exception of the mode showing all transactions.

    if locator_list:
        address_list = locator_list
    elif sending_address or receiving_address:
        # add sending or receiving address or both (None values are ignored)
        address_list = [a for a in [sending_address, receiving_address] if a is not None]
    else:
        address_list = None # this means all transactions will be preselected
        if quiet is False and use_locator is True:
            print("Locator mode not supported if no addresses or decks are selected. Locators will not be used.")
        use_locator = None
        store_locator = None

        #else: # whole wallet mode, not recommended with locators at this time!
        #    address_list = list(eu.get_wallet_address_set())

    blockrange = range(startblock, endblock + 1)

    if store_locator:
        address_blocks = get_address_blockheights(address_list)

    if use_locator:
        loc_blockheights, last_checked_block = get_locator_data(address_list)

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
                if debug:
                    print("Provided start block is above the cached range. Not using nor storing locators to avoid inconsistencies.")
                blockheights = blockrange
                store_locator = False
        else:
            if debug:
                print("Only showing already cached blockheights. No caching will be done.")
            blockheights = [b for b in loc_blockheights if (startblock <= b <= endblock)]
            store_locator = False # makes sense here as there are no new blocks cached.

    else:
        blockheights = blockrange

    if locator_list:
        receiving_address = None # TODO re-check if still necessary. Probably prevented one of the branches of the complex if-else tree before ...

    for bh in blockheights:
        #if bh < startblock:
        #    continue # this can happen when loading locator data
        # Note: loc_blockheights contains data about ALL checked addresses.
        # The following should work anyway, because the blocks not checked will be added to the blocks.
        # if only_store is True and bh in loc_blockheights:
        #    continue

        try:
            if (not quiet) and (bh % 100 == 0) and (use_locator and (bh not in loc_blockheights)):
                print("Processing block:", bh)
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
                    tx_struct = get_tx_structure(txid=txid)
                except Exception as e:
                    if debug:
                        print("TX {} Error: {}".format(txid, e))
                    continue
                #if debug:
                #    # print("TX {} struct: {}".format(txid, tx_struct))
                if not coinbase and len(tx_struct["inputs"]) == 0:
                    continue

                receivers = [r for o in tx_struct["outputs"] for r in o["receivers"]]
                senders = [s for i in tx_struct["inputs"] for s in i["sender"]]

                if address_list:
                    addr_present = not set(address_list).isdisjoint(set(senders + receivers))

                if (not address_list) or addr_present:

                    if advanced:
                        tx_dict = provider.getrawtransaction(txid, 1)
                    else:
                        tx_dict = {"txid" : txid}
                        tx_dict.update(tx_struct)
                        if debug:
                            print("TX detected: {} struct: {}".format(txid, tx_struct))

                    receiver_present = receiving_address in receivers
                    sender_present = sending_address in senders
                    all_txes = (sending_address is None and receiving_address is None)

                    if receiver_present or sender_present or all_txes:
                        tracked_txes.append(tx_dict)

                    if store_locator and bh not in loc_blockheights: ## CHANGED: we now only store if the blocks were not checked before.
                       for a in address_list:
                           if (a in senders) or (a in receivers) and (bh not in address_blocks[a]):
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
    #if store_locator and len(list(blockheights)) > 0:
        # store_locator_data(address_blocks, lastblockheight, lastblockhash, quiet=quiet, debug=debug)
    # return tracked_txes
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


def get_tx_structure(txid: str=None, tx: dict=None, human_readable: bool=True, tracked_address: str=None, add_txid: bool=False) -> dict:
    """Helper function showing useful values which are not part of the transaction,
       like sender(s) and block height."""
    # TODO: could see an usability improvement for coinbase txes.
    # However, this could lead to side effects.

    if not tx:
        if txid:
            tx = provider.getrawtransaction(txid, 1)
        else:
            return None
    try:
        senders = ec.find_tx_senders(tx)
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

    if not senders:
        senders = ["COINBASE"]

    if tracked_address:
        outputs_to_tracked, oindices = [], []
        for oindex, o in enumerate(outputs):
            if (o.get("receivers") is not None and tracked_address in o["receivers"]):
                outputs_to_tracked.append(o)
                oindices.append(oindex)

        if outputs_to_tracked:
            tracked_value = sum([o["value"] for o in outputs_to_tracked])
            sender = senders[0] if len(senders) > 0 else "COINBASE" # fix for coinbase txes
            result = {"sender" : sender, "outputs" : outputs, "height" : height, "oindices": oindices, "ovalue" : tracked_value}
        else:
           return None
    else:
        result = {"inputs" : senders, "outputs" : outputs, "blockheight" : height}

    if add_txid:
        result.update({"txid" : tx["txid"]})

    return result


def get_locator_data(address_list: list, filename: str=None, show_hash: bool=False, debug: bool=False):
    # Note: This command "unifies" the data for several addresses, i.e. it doesn't differentiate per address.

    if not address_list:
        raise ei.PacliInputDataError("If you use the locator feature you have to provide address(es) or deck/tokens.")
    locator = loc.BlockLocator.from_file(locatorfilename=filename)
    raw_blockheights = []
    last_checked_blocks = {}
    for addr in address_list:
        if addr is not None:
            loc_addr = locator.get_address(addr)
            raw_blockheights += loc_addr.heights
            last_checked_blocks.update({loc_addr.lastblockheight : loc_addr.lastblockhash})

    blockheights = list(set(raw_blockheights))
    blockheights.sort()
    last_blockheight = min(last_checked_blocks.keys()) # returns the last commonly checked block for all addresses.

    if show_hash:
        last_blockhash = last_checked_blocks[last_blockheight]
        return (blockheights, last_blockhash)
    else:
        return (blockheights, last_blockheight)


def get_address_blockheights(address_list: list, filename: str=None):
    # this will return blockheights per address, as needed in the address_list.
    locator  = loc.BlockLocator.from_file(locatorfilename=filename)
    block_dict = {}
    for addr in address_list:
        if addr is not None:
            loc_addr = locator.get_address(addr)
            block_dict.update({addr : loc_addr.heights})

    return block_dict

def store_locator_data(address_dict: dict, lastblockheight: int, lastblockhash: str, filename: str=None, quiet: bool=False, debug: bool=False):
    locator = loc.BlockLocator.from_file(locatorfilename=filename)
    for address, values in address_dict.items():
        if address:
            locator.store_blockheights(address, values, lastblockheight, lastblockhash=lastblockhash)
    locator.store(quiet=quiet, debug=debug)

def erase_locator_entries(addresses: list, quiet: bool=False, filename: str=None, debug: bool=False):
    if not quiet:
        print("Deleting block locator entries of addresses:", addresses)
        print("Please type 'yes' to confirm.")
        if not ei.confirm_continuation():
            print("Aborted.")
            return
    locator = loc.BlockLocator.from_file(locatorfilename=filename)
    for address in addresses:
        locator.delete_address(address)
    locator.store(quiet=quiet, debug=debug)
