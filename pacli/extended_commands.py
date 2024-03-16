import pypeerassets as pa
import pacli.keystore as k
import pacli.keystore_extended as ke
import pacli.extended_interface as ei
import pacli.extended_utils as eu
import pacli.config_extended as ce
import pacli.blockexp as bx
from pacli.config import Settings
from pacli.provider import provider

# Address "bifurcations": can be either used with the legacy keystore_extended module or with the new Tools module.

def fresh_address(label: str, set_main: bool=False, backup: str=None, keyring: bool=False, legacy: bool=False, quiet: bool=False):

    label = str(label)
    if keyring:
        address = ke.fresh_address(label, backup=backup, legacy=legacy, quiet=quiet)
    elif legacy or backup:
        if not quiet:
            print("--legacy and --backup are only supported when using --keyring.")
        return None
    else:
        address = provider.getnewaddress()
        ei.run_command(store_address, label, address=address)
        # ei.run_command(ce.write_item, "address", label, address)

    if not quiet:
        print("New address created:", address, "with label (name):", label)
        print("Address already is saved in your wallet, ready to use.")

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
    elif address is None:
        raise ei.PacliInputDataError("No address nor label provided.")

    wif_key = provider.dumpprivkey(address)

    try:
        key = pa.Kutil(network=Settings.network, from_wif=wif_key).privkey
    except ValueError:
        raise ei.PacliInputDataError("Invalid or non-wallet address.")
        return

    ke.set_key("key", key) # Note that this function isn't present in the standard pacli keystore.
    Settings.key = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(k.load_key()))

    if not quiet:
        return Settings.key.address

def show_stored_address(label: str, network_name: str=Settings.network, keyring: bool=False, noprefix: bool=False, raise_if_invalid_label: bool=False, pubkey: bool=False, privkey: bool=False, wif: bool=False, legacy: bool=False):
    # Safer mode for show_stored_key.
    if keyring is True:
        return ke.show_stored_key(str(label), network_name=network_name, noprefix=noprefix, pubkey=pubkey, privkey=privkey, wif=wif, raise_if_invalid_label=raise_if_invalid_label)
    elif pubkey or privkey or wif:
        print("--privkey, --wif and --pubkey are only supported when using --keyring.")
    else:
        return get_address(str(label), network_name=network_name, noprefix=noprefix)

def process_address(addr_string: str, keyring: bool=False, try_alternative: bool=False, network_name: str=Settings.network) -> str:
    """Allows to use a label or an address; you'll get an address back."""
    # TODO it is not clear if the branch with try_alternative is still needed. For now it's set to false.
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
        raise ei.PacliInputDataError("No valid address string or non-existing label in the {}.".format(msg_keyring))
    return result

def show_label(address: str, set_main: bool=False, keyring: bool=False) -> dict:
    if keyring:
        label = ke.show_label(address)

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

def set_label(label: str, address: str, network_name: str=Settings.network, set_main: bool=False, modify: bool=False, keyring: bool=False):

    if keyring:
        ke.set_new_key(label=str(label), new_address=address, modify=modify, network_name=Settings.network)
    else:
        store_address(str(label), address=address, network_name=network_name, modify=modify)

    if set_main:
        return set_main_key(str(label), keyring=keyring)

def store_address(label: str, network_name: str=Settings.network, address: str=None, full: bool=False, modify: bool=False, replace: bool=False, to_wallet: bool=False):
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

    ce.write_item(category="address", key=ext_label, value=address, modify=modify, network_name=network_name, replace=replace)

    if to_wallet is True:
        ke.import_key_to_wallet("keyring_addresses", ext_label[len(network_name + "_"):])


def get_address(label: str, network_name: str=Settings.network, noprefix: bool=False) -> str:
    ext_label = label if noprefix else network_name + "_" + label
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
        ce.delete("address", label, now=now)


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

def get_labels_and_addresses(prefix: str=Settings.network, exclude: list=[], include_only: list=[], keyring: bool=False, named: bool=False, empty: bool=False, mark_duplicates: bool=False) -> dict:
    """Returns a dict of all labels and addresses which were stored.
       Addresses without label are not included if "named" is True."""

    if not keyring:
        result = ce.get_config()["address"]
        if include_only:
            result = {k : result[k] for k in result if result[k] in include_only}

    else:
        result = {}

        keyring_labels = ke.get_labels_from_keyring(prefix)

        for label in keyring_labels:
            address = show_stored_address(label=label, noprefix=True, keyring=True)
            label = label[4:] # wipes key_ out.
            result.update({label : address})

    if mark_duplicates:
       result2 = {}
       for l, a in result.items():
           if a in result2.values():
               l = l + "[D]"
           result2.update({l : a})
       result = result2

    if not named:
        counter = 0
        if include_only:
            wallet_addresses = set(include_only)
        else:
            wallet_addresses = eu.get_wallet_address_set(empty=empty)

        if exclude:
            wallet_addresses -= set(exclude)

        for address in wallet_addresses:
            if address not in result.values():
                if empty is False:
                    if provider.getbalance(address) == 0:
                        continue
                label = "{}_(unlabeled{})".format(prefix, str(counter))

                result.update({ label : address })
                counter += 1

    return result


def store_addresses_from_keyring(network_name: str=Settings.network, replace: bool=False, quiet: bool=False, debug: bool=False) -> None:
    """Stores all labels/addresses stored in the keyring in the extended config file."""
    if not quiet:
        print("Storing all addresses of network", network_name, "from keyring into extended config file.")
        print("The config file will NOT store private keys. It only allows faster access to addresses.")
    keyring_labels = ke.get_labels_from_keyring(network_name)
    if debug:
        print("Labels (with prefixes) retrieved from keyring:", keyring_labels)

    for full_label in keyring_labels:
        try:
            store_address(full_label, full=True, replace=replace, to_wallet=True)
        except ei.ValueExistsError:
            if not quiet:
                print("Label {} already stored.".format("_".join(full_label.split("_")[2:])))
            continue


# Transaction-related tools


def get_address_transactions(addr_string: str=None, sent: bool=False, received: bool=False, advanced: bool=False, keyring: bool=False, include_p2th: bool=False, include_coinbase: bool=False, sort: bool=False, wallet: bool=False, raw: bool=False, debug: bool=False) -> list:
    """Returns all transactions sent to or from a specific address, or of the whole wallet."""
    # TODO recheck all modes: with/without address, wallet, sent/received

    if not wallet and not raw:
        address = process_address(addr_string, keyring=keyring, try_alternative=False)
        if not address:
            raise ei.PacliInputDataError("You must provide either a valid address or a valid label.")
    else:
        address = None

    all_txes = True if (not sent) and (not received) else False
    if wallet:
        wallet_addresses = eu.get_wallet_address_set(empty=True)

    if debug:
        print("Get wallet transactions ...")
    if include_p2th:
        wallet_txes = eu.get_wallet_transactions(debug=debug)
        excluded_addresses = []

    else: # normally exclude p2th accounts
        p2th_accounts = eu.get_p2th(accounts=True)
        if wallet:
            p2th_addresses = set(eu.get_p2th())
            wallet_addresses = wallet_addresses - p2th_addresses
        if debug:
            print("Excluding P2TH accounts", p2th_accounts)
            if wallet:
                print("Wallet addresses", wallet_addresses)
        wallet_txes = eu.get_wallet_transactions(debug=debug, exclude=p2th_accounts)

    if raw: # TODO: mainly debugging mode, maybe later remove again, or return the set (see below).
        return wallet_txes

    unique_txes = list(set([(t["txid"], t["category"]) for t in wallet_txes]))
    #if wallet:
    #    unique_txes = list(set([(t["txid"], t["category"]) for t in wallet_txes]))
    #else:
    #    unique_txes = list(set([(t["txid"], None) for t in wallet_txes])) # if an address is given, we can use the fastest mode.
    if debug:
        print("Sorting ...")

    unique_txes.sort(key=lambda x: x[0], reverse=True) # should be: send, receive, generate

    if debug:
        print("Sorting finished.\nPreprocessing transaction list ...")

    # preprocessing step added
    txes = {}
    if sent or (received and not sent):
        cats = ["send"] if sent is True else ["receive", "generate", "immature"]
    elif include_coinbase is True:
        cats = ["send", "receive", "generate", "immature"]
    else:
        cats = ["send", "receive"]

    oldtxid = None
    for txid, category in unique_txes:
        # deletes txes which aren't in the required categories
        if (oldtxid not in (None, txid)) and set(cats).isdisjoint(txes[oldtxid]):
            if debug:
                print("Ignoring tx {}. Cats {} not matching {}.".format(oldtxid, txes[oldtxid], cats))
            del txes[oldtxid]

        if txid not in txes.keys():
            if debug:
                print("New tx", txid)
            txes.update({ txid : [category]})
        else:
            if category not in txes[txid]:
                if debug:
                    print("Adding category {} to tx {}".format(category, txid))
                txes[txid].append(category)
            else:
                if debug:
                    print("Ignoring category {} to tx {}, already existing in: {}".format(category, txid, txes["txid"]))
        oldtxid = txid

    if debug:
       print(len(txes), "wallet transactions found.")
    result = []
    if debug:
        print("Preprocessing finished.\nChecking senders and receivers ...")

    for txid, categories in txes.items():

        tx = provider.getrawtransaction(txid, 1)
        txdict = None
        try:
            confs = tx["confirmations"]
        except KeyError:
            confs = 0
            if advanced: # more usable and needed for sorting
                tx.update({"confirmations" : 0})

        if debug:
            print("Categories of tx {}: {}".format(tx["txid"], categories))
            print("Checking if wallet or address has sent transaction {} ...".format(tx["txid"]), end="")

        if ("send" in categories) and ((all_txes or sent) or (received and ("receive" in categories))):

            try:
                senders = bx.find_tx_senders(tx)
            except KeyError: # coinbase txes should not be canceled here as they should give []
                if debug:
                    print("Transaction aborted.")
                continue

            if debug:
                print("True.")

            value_sent = 0

            for sender_dict in senders:
                if (wallet and not set(sender_dict["sender"]).isdisjoint(wallet_addresses)) or (address in sender_dict["sender"]):
                    if not wallet and debug:
                        print("Address detected as sender in transaction:", tx["txid"])
                    value_sent += sender_dict["value"]

                    if txdict is None:
                        txdict = tx if advanced else {"txid" : tx["txid"], "type": ["send"], "value_sent" : value_sent, "confirmations": confs}
                        if advanced:
                            break
                    else:
                        txdict.update({"value_sent" : value_sent})

        else:
            if debug:
               print("False.")

        if debug:
            print("Checking if address or wallet is a receiver of transaction: {} ... ".format(tx["txid"]), end="")

        if ("receive" in categories or "generate" in categories or "immature" in categories) and ((all_txes or received) or (sent and ("send" in categories))):

            try:
                outputs = tx["vout"]
            except KeyError:
                if debug:
                    print("WARNING: Invalid transaction. TXID:", tx.get("txid"))
                continue
            if debug:
                print("True.")

            value_received = 0

            for output in outputs:
                out_addresses = output["scriptPubKey"].get("addresses")
                if not out_addresses: # None or []
                    continue

                if (wallet and (include_p2th or not set(out_addresses).isdisjoint(wallet_addresses))) or (address in out_addresses):

                    value_received += output["value"]

            if value_received > 0:
                if txdict is not None:
                    if not advanced:
                        txdict.update({"type" : ["send", "receive"]})
                        txdict.update({"value_received" : value_received})
                else:
                    txdict = tx if advanced else {"txid" : tx["txid"], "type" : ["receive"], "value_received": value_received, "confirmations": confs}

            if debug and not wallet:
                print("Address detected as receiver in transaction: {}. Received value in this output: {}".format(tx["txid"], output["value"]))

        else:
            if debug:
                print("False.")

        if txdict is not None:
            result.append(txdict)

    if sort:
        if debug:
            print("Sorting result by confirmations ...")
        result.sort(key=lambda x: x["confirmations"])

    return result
