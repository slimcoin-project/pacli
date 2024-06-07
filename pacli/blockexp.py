import datetime
from decimal import Decimal
from typing import Union
from prettyprinter import cpprint as pprint
import pypeerassets as pa
import pypeerassets.at.constants as c
import pacli.extended_utils as eu
import pacli.extended_interface as ei
import pacli.extended_commands as ec
import pacli.at_utils as au
import pacli.blocklocator as loc
from pacli.provider import provider
from pacli.config import Settings

# block exploring utilities are now bundled here


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

    if tracked_address:
        outputs_to_tracked = [o for o in outputs if (o.get("receivers") is not None and tracked_address in o["receivers"])]
        sender = senders[0] if len(senders) > 0 else "" # fix for coinbase txes
        result = {"sender" : sender, "outputs" : outputs, "height" : height}

    else:
        result = {"inputs" : senders, "outputs" : outputs, "blockheight" : height}

    if add_txid:
        result.update({"txid" : tx["txid"]})

    return result


def show_txes_by_block(receiving_address: str=None, sending_address: str=None, locator_list: list=None, deckid: str=None, startblock: int=0, endblock: int=None, quiet: bool=False, coinbase: bool=False, advanced: bool=False, use_locator: bool=False, store_locator: bool=False, show_locator_txes: bool=False, debug: bool=False) -> list:

    # locator_list parameter only stores the locator

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
        address_list = [a for a in [sending_address, receiving_address] if a is not None]
    else:
        address_list = None # this means all transactions will be preselected

        #else: # whole wallet mode, not recommended with locators at this time!
        #    address_list = list(eu.get_wallet_address_set())

    if use_locator:
        loc_blockheights, last_checked_block = get_locator_data(address_list)
        print("LOC", loc_blockheights)

        if endblock > last_checked_block:
            if startblock <= last_checked_block:
                if debug:
                    if last_checked_block == 0:
                        print("Addresses", address_list, "were not cached. Storing locator data now.")
                    else:
                        print("Endblock {} is higher than the last cached block {}. Storing locator data for blocks after the last checked block.".format(endblock, last_checked_block))
                blockheights = loc_blockheights + list(range(last_checked_block, endblock + 1))
                store_locator = True
            else:
                if debug:
                    print("Provided start block is above the cached range. Not using nor storing locators to avoid inconsistencies.")
                blockheights = range(startblock, endblock + 1)
        else:
            blockheights = [b for b in loc_blockheights if b <= endblock]

    else:
        blockheights = range(startblock, endblock + 1)

    if store_locator:
        address_blocks = {a : [] for a in address_list}

    if locator_list:
        receiving_address = None # TODO re-check if still necessary. Probably prevented one of the branches of the complex if-else tree before ...

    for bh in blockheights:
        if bh < startblock:
            continue # this can happen when loading locator data

        try:
            if not quiet and bh % 100 == 0:
                print("Processing block:", bh)
            blockhash = provider.getblockhash(bh)
            block = provider.getblock(blockhash)

            try:
                block_txes = block["tx"]
            except KeyError:
                print("You have reached the tip of the blockchain.")
                if lastblockheight is None:
                    raise ei.PacliInputDataError("Start block is after the current block height.")
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
                    # print("LOCPRESENT", addr_present, set(address_list))
                # print(recv, send, sending_address, receiving_address)
                # print([o["receivers"] for o in tx_struct["outputs"]])
                if (not address_list) or addr_present:
                    """if ((not show_locator_txes and ((receiver_present and sender_present) or
                    (receiver_present and sending_address is None) or
                    (sender_present and receiving_address is None) or # sender and
                    (sending_address is None and receiving_address is None))) or # all transactions shown
                    (show_locator_txes and (locator_list is not None) and loc_present)
                    ):"""
                    if advanced:
                        tx_dict = provider.getrawtransaction(txid, 1)
                    else:
                        tx_dict = {"txid" : txid}
                        tx_dict.update(tx_struct)
                        if debug:
                            print("TX added: {} struct: {}".format(txid, tx_struct))

                    receiver_present = receiving_address in receivers
                    sender_present = sending_address in senders
                    all_txes = (sending_address is None and receiving_address is None)

                    if receiver_present or sender_present or all_txes:
                        tracked_txes.append(tx_dict)

                    if store_locator:
                       for a in address_list:
                           if (a in senders) or (a in receivers):
                               address_blocks[a].append(bh)

            lastblockhash = blockhash
            lastblockheight = bh

        except KeyboardInterrupt:
            break

    if store_locator and len(list(blockheights)) > 0:
        store_locator_data(address_blocks, lastblockheight, lastblockhash, quiet=quiet, debug=debug)
    return tracked_txes


def show_txes(receiving_address: str=None, sending_address: str=None, deck: str=None, start: Union[int, str]=None, end: Union[int, str]=None, coinbase: bool=False, advanced: bool=False, quiet: bool=False, debug: bool=False, burns: bool=False, use_locator: bool=True) -> None:
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

        if not start:
            start = 0
        if not end:
            end = provider.getblockcount()

        if "-" in str(start):
            ssp = start.split("-")
            start_formatted = ssp[0] + "-" +  ssp[1].zfill(2) + "-" + ssp[2].zfill(2)
            startdate = datetime.date.fromisoformat(start_formatted)
            startblock = date_to_blockheight(startdate, last_block, debug=debug)
        else:
            startblock = int(start)

        if "-" in str(end):
            esp = end.split("-")
            end_formatted = esp[0] + "-" +  esp[1].zfill(2) + "-" + esp[2].zfill(2)
            enddate = datetime.date.fromisoformat(end_formatted)

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

        if endblock < startblock:
            if endblock + 1 == startblock: # this can happen if there are no blocks during at least one day
                if not quiet:
                    print("No blocks were found in the selected timeframe.")
                return []
            else:
                raise ei.PacliInputDataError("End block or date must be after the start block or date.")

        if not quiet:
            print("Starting at block:", startblock)
            print("Ending at block:", endblock)

    except (IndexError, ValueError):
        raise ei.PacliInputDataError("At least one of the dates you entered is invalid.")


    deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, quiet=quiet) if deck else None
    txes = ei.run_command(show_txes_by_block, receiving_address=receiving_address, sending_address=sending_address, advanced=advanced, deckid=deckid, startblock=startblock, endblock=endblock, coinbase=coinbase, quiet=quiet, debug=debug, use_locator=use_locator, show_locator_txes=use_locator)

    if (not quiet) and (len(txes) == 0):
        print("No transactions found.")
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

def store_locator_data(address_dict: dict, lastblockheight: int, lastblockhash: str, filename: str=None, quiet: bool=False, debug: bool=False):
    locator = loc.BlockLocator.from_file(locatorfilename=filename)
    for address, values in address_dict.items():
        if address:
            locator.store_blockheights(address, values, lastblockheight, lastblockhash=lastblockhash)
    locator.store(quiet=quiet, debug=debug)


def store_deck_blockheights(decks: list, full: bool=False, quiet: bool=False, debug: bool=False, blocks: int=50000):

    if not quiet:
        print("Storing blockheight locators for decks:", [d.id for d in decks])
    # current_block = provider.getblockcount()
    # confirmations = [d.tx_confirmations for d in decks]
    # min_spawn_blockheight = current_block - max(confirmations) - 10 # 10 blocks before first confirmation of a deck spawn
    spawn_blockheights = []
    for d in decks:
        deck_tx = provider.getrawtransaction(d.id, 1)
        try:
            spawn_blockheights.append(provider.getblock(deck_tx["blockhash"])["height"])
        except KeyError:
            continue

    min_spawn_blockheight = min(spawn_blockheights)

    if not quiet:
        print("First deck spawn approximately at block height:", min_spawn_blockheight)

    addresses = []
    for deck in decks:
        addresses += eu.get_deck_p2th_addresses(deck, debug=debug)

    #if not without_burn_address: # probably unnecessary
    #   addresses.append(au.burn_address())

    if debug:
        print("Addresses to store", addresses)
    blockheights, lastblock = get_locator_data(addresses)
    if debug:
        print("Locator data:", blockheights, lastblock)
    if lastblock == 0: # new decks
        start_block = min_spawn_blockheight
    else:
        start_block = lastblock

    if full is True:
        end_block = provider.getblockcount()
        if not quiet:
            print("Full blockchain scan selected. WARNING: This can take several days!")
            print("You can interrupt the scan at any time with KeyboardInterrupt (e.g. CTRL-C) and continue later, calling the same command.")
    else:
        end_block = start_block + blocks
    if not quiet:
        print("Start block: {} End block: {} Number of blocks: {}".format(start_block, end_block, blocks))
    txes = show_txes_by_block(locator_list=addresses, startblock=start_block, endblock=end_block, quiet=quiet, show_locator_txes=True, debug=debug)
    if not quiet:
        print(len(txes), "matching transactions found in the scanned blocks.") # this is not important here, we'd need the new blockheights


def store_address_blockheights(addresses: list, start_block: int=0, blocks: int=50000, quiet: bool=False, debug: bool=False):
    # addresses need to be scanned from 0, as we don't know when they were created
    # An exception could be made for addresses in the wallet.
    if not quiet:
        print("Storing blockheight locators for addresses:", addresses)
    blockheights, lastblock = get_locator_data(addresses)
    if debug:
        print("Locator data (heights, last block):", blockheights, lastblock)
    if not start_block:
        start_block = lastblock
    elif lastblock > 0:
        print("There was a previous caching process, continuing it.")
        print("To cache other block heights, first erase the affected addresses with 'address cache -e'.")
        start_block = lastblock
    else:
        if start_block > (lastblock + 1):
            if not quiet:
                print("WARNING: Block heights between {} and {} not checked.".format(lastblock, start_block))
                if not ei.confirm_continuation():
                    print("Aborted.")
                    return
    end_block = start_block + blocks

    txes = show_txes_by_block(locator_list=addresses, startblock=start_block, endblock=end_block, quiet=quiet, show_locator_txes=True, debug=debug)
    if not quiet:
        print(len(txes), "matching transactions found in the scanned blocks.") # this is not important here, we'd need the new blockheights

def erase_blocklocator_entries(addresses: list, quiet: bool=False, filename: str=None, debug: bool=False):
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

def get_tx_blockheight(txid: str): # TODO look if this is a duplicate.
    tx = provider.getrawtransaction(txid, 1)
    if "blockhash" in tx.keys():
        return provider.getblock(tx["blockhash"])["height"]
    else:
        return None

def integrity_test(address_list: list, rpc_txes: list, lastblockheight: int=None, debug: bool=False):

    # If no lastblockheight is given, it uses the last already checked block.
    if lastblockheight is None:
        lastblockheight = get_locator_data(address_list)[1]

    print("Last blockheight checked", lastblockheight)

    # source 1: blockchain
    if debug:
        print("Blockchain test:")
    blockchain_txes = show_txes_by_block(locator_list=address_list, endblock=lastblockheight, show_locator_txes=True, debug=debug)
    blockchain_balances = get_balances_from_structs(address_list, blockchain_txes, debug=debug)
    # source 2: RPC listtransactions
    if debug:
        print("Wallet transaction test:")
    rpc_txes_struct = [get_tx_structure(tx=tx, human_readable=False, add_txid=True) for tx in rpc_txes]
    rpc_balances = get_balances_from_structs(address_list, rpc_txes_struct, endblock=lastblockheight, debug=debug)

    for address in address_list:
        print("Testing address:", address)
        # source 3: UTXOS (listunspent)
        unspent = provider.listunspent(address=address, minconf=1)
        # print(unspent)
        uvalues = [Decimal(v["amount"]) for v in unspent]
        utxids = [v["txid"] for v in unspent]
        uheights = [get_tx_blockheight(t) for t in utxids]
        if len(uheights) == 0:
            print("Currently no UTXOS found for this address. UTXO test not possible.")
            balance = None
        elif max(uheights) > lastblockheight:
            print("UTXO check not possible, as balances changed after the given blockheight {}.".format(lastblockheight))
            balance = None
        else:
            balance = sum(uvalues)
            print("Balance according to unspent outputs on this address:", balance)

        print("Balances according to wallet transactions (listtransactions RPC command):", rpc_balances[address])
        print("Balances according to blockchain data:", blockchain_balances[address])

        if ((balance is not None) and (blockchain_balances[address]["balance"] == rpc_balances[address]["balance"] == balance)):
            print("PASSED (complete)")
        elif blockchain_balances[address]["balance"] == rpc_balances[address]["balance"]:
            print("PASSED (partly)")
            print("Blockchain data and wallet transaction data match.")
            print("Unspent outputs either not possible to test or not matching.")
            if balance is not None:
                print("Transactions missing in the unspent outputs:")
                btxes = set([b["txid"] for b in blockchain_txes])
                print(btxes - set(utxids))
        else:
            ei.print_red("NOT PASSED")
            rtxes = set([r["txid"] for r in rpc_txes_struct])
            btxes = set([b["txid"] for b in blockchain_txes])
            print("Transactions missing in the RPC view (listtransactions command):")
            print(btxes - rtxes)
            print("Try to rescan the blockchain and then restart the client. If this doesn't change, your wallet file may be corrupted.")
            print("Transactions missing in the unspent outputs:")
            print(btxes - set(utxids))


def get_tx_address_balance(address: str, tx: dict):
    # this takes TX Structure as a dict!
    # print("TX", tx)
    balance = 0
    observed = False
    for i in tx["inputs"]:
        if i["sender"] == address:
            balance -= Decimal(str(i["value"]))
    for o in tx["outputs"]:
        if address in o["receivers"]:
            if len(set(o["receivers"])) == 1:
                balance += Decimal(str(o["value"]))
            else:
                observed = True

    return (balance, observed)

def show_locators(value: str, quiet: bool=False, debug: bool=False):
    # first we look if it's a deck
    try:
        deckid = eu.search_for_stored_tx_label("deck", value, quiet=True)
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        addresses = eu.get_deck_p2th_addresses(deck, debug=debug)
        checktype = "token"
    except ei.PacliInputDataError:
        try:
            addresses = [ec.process_address(value)]
            checktype = "address"
        except:
            raise ei.PacliInputDataError("You need to enter a valid address or token (deck).")

    locators, last_checked_block = get_locator_data(address_list=addresses, debug=debug, show_hash=True)
    last_blockheight = provider.getblock(last_checked_block).get("height")

    result = {"blockheights" : locators,
             "lastblockhash" : last_checked_block,
             "lastblockheight" : last_blockheight}
    readable = {"blockheights" : "Block heights",
                "lastblockhash" : "Last checked block (hash)",
                "lastblockheight" : "Last checked block (height)"}
    if quiet:
        print(result)
    else:
        pprint("Result for {} {}:".format(checktype, value))
        for k, v in result.items():
            print("{}: {}".format(readable[k], v))


def get_balances_from_structs(address_list: list, txes: list, endblock: int=None, debug: bool=False):
    balances = {}
    for address in address_list:
        balances.update({address : {"balance" : Decimal(0), "observed" : False}})
        for tx in txes:
            if endblock is not None and tx["blockheight"] > endblock:
                continue
            tx_balance, observed = get_tx_address_balance(address, tx)
            if observed:
                balances[address]["observed"] = True
            balances[address]["balance"] += tx_balance
            if debug:
                print("TX {} adding balance: {}".format(tx["txid"], tx_balance))
    return balances
