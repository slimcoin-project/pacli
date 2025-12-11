from prettyprinter import cpprint as pprint
import pypeerassets as pa
import pacli.keystore as k
import pacli.extended_keystore as ke
import pacli.extended_interface as ei
import pacli.extended_utils as eu
import pacli.extended_queries as eq
import pacli.extended_config as ce
import pacli.extended_constants as c
import pacli.blockexp_utils as bu
from pypeerassets.pautils import exponent_to_amount
from pacli.config import Settings
from pacli.provider import provider
import time

# address tools

def fresh_address(label: str, set_main: bool=False, backup: str=None, check_usage: bool=False, keyring: bool=False, legacy: bool=False, quiet: bool=False):

    label = str(label)
    addr_txes = 1

    while addr_txes:
        address = provider.getnewaddress()

        if check_usage:
            if not quiet:
                print("Checking usage of new address {} (can take some minutes) ...".format(address))
            # addr_txes = len(eq.get_address_transactions(addr_string=address, include_coinbase=True))
            addr_txes = check_first_tx(address)
            if not quiet:
                if addr_txes > 0 :
                    print("Address was already used. Trying new address.")
                else:
                    print("Usage check PASSED, no recorded transactions.")
        else:
            addr_txes = 0

    if keyring:
        ke.store_address_in_keyring(label, address, backup=backup, legacy=legacy, quiet=quiet)
    elif legacy or backup:
        if not quiet:
            print("--legacy and --backup are only supported when using --keyring.")
        return None

    else:
        store_address(label, address=address)


    if not quiet:
        print("New address created:", address, "with label (name):", label)
        print("Address already is saved in your wallet, ready to use, and set as the current main address.")

    if set_main:
        return set_main_key(label, keyring=keyring, legacy=legacy, quiet=quiet)

def set_main_key(label: str=None, address: str=None, backup: str=None, keyring: bool=False, legacy: bool=False, quiet: bool=False):
    if keyring and not address:
        return ke.set_main_key(label, backup=backup, legacy=legacy)

    if backup:
        print("Backups not supported when using external config file for address labels.")
        return

    if label is not None:
        address = get_address(label)
        if address is None:
            raise ei.PacliDataError("Label does not exist.")
    elif address is None:
        raise ei.PacliDataError("No address nor label provided.")

    if not eu.is_mine(address):
        raise ei.PacliDataError("Address does not exist or is not stored in your wallet.")

    wif_key = provider.dumpprivkey(address) # TODO: keyring not supported here it seems!
    if type(wif_key) == dict and wif_key.get("code") == -13:
        raise ei.PacliDataError("Your {} client's wallet is locked. You need to unlock it before you change the main address.\nChanging the main address wasn't possible, however if you were running this command to create a fresh address with a new label the address was created and associated with the label of your choice.".format(Settings.network.upper()))

    try:
        key = pa.Kutil(network=Settings.network, from_wif=wif_key).privkey
    except ValueError as e:
        if "Invalid wif length" in str(e):
            raise ei.PacliDataError("WIF key corrupted.")
        else:
            raise ei.PacliDataError("Invalid or non-wallet address (or incorrect command usage).")
        return

    ke.set_key("key", key) # Note that this function isn't present in the standard pacli keystore.
    Settings.key = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(k.load_key()))

    if not quiet:
        print("Main address set to:", Settings.key.address)
        print("Balance:", provider.getbalance(address))

def show_stored_address(label: str, network_name: str=Settings.network, keyring: bool=False, noprefix: bool=False, raise_if_invalid_label: bool=False, pubkey: bool=False, privkey: bool=False, wif: bool=False, legacy: bool=False):
    # Safer mode for show_stored_key.
    if keyring is True:
        return ke.show_stored_key(str(label), network_name=network_name, noprefix=noprefix, pubkey=pubkey, privkey=privkey, wif=wif, raise_if_invalid_label=raise_if_invalid_label)
    elif pubkey or privkey or wif:
        print("--privkey, --wif and --pubkey are only supported when using --keyring.")
    else:
        return get_address(str(label), network_name=network_name, noprefix=noprefix)

def process_address(addr_string: str, keyring: bool=False, try_alternative: bool=False, network_name: str=Settings.network, debug: bool=False) -> str:
    """Allows to use a label or an address; you'll get an address back."""
    # TODO it is not clear if the branch with try_alternative is still needed. For now it's set to false.
    if addr_string is None:
        return None # TODO: recheck this!
    result = None
    try:
        address = show_stored_address(addr_string, keyring=keyring, raise_if_invalid_label=True)
        assert address is not None
        result = address
    except (TypeError, AssertionError):
        try:
            assert (not keyring) and try_alternative
            address = show_stored_address(addr_string, keyring=True, raise_if_invalid_label=True)
            assert address is not None
            result = address
        except (TypeError, AssertionError):
            # TODO: we don't check here if the addr_string is a valid address.
            result = addr_string

    if not eu.is_possible_address(result, network_name):
        msg_keyring = "keyring" if keyring is True else "extended configuration file"
        raise ei.PacliInputDataError("Value {} is neither a valid address nor an existing label in the {}.".format(result, msg_keyring))
    return result

def show_label(address: str, set_main: bool=False, keyring: bool=False) -> dict:
    if keyring:
        try:
            label = ke.show_keyring_label(address)
        except ImportError:
            raise ei.PacliInputDataError("Feature not supported without 'secretstorage'.")

    else:
        # extended_config address category has only one entry per value
        # so we can pick the first item.
        try:
            # TODO this is a bit inconsistent as it uses a function directly which should be private
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

def set_label(label: str, address: str, network_name: str=Settings.network, set_main: bool=False, modify: bool=False, keyring: bool=False, quiet: bool=False):

    if (not modify) and (not eu.is_possible_address(address, network_name)):
        raise ei.PacliInputDataError("Value must be a valid address.")

    if keyring:
        ke.set_new_key(label=str(label), new_address=address, modify=modify, network_name=Settings.network, quiet=quiet)
    else:
        store_address(str(label), address=address, network_name=network_name, modify=modify, quiet=quiet)

    if set_main:
        return set_main_key(str(label), keyring=keyring)

def store_address(label: str, network_name: str=Settings.network, address: str=None, full: bool=False, modify: bool=False, replace: bool=False, to_wallet: bool=False, quiet: bool=False):
    keyring_prefix = "key_"
    # ext_label is the extended config label, full_label includes the 'key_' prefix used in the keyring.
    # full option means that full keyring labels are processed.
    # full_label is only necessary if the full option is True or no address is given.

    if full:
        full_label = label
        ext_label = full_label[len(keyring_prefix):]
    else:
        ext_label = network_name + "_" + label
        full_label = keyring_prefix + ext_label

    if not address:
        address = ke.label_to_kutil(full_label).address

    ce.write_item(category="address", key=ext_label, value=address, modify=modify, network_name=network_name, replace=replace, quiet=quiet)

    if to_wallet is True:
        ke.import_key_to_wallet("keyring_addresses", ext_label[len(network_name + "_"):])


def get_address(label: str, network_name: str=Settings.network, noprefix: bool=False) -> str:
    ext_label = label if noprefix else network_name + "_" + label
    return ce.read_item(category="address", key=ext_label)

def get_all_labels(prefix: str=Settings.network, keyring: bool=False) -> list:
    if keyring:
        try:
            return ke.get_labels_from_keyring(prefix)
        except ImportError:
            raise ei.PacliInputDataError("Feature not supported without 'secretstorage'.")

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
        ce.delete("address", label, now=now)

def store_addresses_from_keyring(network_name: str=Settings.network, replace: bool=False, quiet: bool=False, debug: bool=False) -> None:
    """Stores all labels/addresses stored in the keyring in the extended config file."""
    if not quiet:
        print("Storing all addresses of network", network_name, "from keyring into extended config file.")
        print("The config file will NOT store private keys. It only allows faster access to addresses.")
    try:
        keyring_labels = ke.get_labels_from_keyring(network_name)
    except ImportError:
        raise ei.PacliInputDataError("Feature not supported without 'secretstorage'.")
    if debug:
        print("Labels (with prefixes) retrieved from keyring:", keyring_labels)

    for full_label in keyring_labels:
        try:
            store_address(full_label, full=True, replace=replace, to_wallet=True)
        except ei.ValueExistsError:
            if not quiet:
                print("Label {} already stored.".format("_".join(full_label.split("_")[2:])))
            continue

def check_first_tx(address: str, debug: bool=False):
    # this command only checks the first transaction of an address, and is thus no replacement for eq.get_wallet_transactions.
    for account in provider.listaccounts():
        account_addresses = provider.getaddressesbyaccount(account)
        if address in account_addresses:
            if debug:
                print("Account of address {}: {}".format(address, account))
            break
    else:
        return []
    start=0
    while True:
        txes = provider.listtransactions(account=account, many=500, since=start)
        if len(txes) == 0:
            break
        for tx in txes:
            try:
                tx_address = tx["address"]
                print("Address in tx:", tx_address)
            except KeyError:
                continue
            if address == tx_address:
                return True
        start += 500
        if debug:
            print("next 500 ...")
    return False


