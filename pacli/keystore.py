import os
import keyring
from btcpy.structs.crypto import PrivateKey

if os.name == 'nt':
    from keyring.backends import Windows
    keyring.set_keyring(Windows.WinVaultKeyring())


def generate_key() -> PrivateKey:
    '''generate new random key'''

    return os.urandom(32).hex()


def init_keystore(new_key=None) -> None:
    '''save key to the keystore'''

    if not keyring.get_password('pacli', 'key'):
        keyring.set_password("pacli", 'key', generate_key())


def load_key() -> PrivateKey:
    '''load key from the keystore'''

    init_keystore()

    key = keyring.get_password('pacli', 'key')

    return key

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
        key = generate_key()

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
