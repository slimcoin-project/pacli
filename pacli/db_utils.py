from pacli.provider import provider
from pacli.blockexp_utils import get_tx_structure

# TODO: the decoding works but the transactions seem not to have the correct format. TXIDs are off.
# txid is reverse of the txjson["txid"]!

PATH = '/home/usery/.slimcoin/testnet2/testnet/wallet.dat'

def get_wallet_database(path: str=PATH):
    from berkeleydb import db
    d = db.DB()
    d.open(path, 'main', db.DB_BTREE, db.DB_THREAD | db.DB_RDONLY)
    return d

def print_transactions(database: object):
    for k in database.keys():
        entry = database.get(k)
        if k.startswith(b"\x02tx"):
            txid = k[3:]
            print(txid, entry)
            print(txid.hex(), entry.hex())
            print(len(txid))


def yield_transactions(database: object):
    # txes = []
    for k in database.keys():
        tx = database.get(k).hex()
        if k.startswith(b"\x02tx"):
            txid = k[3:].hex()
            tx_json = provider.decoderawtransaction(tx)
            print(txid, tx_json["txid"])
            # txes.append({ txid : tx_json })
            yield [txid, tx_json]

    # return txes


def get_all_transactions(address: str=None, structs: bool=False, sort: bool=False, debug: bool=False):
    d = get_wallet_database()
    txes = []
    for tx_tuple in yield_transactions(d):
       txid, tx = tx_tuple
       if address is not None or structs is True:
          struct = get_tx_structure(tx)
          if address:
              if address in struct["sender"] or address in struct["receiver"]:
                  txes.append(tx)
              elif struct:
                  txes.append(struct)
          else:
              txes.append(tx)

    return txes



