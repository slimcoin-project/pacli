"""The extended keystore allows to manage several keys and addresses.
This module contains basic and high-level commands."""

import os
import keyring
import pypeerassets as pa
from pacli.provider import provider
from pacli.config import Settings
import pacli.keystore as k

def set_new_key(new_key: str=None, backup_id: str=None, label: str=None, existing_label: str=None, network_name: str=None, legacy: bool=False) -> None: ### NEW FEATURE ###
    '''save/import new key, can be as main address or with an id, old key can be backed up
       this feature allows to import keys and generate new addresses'''

    try:
        # to prevent malfunction if "--wif" is forgot or format is wrong, this checks if the key is a hex number
        # may be even better to do that with kutil, to catch all format errors.
        if new_key:
            # print(new_key, type(new_key))
            checkkey = int(new_key, 16)
    except ValueError:
        raise ValueError("Key in wrong format.")

    kprefix = get_key_prefix(network_name, legacy)

    if not label:

        if backup_id:
            # old_key = keyring.get_password("pacli", "key")
            old_key = get_key("key")
            #keyring.set_password("pacli", get_key_prefix(network_name) + backup_id, old_key)
            set_key(kprefix + backup_id, old_key)
        elif existing_label == "key":
            raise Exception("Trying to replace main key without providing backup ID. Use --force if you really want to do that.")

    if new_key is not None:
        key = new_key
    elif existing_label:
        #key = keyring.get_password("pacli", get_key_prefix(network_name) + existing_label)
        key = get_key(kprefix + existing_label)
    else:
        key = k.generate_key()

    if label:
        set_key(kprefix + label, key)
    else:
        set_key('key', key)


def get_key_prefix(network_name: str=None, legacy: bool=False): ### NEW FEATURE ###
    # The key prefix determines the network, and separates private keys from possible other uses.
    if legacy:
        return "key_bak_"
    else:
        return "key_" + network_name + "_"

def get_key(full_label: str) -> str: ### NEW FEATURE ###
    return keyring.get_password("pacli", full_label)

def delete_key(full_label: str) -> None: ### NEW FEATURE ###
    '''delete key from keyring.'''
    keyring.delete_password("pacli", full_label)

def set_key(full_label: str, key: str) -> None: ### NEW FEATURE ###
    '''set new key, simple way'''
    keyring.set_password("pacli", full_label, key)

def get_all_labels(prefix: str):
    # returns all labels corresponding to a network shortname (the prefix)
    # does currently NOT support Windows Credential Locker nor KDE.
    # Should work with Gnome Keyring, KeepassXC, and KSecretsService.
    import secretstorage
    bus = secretstorage.dbus_init()
    collection = secretstorage.get_default_collection(bus)
    labels = []
    for item in collection.search_items({'application': 'Python keyring library', "service" : "pacli"}):
        # print(item.get_label())
        label = item.get_attributes()["username"]
        if prefix in label:
            labels.append(label)

    return labels

def show_stored_key(label: str, network_name: str, pubkey: bool=False, privkey: bool=False, wif: bool=False, json_mode=False, legacy=False):
    # TODO: json_mode (only for addresses)
    if legacy:
       fulllabel = "key_bak_" + label
    else:
       fulllabel = "key_" + network_name + "_" + label
    try:
        raw_key = bytearray.fromhex(get_key(fulllabel))
    except TypeError:
        exc_text = "No key data for key {}".format(fulllabel)
        raise Exception(exc_text)

    key = pa.Kutil(network=network_name, privkey=raw_key)

    if privkey:
        return key.privkey
    elif pubkey:
        return key.pubkey
    elif wif:
        return key.wif
    else:
        return key.address

def show_stored_address(label: str, network_name: str, json_mode=False):
    # Safer mode for show_stored_key.
    # TODO: json mode still unfinished.
    return show_stored_key(label, network_name=network_name, json_mode=json_mode)

def show_addresses(addrlist: list, keylist: list, network: str, debug=False):
    if len(addrlist) != len(keylist):
        raise ValueError("Both lists must have the same length.")
    result = []
    for kpos in range(len(keylist)):
        if (addrlist[kpos] == None) and (keylist[kpos] is not None):

            adr = show_stored_address(keylist[kpos], network_name=network)
            if debug: print("Address", adr, "got from key", keylist[kpos])
        else:
            adr = addrlist[kpos]
        result.append(adr)
    return result

def show_label(address):
    # Needs secretstorage!
    labels = get_all_labels(Settings.network)
    for fulllabel in labels:
        try:
            label = fulllabel.split("_")[-1]
        except IndexError:
            continue
        addr2 = show_stored_key(label, Settings.network)
        if address == addr2:
            return {"label" : label, "address" : address}

def new_privkey(label: str, key: str=None, backup: str=None, wif: bool=False, legacy: bool=False):
    # TODO: can't this be merged with fresh_address?
    # This command generates a new address but independently from the wallet.

    if wif:
        new_key = pa.Kutil(network=Settings.network, from_wif=key)
        key = new_key.privkey
    elif (label is None) and (key is not None):
        new_key = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(key))

    set_new_key(new_key=key, backup_id=backup, label=label, network_name=Settings.network, legacy=legacy)
    fulllabel = get_key_prefix(Settings.network, legacy) + label
    key = get_key(fulllabel)

    if not label:
        if new_key is None:
            new_key = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(load_key()))
        Settings.key = new_key

    return "Address: " + pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(key)).address

def fresh_address(label: str, backup: str=None, show: bool=True, set_main: bool=False, legacy: bool=False):
    # NOTE: This command does not assign the address an account name or label in the wallet!

    addr = provider.getnewaddress()
    privkey_wif = provider.dumpprivkey(addr)
    privk_kutil = pa.Kutil(network=Settings.network, from_wif=privkey_wif)
    privkey = privk_kutil.privkey

    fulllabel = get_key_prefix(Settings.network, legacy) + label

    try:
        if fulllabel in get_all_labels(Settings.network):
            return "ERROR: Label already used. Please choose another one."
    except ImportError:
        print("NOTE: If you do not use SecretStorage, which is likely if you use Windows, you currently have to make sure yourself you don't use the same label for two or more addresses.")

    set_key(fulllabel, privkey)

    if show:
        print("New address created:", privk_kutil.address, "with label (name):", label)
        print("Address already is saved in your wallet and in your keyring, ready to use.")
    if set_main:
        set_new_key(new_key=privkey, backup_id=backup, label=label, network_name=Settings.network, legacy=legacy)
        Settings.key = privk_kutil
        return Settings.key.address


def show_all_keys(debug: bool=False, legacy: bool=False):

    net_prefix = "bak" if legacy else Settings.network

    labels = get_all_labels(net_prefix)

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
            print(addr.ljust(35), balance.ljust(15), label.ljust(15))

        except Exception as e:
            if debug: print("ERROR:", label, e)
            continue


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

def delete_key_from_keyring(label: str, legacy: bool=False):
    prefix = get_key_prefix(Settings.network, legacy)
    try:
       delete_key(prefix + label)
       print("Key", label, "successfully deleted.")
    except keyring.errors.PasswordDeleteError:
       print("Key", label, "does not exist. Nothing deleted.")
