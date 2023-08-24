import pypeerassets as pa
import pacli.keystore as k
import pacli.keystore_extended as ke
import pacli.extended_interface as ei
import pacli.extended_utils as eu
import pacli.config_extended as ce
from pacli.config import Settings
from pacli.provider import provider

# Address "bifurcations": can be either used with the legacy keystore_extended module or with the new Tools module.

def fresh_address(label: str, set_main: bool=False, backup: str=None, keyring: bool=False, legacy: bool=False, silent: bool=False):

    label = str(label)
    if keyring:
        address = ke.fresh_address(label, backup=backup, legacy=legacy, silent=silent)
    elif legacy or backup:
        if not silent:
            print("--legacy and --backup are only supported when using --keyring.")
        return None
    else:
        address = provider.getnewaddress()
        ei.run_command(store_address, label, address=address)
        # ei.run_command(ce.write_item, "address", label, address)

    if not silent:
        print("New address created:", address, "with label (name):", label)
        print("Address already is saved in your wallet, ready to use.")

    if set_main:
        return set_main_key(label, keyring=keyring, legacy=legacy, silent=silent)

def set_main_key(label: str, backup: str=None, keyring: bool=False, legacy: bool=False, silent: bool=False):
    if keyring:
        return ke.set_main_key(label, backup=backup, legacy=legacy)

    if backup:
        print("Backups not supported when using Tools for address labels.")
        return

    address = get_address(label)
    wif_key = provider.dumpprivkey(address)

    try:
        key = pa.Kutil(network=Settings.network, from_wif=wif_key).privkey
    except ValueError:
        ei.print_red("Error: Invalid address or private key.")
        return

    ke.set_key("key", key) # Note that this function isn't present in the standard pacli keystore.
    Settings.key = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(k.load_key()))

    if not silent:
        return Settings.key.address

def show_stored_address(label: str, network_name: str=Settings.network, keyring: bool=False, noprefix: bool=False, raise_if_invalid_label: bool=False, pubkey: bool=False, privkey: bool=False, wif: bool=False, legacy: bool=False):
    # Safer mode for show_stored_key.
    if keyring:
        return ke.show_stored_key(str(label), network_name=network_name, noprefix=noprefix, pubkey=pubkey, privkey=privkey, wif=wif, raise_if_invalid_label=raise_if_invalid_label)
    elif pubkey or privkey or wif:
        print("--privkey, --wif and --pubkey are only supported when using --keyring.")
    else:
        return get_address(str(label), network_name=network_name, noprefix=noprefix)

def process_address(addr_string: str) -> str:
    """Allows to use a label or an address; you'll get an address back."""
    try:
        address = show_stored_address(addr_string, keyring=True, raise_if_invalid_label=True)
    except TypeError:
        try:
            address = show_stored_address(addr_string, keyring=False)
            assert address is not None
        except AssertionError:
            return addr_string
    return address

def show_label(address: str, set_main: bool=False, keyring: bool=False) -> dict:
    if keyring:
        label = ke.show_label(address)

    # extended_config address category has only one entry per value
    # so we can pick the first item.
    try:
        fulllabel = ce.search_value("address", address)[0]
    except IndexError:
        print("No label is assigned to that address.")
        return
    # label is differently stored in extconf than in keyring.
    label = "_".join(fulllabel.split("_")[1:])

    if set_main:
        print("This address is now the main address (--set_main option).")
        set_main_key(label)

    return {"label" : label, "address" : address}

# extended config

def set_label(label: str, address: str, network_name: str=Settings.network, set_main: bool=False, modify: bool=False, keyring: bool=False):

    if keyring:
        ke.set_new_key(label=str(label), new_address=address, modify=modify, network_name=Settings.network)
    else:
        ei.run_command(store_address, str(label), address=address, network_name=network_name, modify=modify)

    if set_main:
        return set_main_key(str(label), keyring=keyring)

def store_address(label: str, network_name: str=Settings.network, address: str=None, full: bool=False, modify: bool=False):
    keyring_prefix = "key_"
    # ext_label is the extended config label, full_label includes the 'key_' prefix used in the keyring.
    # full_label is only necessary if no address is given.

    if not full:
        ext_label = network_name + "_" + label
        full_label = keyring_prefix + ext_label
    else:
        full_label = label
        ext_label = full_label[len(keyring_prefix):]

    if not address:
        address = ke.label_to_kutil(full_label).address

    ce.write_item(category="address", key=ext_label, value=address, modify=modify, network_name=network_name)


def get_address(label: str, network_name: str=Settings.network, noprefix: bool=False) -> str:
    ext_label = network_name + "_" + label
    return ce.read_item(category="address", key=ext_label)

def get_all_labels(prefix: str=Settings.network, keyring: bool=False) -> list:
    if keyring:
        return ke.get_labels_from_keyring(prefix)

    labels = list(ce.get_config()["address"].keys())
    # TODO: investigate reason for the following lines
    #labels_in_legacy_format = [ "key_" + l for l in labels ]
    #return labels_in_legacy_format
    return labels

def delete_label(label: str, network_name: str=Settings.network, keyring: bool=False, legacy: bool=False, now: bool=False):
    if keyring:
        if now:
            ke.delete_key_from_keyring(str(label), legacy=legacy, network_name=network_name)
        else:
            print("Dry run: label {} of network {} to delete. Delete with --now.".format(label, network_name))
    else:
        full_label = network_name + "_" + str(label)
        ce.delete_item("address", full_label, now=now)


def show_addresses(addrlist: list, label_list: list, network: str=Settings.network, debug=False):
    # This function "synchronizes" labels and addresses given as lists.
    # Useful if we have an option where we can alternatively input addresses and labels.
    if len(addrlist) != len(label_list):
        raise ValueError("Both lists must have the same length.")
    result = []
    for lpos in range(len(label_list)):
        if addrlist[lpos] == None:
            if label_list[lpos] is None: # if both values are None, they stay None.
                adr = None
            else:
                adr = show_stored_address(label_list[lpos], network_name=network)
                if debug: print("Address", adr, "got from label", label_list[lpos])
        else:
            adr = addrlist[lpos]
        result.append(adr)
    return result

def get_addresses_and_labels(prefix: str=Settings.network, keyring: bool=False) -> dict:
    if not keyring:
        return ce.get_config()["address"]

    labels = ke.get_labels_from_keyring(prefix)
    result = {}
    for label in labels:
        address = show_stored_address(label=label, noprefix=True)
        result.update({label: address})
    return result


def get_address_transactions(addr_string: str, sent: bool=False, received: bool=False, advanced: bool=False) -> list:

    address = process_address(addr_string)
    #if label:  # label overrides address
    #    address = show_stored_address(label, network_name=Settings.network)
    if not address:
        ei.print_red("Error: You must provide either a valid address or a valid label.")

    all_txes = True if (not sent) and (not received) else False
    all_txids = set([t["txid"] for t in eu.get_wallet_transactions()])
    all_wallet_txes = [provider.getrawtransaction(txid, 1) for txid in all_txids]
    result = []

    for tx in all_wallet_txes:
        if sent or all_txes:
            for sender_dict in eu.find_tx_senders(tx):
                if address in sender_dict["sender"]:
                    txdict = tx if advanced else {"txid" : tx["txid"], "type": "send", "value" : sender_dict["value"]}
                    result.append(txdict)
        if received or all_txes:
            for output in tx["vout"]:
                out_addresses = output["scriptPubKey"].get("addresses")
                try:
                    if address in out_addresses:
                        txdict = tx if advanced else {"txid" : tx["txid"], "type" : "receive", "value": output["value"]}
                        result.append(txdict)
                except TypeError:
                    continue

    return result
