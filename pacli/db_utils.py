from pacli.provider import provider
from pacli.blockexp_utils import get_tx_structure
import pacli.extended_interface as ei
import pacli.extended_txtools as et
from pacli.config import Settings
from pypeerassets.networks import net_query
import sys
import os
import os.path
import hashlib

# TODO: check if unencrypted wallets lead to the "key" instead of "ckey" key in the database dict!

# Copyright notice:
# contains code from:
# PyWallet 1.2.1 (Public Domain)
# http://github.com/joric/pywallet

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

def yield_transactions(database: object, ignore_corrupted: bool=True, debug: bool=False):

    for k in database.keys():
        tx = database.get(k)
        if k.startswith(b"\x02tx"):
            try:
                raw_txdata = tx.hex()
                tx_json = provider.decoderawtransaction(raw_txdata)
                txid = tx_json["txid"]
            except ValueError as e:
                if debug:
                    print("Bad tx data:", txid, raw_txid)
                if ignore_corrupted:
                    continue
                tx_json = {}
                raise ei.PacliDataError(e)
            except AttributeError as e:
                if debug:
                    print("Bad value of tx wallet data: key {} value {}".format(k, tx))
                continue

            #if debug:
            #    print("Processing tx:", txid)
            yield [txid, tx_json]

# address tools from pywallet

__b58chars = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
__b58base = len(__b58chars)

def b58encode(v):
    """ encode v, which is a string of bytes, to base58.
    """

    long_value = 0 # 0L
    for (i, c) in enumerate(v[::-1]):
        long_value += (256**i) * c # ord(c)

    result = ''
    while long_value >= __b58base:
        div, mod = divmod(long_value, __b58base)
        result = __b58chars[mod] + result
        long_value = div
    result = __b58chars[long_value] + result

    # Bitcoin does a little leading-zero-compression:
    # leading 0-bytes in the input become leading-1s
    nPad = 0
    for c in v:
        if c == '\0': nPad += 1
        else: break

    return (__b58chars[0]*nPad) + result

def Hash(data):
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def hash_160(public_key):
    md = hashlib.new('ripemd160')
    md.update(hashlib.sha256(public_key).digest())
    return md.digest()

def public_key_to_bc_address(public_key):
    h160 = hash_160(public_key)
    return hash_160_to_bc_address(h160)

def get_addrtype(output_type: str="p2pkh"):
    nwvalues = net_query(Settings.network)
    try:
        addrtype = nwvalues.base58_raw_prefixes[output_type]
    except KeyError:
        raise ei.PacliDataError("Unsupported output type: {}".format(output_type))
    #print(addrtype.hex())
    #return int(addrtype.hex(), 16)
    return addrtype

def hash_160_to_bc_address(h160):

    addrtype = get_addrtype("p2pkh") # addrtype is now a bytearray
    # vh160 = chr(addrtype) + h160
    # vh160 = bytes([addrtype]) + h160 # python3
    vh160 = addrtype + h160
    h = Hash(vh160)
    addr = vh160 + h[0:4]
    return b58encode(addr)

def get_addresses(datadir: str=None, keyring: bool=False, ignore_corrupted: bool=False, debug: bool=False):

    database = get_database(datadir, debug=debug)
    addresses = []

    for k in database.keys():
        if b"key" not in k[:10]: # k.startswith(b"\x04ckey"):
            continue
        # value = database.get(k)
        size = k[0]
        nextsize = k[5]
        pubkey = k[6:]
        address = public_key_to_bc_address(pubkey)
        if debug:
            print("Retrieving address {} from wallet with pubkey {}".format(address, pubkey))
        addresses.append(address)
    return set(addresses)


def get_database(datadir: str=None, debug: bool=False):
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
    return d


def get_all_transactions(address: str=None, sender: str=None, firstsender: str=None, receiver: str=None, datadir: str=None, advanced: bool=False, wholetx: bool=True, sort: bool=False, exclude_coinbase: bool=False, debug: bool=False):
    # TODO to speed up this for -g/-b, it would be necessary to exclude some of the txes, e.g. coinbase. For these we wouldn't need the getrawtransactions.

    d = get_database(datadir, debug=debug)

    txes = []
    for tx_tuple in yield_transactions(d, ignore_corrupted=True, debug=debug):
        txid, tx = tx_tuple
        if exclude_coinbase:
            if "coinbase" in [v.keys() for v in tx["vin"]]:
                continue
        if receiver is not None and not et.check_receiver(tx, receiver): # optimization: receivers are much cheaper to check
            continue

        if (address or firstsender or sender) or advanced is False:
            try:
                struct = get_tx_structure(tx=tx, human_readable=False, add_txid=True)
            except ei.PacliDataError as e:
                if debug:
                    print("Bad tx data:", tx, e)
                continue

            # if (address or sender or firstsender or receiver) or advanced is False: # if advanced is True then that will not work here.
            #if address is not None:
            #    sender = receiver = address
            #senders = [s for i in struct["inputs"] for s in i["sender"]]
            #receivers = [r for o in struct["outputs"] for r in o["receivers"]]
            #if (sender not in senders) and (receiver not in receivers):
            #if ((sender is not None) and (sender not in senders)) or ((receiver is not None) and (receiver not in receivers)):
            if not et.check_address_in_txstruct(struct, address=address, firstsender=firstsender, sender=sender, debug=debug):
                #if debug:
                #    print("TX not fulfilling address requirements:", txid)
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
