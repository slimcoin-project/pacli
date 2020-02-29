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

def set_new_key(new_key: str=None, backup_id: str=None, key_id: str=None, old_key_backup: str=None, force: bool=False) -> None: ### NEW FEATURE ###
    '''save/import new key, can be as main address or with an id, old key can be backed up
       this feature allows to import keys and generate new addresses
       It MAY be better to replace key_bak by other identifier, but that has to be discussed.'''

    try:
        # to prevent malfunction if "--wif" is forgot or format is wrong
        # may be even better to do that with kutil, to catch all format errors.
        if new_key:
            print(new_key, type(new_key))
            checkkey = int(new_key, 16) 
    except ValueError:
        raise ValueError("Key in wrong format.")

    if not key_id:
        old_key = keyring.get_password("pacli", "key")
        if backup_id:
            keyring.set_password("pacli", "key_bak_" + backup_id, old_key)
        elif not force:
            raise Exception("Trying to replace main key without providing backup ID. Use --force if you really want to do that.")

    if new_key:
        key = new_key
    elif old_key_backup:
        key = keyring.get_password("pacli", "key_bak_" + old_key_backup)
    else:
        key = generate_key()

    if key_id:
        keyring.set_password("pacli", "key_bak_" + key_id, key)
    else:
        keyring.set_password("pacli", 'key', key)
    

def get_key(key_id: str) -> str: ### NEW FEATURE ###
    return keyring.get_password("pacli", "key_bak_" + key_id)

def delete_key(key_id: str) -> None: ### NEW FEATURE ###
    '''delete key from keyring.'''
    keyring.delete_password("pacli", "key_bak_" + key_id)
