"""The extended keystore allows to manage several keys and addresses.
This module contains basic and high-level commands."""

import os
import keyring
import pypeerassets as pa
from pypeerassets.networks import networks as supported_networks
from pacli.provider import provider
from pacli.config import Settings
import pacli.keystore as k
import pacli.config_extended as ce
import pacli.extended_interface as ei
import pacli.extended_utils as eu

def set_new_key(new_key: str=None, new_address: str=None, backup_id: str=None, label: str=None, existing_label: str=None, network_name: str=Settings.network, modify: bool=False, legacy: bool=False, quiet: bool=False) -> None:
    '''save/import new key, can be as main address or with a label, old key can be backed up
       this feature allows to import keys and generate new addresses'''

    try:
        # to prevent malfunction if "--wif" is forgot or format is wrong, this checks if the key is a hex number
        # may be even better to do that with kutil, to catch all format errors.
        if new_key:
            checkkey = int(new_key, 16)
    except ValueError:
        if not quiet:
            ei.print_red("Key in wrong format.")
        return

    kprefix = get_key_prefix(network_name, legacy)

    if not label:

        if backup_id:
            old_key = get_key("key")
            set_key(kprefix + backup_id, old_key)
        elif existing_label == "key":
            if not quiet:
                ei.print_red("Error: Trying to replace main key without providing backup ID. Use --force if you really want to do that.")
            return
    else:
        label = str(label)

    if new_key is not None:
        key = new_key
    elif new_address is not None:
        wif_key = provider.dumpprivkey(new_address)
        try:
            key = pa.Kutil(network=network_name, from_wif=wif_key).privkey
        except ValueError:
            if not quiet:
                ei.print_red("Error: Invalid address or private key.")
            return

    elif existing_label:
        key = get_key(kprefix + existing_label)
    else:
        key = k.generate_key()

    if label:
        if modify:
            try:
                raw_old_label = show_keyring_label(new_address)["label"]
                old_label = kprefix + raw_old_label
                delete_key(old_label)
            except ImportError:
                raise ei.PacliInputDataError("Option --modify not available, secretstorage missing (probably not supported by your operating system)")
            except (KeyError, TypeError):
                if not quiet:
                    print("Note: This address/key wasn't stored in the keyring before. No keyring entry was deleted.")
        set_key(kprefix + label, key)
    else:
        set_key('key', key)


def get_key_prefix(network_name: str=Settings.network, legacy: bool=False, extconf: bool=False):
    # The key prefix determines the network, and separates private keys from possible other uses.
    if legacy:
        return "key_bak_"
    elif extconf:
        return network_name + "_"
    else:
        return "key_" + network_name + "_"

def get_key(full_label: str) -> str:
    return keyring.get_password("pacli", full_label)

def delete_key(full_label: str) -> None:
    '''delete key from keyring.'''
    keyring.delete_password("pacli", full_label)

def set_key(full_label: str, key: str) -> None:
    '''set new key, simple way'''
    keyring.set_password("pacli", full_label, key)

def get_labels_from_keyring(prefix: str=Settings.network):
    # returns all (full) labels corresponding to a network shortname (the prefix)
    # does currently NOT support Windows Credential Locker nor KDE.
    # Should work with Gnome Keyring, KeepassXC, and KSecretsService.

    try:
        import secretstorage
    except (ImportError, ModuleNotFoundError, secretstorage.exceptions.SecretServiceNotAvailableException):
        print("""This feature needs the 'secretstorage' package, which is currently not installed.
It may not be supported by your operating system or desktop environment.
In this case, it is recommended to use the extended configuration file to store address labels.""")
        raise ImportError

    bus = secretstorage.dbus_init()
    collection = secretstorage.get_default_collection(bus)
    labels = []
    for item in collection.search_items({'application': 'Python keyring library', "service" : "pacli"}):
        # print(item.get_label())
        label = item.get_attributes()["username"]
        try:
            if (not prefix) or (label.split("_")[1] == prefix):
                labels.append(label)
        except IndexError:
            continue

    return labels

def show_stored_key(label: str, network_name: str=Settings.network, pubkey: bool=False, privkey: bool=False, wif: bool=False, legacy: bool=False, noprefix: bool=False, raise_if_invalid_label: bool=False):

    label = str(label)
    if legacy:
        full_label = "key_bak_" + label
    elif noprefix:
        full_label = label
    else:
        full_label = "key_" + network_name + "_" + label
    try:
        raw_key = bytearray.fromhex(get_key(full_label))
    except TypeError:
        if raise_if_invalid_label:
            raise
        else:
            ei.print_red("Error: Label {} was not stored in the keyring.".format(label))
            return None

    key = pa.Kutil(network=network_name, privkey=raw_key)

    if privkey:
        return key.privkey
    elif pubkey:
        return key.pubkey
    elif wif:
        return key.wif
    else:
        return key.address

def show_keyring_label(address: str, set_main: bool=False) -> dict:
    # Function is now reserved for usage with keyring.

    # NOTE: The ImportError has to be catched in all commands using this function.
    labels = get_labels_from_keyring(Settings.network)

    for full_label in labels:
        legacy = is_legacy_label(full_label)
        try:
            label = format_label(full_label, keyring=True)
        except IndexError:
            continue
        if address == show_stored_key(label, Settings.network, legacy=legacy):
            break
    else:
        raise ei.PacliInputDataError("No label was stored for address {}.".format(address))

    return label

def format_label(full_label: str, keyring: bool=False):

    if keyring:
        prefix = "_".join(full_label.split("_")[:2]) + "_"
    else:
        prefix = full_label.split("_")[0] + "_"

    # label = full_label.replace(prefix, "")
    label = full_label[len(prefix):]
    return label

def is_legacy_label(full_label: str):
    # The label format was originally less standardized
    # without this test, errors will be raised due to that.

    label_elements = full_label.split("_")
    network_names = [ n.shortname for n in supported_networks ]

    # current labels have at least 3 elements, network is the second one,
    if (len(label_elements) >= 3) and (label_elements[0] == "key") and (label_elements[1] in network_names):
        return False
    else:
        return True

def new_privkey(label: str, key: str=None, backup: str=None, wif: bool=False, legacy: bool=False):
    # TODO: can't this be merged with fresh_address?
    # This command generates a new address but independently from the wallet.

    if wif:
        new_key = pa.Kutil(network=Settings.network, from_wif=key)
        key = new_key.privkey
    elif (label is None) and (key is not None):
        new_key = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(key))

    set_new_key(new_key=key, backup_id=backup, label=label, network_name=Settings.network, legacy=legacy)
    full_label = get_key_prefix(Settings.network, legacy) + label
    key = get_key(full_label)

    if not label:
        if new_key is None:
            new_key = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(load_key()))
        Settings.key = new_key

    return "Address: " + pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(key)).address

def store_address_in_keyring(label: str, addr: str, backup: str=None, set_main: bool=False, legacy: bool=False, quiet: bool=False):
    # NOTE: This command does not assign the address an account name or label in the wallet.

    privkey_wif = provider.dumpprivkey(addr)
    privk_kutil = pa.Kutil(network=Settings.network, from_wif=privkey_wif)
    full_label = get_key_prefix(Settings.network, legacy=legacy) + str(label)

    try:
        if full_label in get_labels_from_keyring():
            return "ERROR: Label already used. Please choose another one."
    except ImportError:
        print("NOTE: If you do not use SecretStorage, which is likely if you use Windows, you currently have to make sure yourself you don't use the same label for two or more addresses.")

    set_key(full_label, privk_kutil.privkey)

def show_all_keys(debug: bool=False, legacy: bool=False):

    net_prefix = "bak" if legacy else Settings.network

    try:
        labels = get_labels_from_keyring(net_prefix)
    except ImportError:
        raise ei.PacliInputDataError("This feature is not available if you don't use 'secretstore'.")

    prefix = "key_" + net_prefix + "_"
    print("Address".ljust(35), "Balance".ljust(15), "Label".ljust(15))
    print("---------------------------------------------------------")
    for raw_label in labels:
        try:
            label = raw_label.replace(prefix, "")
            raw_key = bytearray.fromhex(get_key(raw_label))
            key = pa.Kutil(network=Settings.network, privkey=raw_key)
            addr = key.address
            balance = str(provider.getbalance(addr))
            if balance != "0":
                balance = balance.rstrip("0")
            print(addr.ljust(35), balance.ljust(15), label.ljust(15))

        except Exception as e:
            if debug: print("ERROR:", label, e)
            continue

def set_main_key(label: str, backup: str=None, legacy: bool=False) -> str:

    try:
        set_new_key(existing_label=str(label), backup_id=backup, network_name=Settings.network, legacy=legacy)
    except TypeError:
        ei.print_red("Error: Label {} does not exist. Main address is not changed.".format(str(label)))
        return ""

    Settings.key = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(k.load_key()))
    return Settings.key.address

def import_key_to_wallet(accountname: str, label: str=None, legacy: bool=False):

    prefix = get_key_prefix(Settings.network, legacy)
    if label:
        pkey = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(get_key(prefix + label)))
        wif = pkey.wif
    else:
        wif = Settings.key.wif
    if Settings.network in ("slm", "tslm"):
        provider.importprivkey(wif, accountname, rescan=True)
    else:
        provider.importprivkey(wif, account_name=accountname)

def delete_key_from_keyring(label: str, network_name: str=Settings.network, legacy: bool=False):
    prefix = get_key_prefix(network_name, legacy=legacy)
    try:
       delete_key(prefix + label)
       print("Key", label, "successfully deleted.")
    except keyring.errors.PasswordDeleteError:
       print("Key", label, "does not exist. Nothing deleted.")

def label_to_kutil(full_label: str) -> pa.Kutil:
    raw_key = bytearray.fromhex(get_key(full_label))
    return pa.Kutil(network=Settings.network, privkey=raw_key)
