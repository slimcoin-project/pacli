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
from pacli.provider import provider
from pacli.config import Settings
from pacli.blockexp_utils import show_txes_by_block, date_to_blockheight, get_tx_structure, get_locator_data, store_locator_data, erase_locator_entries

# higher level block exploring utilities are now bundled here

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

    except (IndexError, ValueError):
        raise ei.PacliInputDataError("At least one of the dates you entered is invalid.")


    deckid = eu.search_for_stored_tx_label("deck", deck, quiet=quiet) if deck else None

    if deckid:
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        try:
            receiving_address = deck.at_address # was originally tracked_address, but that was probably a bug.
            if "startblock" in deck.__dict__:
                startblock = deck.startblock if startblock in (0, None) else min(deck.startblock, startblock)

            if "endblock" in deck.__dict__:
                endblock = deck.endblock if endblock is None else min(deck.endblock, endblock)
        except AttributeError:
            raise ei.PacliInputDataError("Deck ID {} does not reference an AT deck.".format(deckid))

    if not quiet:
        print("Starting at block:", startblock)
        print("Ending at block:", endblock)

    blockdata = show_txes_by_block(receiving_address=receiving_address, sending_address=sending_address, advanced=advanced, startblock=startblock, endblock=endblock, coinbase=coinbase, quiet=quiet, debug=debug, use_locator=use_locator, store_locator=use_locator)
    txes = blockdata["txes"]

    if debug:
        print("Block data:", blockdata)
    if use_locator:
        if "bheight" in blockdata:
            if not quiet:
                print("Stored block data until block", blockdata["bheight"], "with hash", blockdata["bhash"])
            store_locator_data(blockdata["blocks"], blockdata["bheight"], blockdata["bhash"], quiet=quiet, debug=debug)

    return txes


def store_deck_blockheights(decks: list, chain: bool=False, quiet: bool=False, debug: bool=False, blocks: int=50000):

    if not quiet:
        print("Storing blockheight locators for decks:", [d.id for d in decks])

    spawn_blockheights = []
    for d in decks:
        deck_tx = provider.getrawtransaction(d.id, 1)
        try:
            spawn_blockheights.append(provider.getblock(deck_tx["blockhash"])["height"])
        except KeyError:
            continue

    min_spawn_blockheight = min(spawn_blockheights)

    if not quiet:
        print("First deck spawn at block height:", min_spawn_blockheight)

    addresses = []
    for deck in decks:
        addresses += eu.get_deck_p2th_addresses(deck, debug=debug)

    if debug:
        print("Addresses to store", addresses)
    blockheights, lastblock = get_locator_data(addresses)
    if debug:
        print("Locator data:", blockheights, lastblock)
    if lastblock == 0: # new decks
        start_block = min_spawn_blockheight
    else:
        start_block = lastblock

    if chain is True:
        end_block = provider.getblockcount()
        blocks = end_block - start_block
        if not quiet:
            print("Full blockchain scan selected. WARNING: This can take several days!")
            print("You can interrupt the scan at any time with KeyboardInterrupt (e.g. CTRL-C) and continue later, calling the same command.")
    else:
        end_block = start_block + blocks
    if not quiet:
        print("Start block: {} End block: {} Number of blocks: {}".format(start_block, end_block, blocks))

    blockdata = show_txes_by_block(locator_list=addresses, startblock=start_block, endblock=end_block, quiet=quiet, only_store=True, debug=debug)

    if debug:
        print("Block data for all addresses:", blockdata)

    if "bheight" in blockdata:
        if not quiet:
            print("Stored block data until block", blockdata["bheight"], "with hash", blockdata["bhash"])
        store_locator_data(blockdata["blocks"], blockdata["bheight"], blockdata["bhash"], quiet=quiet, debug=debug)
    else:
        if not quiet:
            print("No new data was stored to avoid inconsistencies.")


def store_address_blockheights(addresses: list, start_block: int=0, blocks: int=50000, force: bool=False, quiet: bool=False, debug: bool=False):
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
        if force is True:
            if start_block < lastblock:
                raise ei.PacliInputDataError("Starting caching before the last stored block is not supported, as this might lead to inconsistencies.")
            if not quiet:
                print("Forcing to cache block heights as required. Last stored block was {}, continuing from block {} on.".format(lastblock, start_block))

        else:
            if not quiet:
                print("There was a previous caching process. Continuing it from last cached block {} on.".format(lastblock))
                print("To cache other block heights, use -f / --force or erase the affected addresses from the block locator file with 'address cache -e'.")
            start_block = lastblock
    else:
        if start_block > (lastblock + 1) and not force:
            if not quiet:
                print("WARNING: Block heights between {} and {} not checked.".format(lastblock, start_block))
                if not ei.confirm_continuation():
                    print("Aborted.")
                    return
    end_block = start_block + blocks

    blockdata = show_txes_by_block(locator_list=addresses, startblock=start_block, endblock=end_block, force_storing=force, quiet=quiet, debug=debug)
    new_blockheights = blockdata["blocks"] if "blocks" in blockdata else []
    if debug:
        print("Block data:", blockdata)

    if blockdata.get("bheight"):
        store_locator_data(new_blockheights, blockdata["bheight"], blockdata["bhash"], quiet=quiet, debug=debug)
        if not quiet:
            print("Stored block data until block", blockdata.get("bheight"), "with hash", blockdata.get("bhash"), ".\nBlock heights for the checked addresses:", new_blockheights)
    else:
        if not quiet:
            print("Start block located before last checked block. No new data was stored to avoid inconsistencies.")


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
    blockchain_txes = show_txes_by_block(locator_list=address_list, endblock=lastblockheight, debug=debug).get("txes")
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
