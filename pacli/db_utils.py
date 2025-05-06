from pacli.provider import provider
from pacli.blockexp_utils import get_tx_structure
import pacli.extended_interface as ei
import sys
import os
import os.path

try:
    import berkeleydb
except ImportError:
    raise ei.PacliDataError("Berkeley databases not supported. Install berkeleydb Python package for this command to run.")

def determine_db_dir(): # from pywallet

    import platform
    if platform.system() == "Darwin":
        basedir = os.path.expanduser("~/Library/Application Support/Bitcoin/")
    elif platform.system() == "Windows":
        basedir = os.path.join(os.environ['APPDATA'], "Bitcoin")
    else:
        basedir = os.path.expanduser("~/.slimcoin")
    if provider.is_testnet is True:
        return basedir + "/testnet"
    else:
        return basedir

def get_wallet_database(path: str):

    db = berkeleydb.db
    d = db.DB()
    d.open(path, 'main', db.DB_BTREE, db.DB_THREAD | db.DB_RDONLY)
    return d

"""def inversetxid(txid: str, debug: bool=False) -> str: # from pywallet. Currently not used.
    if len(txid) != 64:
        if debug:
            print("Bad txid:", txid)
        raise ValueError("Bad txid found: {}".format(txid))
    new_txid = ""
    for i in range(32):
        new_txid += txid[62 - 2 * i];
        new_txid += txid[62 - 2 * i + 1];
    if debug:
        print("Txid", txid)
    return new_txid"""

def yield_transactions(database: object, ignore_corrupted: bool=False, debug: bool=False):

    for k in database.keys():
        tx = database.get(k)
        if k.startswith(b"\x02tx"):
            try:
                raw_txdata = tx.hex()
                tx_json = provider.decoderawtransaction(raw_txdata)
                txid = tx_json["txid"]
            except ValueError as e:
                if not ignore_corrupted:
                    continue
                if debug:
                    print("Bad tx data:", txid, raw_txdata)
                tx_json = {}
                raise ei.PacliDataError(e)

            #if debug:
            #    print("Processing tx:", txid)
            yield [txid, tx_json]


def get_all_transactions(address: str=None, datadir: str=None, advanced: bool=False, wholetx: bool=True, sort: bool=False, debug: bool=False):

    if datadir is None:
        datadir = determine_db_dir()
        locmsg = "standard"
    else:
        datadir = os.path.expanduser(datadir)
        if provider.is_testnet is True:
            datadir = datadir + "/testnet"
        locmsg = "given"
    path = datadir + "/wallet.dat"
    if debug:
        print("Searching wallet file at path:", path)
    try:
        d = get_wallet_database(path)
    except FileNotFoundError:
        raise ei.PacliDataError("Wallet file not found at the {} location.".format(locmsg))
    except berkeleydb.db.DBAccessError:
        raise ei.PacliDataError("Wallet file cannot be accessed, permission denied. Please check permissions.")

    txes = []
    for tx_tuple in yield_transactions(d, ignore_corrupted=True, debug=debug):
        txid, tx = tx_tuple
        if address is not None or advanced is False:
            try:
                struct = get_tx_structure(tx=tx)
            except ei.PacliDataError as e:
                if debug:
                    print("Bad tx data:", tx, e)
                continue

        if address is not None:
            if (address not in [s for i in struct["inputs"] for s in i["sender"]]) and (address not in [r for o in struct["outputs"] for r in o["receivers"]]):
                continue

        if wholetx:
            complete_tx = provider.getrawtransaction(txid, 1)
            if not advanced:
                if "blockhash" in complete_tx:
                    blockheight = provider.getblock(complete_tx["blockhash"])["height"]
                    struct.update({"blockheight" : blockheight})
                result = struct
            else:
                result = complete_tx
        else:
            result = tx if advanced is True else struct
        txes.append(result)
        if debug:
                print("TX appended:", tx["txid"])
    if debug:
        print("Number of transactions found:", len(txes))
    return txes
