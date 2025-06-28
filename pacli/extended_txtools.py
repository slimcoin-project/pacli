# transaction utilities

def check_receiver(tx: dict, receiver: str):
    receivers = []
    for o in tx["vout"]:
        try:
            receivers.append(o["scriptPubKey"]["addresses"][0])
        except (KeyError, IndexError):
            continue # case OP_RETURN etc.

    #except (KeyError, AttributeError, AssertionError):
    #    return False
    #return True
    return receiver in receivers

def check_address_in_txstruct(tx: dict, address: str=None, sender: str=None, firstsender: str=None, receiver: str=None, debug: bool=False) -> bool:
    # Note: address means an OR relation normally (i.e. address can be sender OR receiver).
    # If an AND relation is needed, sender and receiver can be set to the same address.
    # firstsender is for AT txes, where only the first input is credited.

    senders = [s for i in tx["inputs"] for s in i["sender"]]
    receivers = [r for o in tx["outputs"] for r in o["receivers"]]

    if firstsender is not None:
        if len(senders) == 0 or senders[0] != firstsender:
            return False
    if (sender is not None) and (sender not in senders):
        return False
    if (receiver is not None) and (receiver not in receivers):
        return False
    if (address is not None) and (address not in senders + receivers):
        return False
    return True


def return_tx_format(fmt: str, txjson: dict=None, txstruct: dict=None, tracked_address: str=None, debug: bool=False) -> dict:
    # should contain common tx formats except the getrawtransaction TXJSON and the txstruct.

    if fmt == "gatewaytx" and txstruct is not None: # support for txjson probably not needed here
        outputs_to_tracked, oindices = [], []
        for oindex, o in enumerate(txstruct["outputs"]):
            if (o.get("receivers") is not None and tracked_address in o["receivers"]):
                outputs_to_tracked.append(o)
                oindices.append(oindex)

        if outputs_to_tracked:
            tracked_value = sum([o["value"] for o in outputs_to_tracked])
            # sender = senders[0] if len(senders) > 0 else "COINBASE" # fix for coinbase txes
            # result = {"sender" : sender, "outputs" : outputs, "blockheight" : height, "oindices": oindices, "ovalue" : tracked_value}
        else:
            return None


        result = {"txid" : txstruct["txid"],
                  "value" : tracked_value, # txstruct["ovalue"],
                  "outputs" : oindices, # txstruct["oindices"],
                  "blockheight" : txstruct["blockheight"]}

    return result


def extract_txids_from_utxodict(txdicts: list, exclude_cats: list=[], required_address: str=None, debug: bool=False):
    # Processes listtransactions output.
    processed_txids = []
    for txdict in txdicts:
        try:
            assert txdict["txid"] not in processed_txids

            for cat in exclude_cats:
                assert txdict["category"] != cat

            if required_address is not None:
                assert txdict["address"] == required_address

        except (AssertionError, KeyError):
            continue

        processed_txids.append(txdict["txid"])
        yield txdict["txid"]


