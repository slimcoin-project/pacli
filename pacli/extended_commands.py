from prettyprinter import cpprint as pprint
import pypeerassets as pa
import pacli.keystore as k
import pacli.keystore_extended as ke
import pacli.extended_interface as ei
import pacli.extended_utils as eu
import pacli.config_extended as ce
import pacli.extended_constants as c
import pacli.blockexp_utils as bu
from pypeerassets.pautils import exponent_to_amount
from pacli.config import Settings
from pacli.provider import provider

# main functions

def get_labels_and_addresses(prefix: str=Settings.network,
                             exclude: list=[],
                             excluded_accounts: list=[],
                             include_only: list=[],
                             include: list=[],
                             access_wallet: str=None,
                             keyring: bool=False,
                             named: bool=False,
                             wallet_only: bool=True,
                             empty: bool=False,
                             mark_duplicates: bool=False,
                             labels: bool=False,
                             full_labels: bool=False,
                             no_labels: bool=False,
                             balances: bool=False,
                             network: bool=False,
                             debug: bool=False) -> list:
    """Returns a dict of all labels and addresses which were stored.
       Addresses without label are not included if "named" is True."""
       # This version is better ordered and already prepares the dict for the address table.
       # NOTE: wallet_only excludes the named addresses which are not in the wallet.
       # note 2: empty parameter here only refers to coin balances, not token balances.

    result = []
    addresses = []

    if no_labels is True:
        pass
    elif keyring is False:
        if full_labels or labels:
            # this returns a list of simple full_label:address dicts
            result = ce.list("address", prefix=prefix, quiet=True, return_list=True)
        else:
            result = ce.list("address", prefix=prefix, quiet=True, address_list=True)
    else:
        try:
            keyring_labels = ke.get_labels_from_keyring(prefix)
        except ImportError:
            raise ei.PacliInputDataError("This and some other keyring features are not supported without 'secretstorage'.")

        for label in keyring_labels:
            label = label[4:] # wipes key_ out.
            label = label if full_labels is True else ke.format_label(label)
            if labels or full_labels:
                result.append(label)
            else:
                address = show_stored_address(label=label, keyring=True) # noprefix=True,
                if include_only and (address not in include_only):
                    continue
                result.append({"label" : label, "address" : address, "network" : prefix})

    if debug:
        print(len(result), "named addresses found.")

    if labels or full_labels:
        if labels:
            items = [(i.replace(prefix + "_", ""), entry[i]) for entry in result for i in entry]
        elif full_labels:
            items = [(i, entry[i]) for entry in result for i in entry]
        items.sort()
        return items

    if include_only:
        result = [item for item in result if item["address"] in include_only]

    if wallet_only:
        result = [i for i in result if eu.is_mine(i["address"])]

    if mark_duplicates:
       addresses = []
       result2 = []
       for item in result:
           if item["address"] in addresses:
               label = item["label"]
               item.update({"label" : label + "[D]"})
           result2.append(item)
           addresses.append(item["address"])
       result = result2

    if not named:
        # labeled_addresses = [i["address"] for i in result]
        labeled_addresses = {i["address"] : i for i in result}
        #if wallet_only:
        #    # result = [] # resets the result list, so it will only be filled with named addresses which are part of the wallet
        #    result = [i for i in result if eu.is_mine(i["address"])]
        if include_only:
            wallet_addresses = set(include_only)
        elif access_wallet is not None:
            import pacli.db_utils as dbu
            datadir = access_wallet if type(access_wallet) == str else None
            wallet_addresses = dbu.get_addresses(datadir=datadir, debug=debug)
        else:
            wallet_addresses = eu.get_wallet_address_set(empty=empty, excluded_accounts=excluded_accounts)

        if include:
            wallet_addresses = wallet_addresses | set(include)
        if exclude:
            wallet_addresses -= set(exclude)

        if debug:
            print("{} wallet addresses processed: {}".format(len(wallet_addresses), wallet_addresses))

        for address in wallet_addresses:
            if address not in labeled_addresses:
                if empty is False and provider.getbalance(address) == 0:
                    continue

                result.append({"label" : "", "address" : address, "network" : prefix})
                if debug:
                    print("Unnamed address added:", address)

    if balances:
        result2 = []
        for item in result:
            try:
                balance = str(provider.getbalance(item["address"]))
            except TypeError:
                balance = "0"
                if debug is True:
                    print("No valid balance for address {} with label {}. Probably not a valid address.".format(address, label))

            if "." in balance:
                balance = balance.rstrip("0")
                balance = balance.rstrip(".")
            item.update({"balance" : balance})
            result2.append(item)
        result = result2

    return result


def get_address_transactions(addr_string: str=None,
                             sent: bool=False,
                             received: bool=False,
                             advanced: bool=False,
                             keyring: bool=False,
                             include_p2th: bool=False,
                             include_coinbase: bool=False,
                             sort: bool=False,
                             reverse_sort: bool=False,
                             unconfirmed: bool=True,
                             wallet: bool=False,
                             raw: bool=False,
                             txstruct: bool=False,
                             debug: bool=False) -> list:
    """Returns all transactions sent to or from a specific address, or of the whole wallet."""

    if not wallet and not raw:
        address = process_address(addr_string, keyring=keyring, try_alternative=False)
        if not address:
            raise ei.PacliInputDataError("You must provide either a valid address or a valid label.")
    else:
        address = None

    all_txes = True if (not sent) and (not received) else False
    if not include_p2th:
        p2th_dict = eu.get_p2th_dict()
    if wallet:
        wallet_addresses = eu.get_wallet_address_set(empty=True)
    if sort and txstruct:
        unconfirmed = False # we can only sort by blockheight if there is a value for confirmations.

    if debug:
        print("Get wallet transactions ...")

    if address is not None and not include_p2th:
        # special case: P2TH address is checked
        if address in p2th_dict.keys():
            include_p2th = True

    if include_p2th:
        wallet_txes = eu.get_wallet_transactions(debug=debug)
        excluded_addresses = []

    else: # normally exclude p2th accounts
        p2th_accounts = p2th_dict.values()
        if wallet:
            p2th_addresses = set(p2th_dict.keys())
            wallet_addresses = wallet_addresses - p2th_addresses
        if debug:
            print("Excluding P2TH accounts", p2th_accounts)
            if wallet:
                print("Wallet addresses", wallet_addresses)
        wallet_txes = eu.get_wallet_transactions(debug=debug, exclude=p2th_accounts)

    if raw: # TODO: mainly debugging mode, maybe later remove again, or return the set (see below).
        return wallet_txes

    unique_txes = list(set([(t["txid"], t["category"]) for t in wallet_txes]))
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
                print("New tx", txid, "with category", category)
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
        if txstruct:
            formatted_tx = bu.get_tx_structure(tx=tx, human_readable=False, add_txid=True)
        elif advanced:
            formatted_tx = tx
        try:
            confs = tx["confirmations"]
        except KeyError:
            if unconfirmed is False:
                continue
            confs = 0
            if advanced: # more usable and needed for sorting
                tx.update({"confirmations" : 0})

        if debug:
            print("Categories of tx {}: {}".format(tx["txid"], categories))

        # checking sender(s) and sent value(s) (also for transactions in the "receive" category).
        if ("send" in categories) and ((all_txes or sent) or (received and ("receive" in categories))):

            if debug:
                print("Checking if wallet or address has sent transaction {} ...".format(tx["txid"]), end="")

            try:
                senders = bu.find_tx_senders(tx)
            except KeyError: # coinbase txes should not be canceled here as they should give []
                if debug:
                    print("Transaction aborted.")
                continue

            value_sent = 0

            for sender_dict in senders:
                if (wallet and not set(sender_dict["sender"]).isdisjoint(wallet_addresses)) or (address in sender_dict["sender"]):

                    value_sent += sender_dict["value"]

                    if txdict is None:
                        if advanced or txstruct:
                            txdict = formatted_tx
                        else:
                            txdict = {"txid" : tx["txid"], "type": ["send"], "value_sent" : value_sent, "confirmations": confs}
                        if advanced:
                            break
                    else:
                        txdict.update({"value_sent" : value_sent})

            if debug:
                if value_sent > 0:
                    print("True.")
                else:
                    print("False.")

        if ("receive" in categories or "generate" in categories or "immature" in categories) and ((all_txes or received) or (sent and ("send" in categories))):

            if debug:
                print("Checking if address or wallet is a receiver of transaction: {} ... ".format(tx["txid"]), end="")

            if "send" in categories:
                categories.remove("send")

            try:
                outputs = tx["vout"]
            except KeyError:
                if debug:
                    print("WARNING: Invalid transaction. TXID:", tx.get("txid"))
                continue

            value_received = 0

            for output in outputs:
                out_addresses = output["scriptPubKey"].get("addresses")
                if not out_addresses: # None or []
                    continue

                if (wallet and (include_p2th or not set(out_addresses).isdisjoint(wallet_addresses))) or (address in out_addresses):

                    value_received += output["value"]

            # TODO: if receiver or not depends on value.
            # This could be problematic in the future if 0-value-txes are allowed.
            if value_received > 0:
                if txdict is not None:
                    if not advanced and not txstruct and "type" in txdict:
                        # print(txdict["type"], categories)
                        txdict["type"] += categories
                        txdict.update({"value_received" : value_received})
                else:
                    if advanced or txstruct:
                        txdict = formatted_tx
                    else:
                        txdict = {"txid" : tx["txid"], "type" : categories, "value_received": value_received, "confirmations": confs}

                if debug:
                    print("True.")
                    if not wallet:
                        print("Address detected as receiver in transaction: {}. Received value in this output: {}".format(tx["txid"], output["value"]))


            else:
                if debug:
                    print("False.")

        if txdict is not None:
            result.append(txdict)

    if sort:
        confpar = "blockheight" if txstruct else "confirmations"
        rev = not reverse_sort if txstruct else reverse_sort
        if debug:
            print("Sorting result by confirmations or block height ...")
        result.sort(key=lambda x: x[confpar], reverse=rev)

    return result


def show_claims(deck_str: str,
                address: str=None,
                donation_txid: str=None,
                claim_tx: str=None,
                wallet: bool=False,
                wallet_and_named: bool=False,
                full: bool=False,
                param: str=None,
                basic: bool=False,
                quiet: bool=False,
                debug: bool=False):
    '''Shows all valid claim transactions for a deck, with rewards and TXIDs of tracked transactions enabling them.'''
    # NOTE: added new "basic" mode, like quiet with simplified dict, but with printouts.

    if (donation_txid and not eu.is_possible_txid(donation_txid) or
        claim_tx and not eu.is_possible_txid(claim_tx)):
        raise ei.PacliInputDataError("Invalid transaction ID.")

    if deck_str is None:
        raise ei.PacliInputDataError("No deck given, for --claim options the token/deck is mandatory.")

    if quiet or basic:
        param_names = {"txid" : "txid", "amount": "amount", "sender" : "sender", "receiver" : "receiver", "blocknum" : "blockheight"}
    else:
        param_names = {"txid" : "Claim transaction ID", "amount": "Token amount(s)", "sender" : "Sender", "receiver" : "Receiver(s)", "blocknum" : "Block height"}

    deck = eu.search_for_stored_tx_label("deck", deck_str, quiet=quiet, check_initialized=True, return_deck=True, abort_uninitialized=True)
    # deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

    if "at_type" not in deck.__dict__:
        raise ei.PacliInputDataError("{} is not a DT/dPoD or AT/PoB token.".format(deck.id))

    if deck.at_type == 2:
        if deck.at_address == c.BURN_ADDRESS[provider.network]:
            dtx_param = "burn_tx" if (quiet or basic) else "Burn transaction"
            token_type = "PoB"
        else:
            # AssertionError gets thrown by a non-PoB AT token, AttributeError by dPoD token
            # param_names.update({"donation_txid" : "Gateway transaction"})
            dtx_param = "gateway_tx" if (quiet or basic) else "Gateway transaction"
            token_type = "AT"
    elif deck.at_type == 1:
        dtx_param = "donation_tx" if (quiet or basic) else "Donation transaction"
        token_type = "dPoD"
    if debug:
        #    token_type = "dPoD" if type(e) == AttributeError else "AT"
        print("{} token detected.".format(token_type))

    param_names.update({"donation_txid" : dtx_param})

    if wallet:
        p2th_dict = eu.get_p2th_dict()
        # addresses = get_labels_and_addresses(empty=True, exclude=p2th_dict.keys(), excluded_accounts=p2th_dict.values(), debug=debug)
        # wallet_senders = set([a["address"] for a in addresses])
        # NOTE: changed method to restrict result to wallet addresses, now ismine and P2TH exclusion is used.
        raw_claims = eu.get_valid_cardissues(deck, only_wallet=True, excluded_senders=p2th_dict.keys(), debug=debug)
    else:
        raw_claims = eu.get_valid_cardissues(deck, sender=address, debug=debug)

    if claim_tx is None:
        claim_txids = set([c.txid for c in raw_claims])
    else:
        claim_txids = [claim_tx]
    if debug and not claim_tx:
        print("{} claim transactions found.".format(len(claim_txids)))
    claims = []

    for claim_txid in claim_txids:

        bundle = [c for c in raw_claims if c.txid == claim_txid]
        if not bundle:
            continue
        claim = bundle[0]
        if donation_txid is not None and claim.donation_txid != donation_txid:
            continue

        if len(bundle) > 1:
            for b in bundle[1:]:
                claim.amount.append(b.amount[0])
                claim.receiver.append(b.receiver[0])
        claims.append(claim)

    if full:
        result = [c.__dict__ for c in claims]
    elif param:
        # TODO: this now is unnecessary when using the transaction list command
        # re-check other commands
        try:
            result = [{ claim.txid : claim.__dict__.get(param) } for claim in claims]
        except KeyError:
            raise ei.PacliInputDataError("Parameter does not exist in the JSON output of this mode, or you haven't entered a parameter. You have to enter the parameter after --param/-p.")
    else:
        result = [{param_names["txid"] : claim.txid,
                   param_names["donation_txid"] : claim.donation_txid,
                   param_names["amount"] : [exponent_to_amount(a, claim.number_of_decimals) for a in claim.amount],
                   param_names["sender"] : claim.sender,
                   param_names["receiver"] : claim.receiver,
                   param_names["blocknum"] : claim.blocknum} for claim in claims]

    if (not quiet) and len(result) == 0:
        print("No claim transactions found.")

    return result

# address tools

def fresh_address(label: str, set_main: bool=False, backup: str=None, check_usage: bool=False, keyring: bool=False, legacy: bool=False, quiet: bool=False):

    label = str(label)
    addr_txes = 1

    while addr_txes:
        address = provider.getnewaddress()

        if check_usage:
            if not quiet:
                print("Checking usage of new address {} (can take some minutes) ...".format(address))
            addr_txes = len(get_address_transactions(addr_string=address, include_coinbase=True))
            if not quiet:
                if addr_txes > 0 :
                    print("Address was already used with {} transactions. Trying new address.".format(addr_txes))
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

    wif_key = provider.dumpprivkey(address)

    try:
        key = pa.Kutil(network=Settings.network, from_wif=wif_key).privkey
    except ValueError as e:
        if "Invalid wif length" in str(e):
            raise ei.PacliDataError("Address does not exist or your {} client's wallet is locked. Changing the main address wasn't possible, however if you were running this command to create a fresh address with a new label the address was created and associated with the label of your choice. If your wallet is locked with a passphrase, you need to unlock it before you change the main address.".format(Settings.network.upper()))
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

def search_change_addresses(known_addresses: list, wallet_txes: list=None, balances: bool=False, debug: bool=False) -> list:
    """Searches all wallet transactions for unknown change addresses."""
    # note: needs advanced mode for wallet txes (complete getrawtransaction tx dict)
    if not wallet_txes:
        wallet_txes = get_address_transactions(wallet=True, advanced=True, debug=debug)
    known_addr_list = [a["address"] for a in known_addresses]
    unknown_wallet_addresses = []
    new_addr_list = []
    network = Settings.network

    for tx in wallet_txes:
        if debug:
            print("CHANGE ADDRESS SEARCH: checking tx:", tx["txid"])
        for output in tx["vout"]:
            try:
                addresses = output["scriptPubKey"]["addresses"]
            except KeyError:
                continue
            for address in addresses:
                if address not in known_addr_list and address not in new_addr_list:
                    validation = provider.validateaddress(address)
                    if validation.get("ismine") == True:
                        address_item = {"label" : "", "address" : address, "network" : network}
                        if balances is True:
                            balance = retrieve_balance(address, debug=debug)
                            address_item.update({"balance" : balance})
                        unknown_wallet_addresses.append(address_item)
                        new_addr_list.append(address)
                        if debug:
                            print("Found and added unknown address:", address)
                    elif debug:
                        print("Ignored non-wallet address:", address)
    return unknown_wallet_addresses

def retrieve_balance(address: str, debug: bool=False) -> str:
    # currently a string is returned, to be converted into Decimal if needed.
    try:
        balance = str(provider.getbalance(address))
    except TypeError:
        balance = "0"
        if debug is True:
            print("No valid balance for address {}. Probably not a valid address.".format(address))
    if balance != "0":
        balance = balance.rstrip("0")
    return balance

def utxo_check(utxodata: list, access_wallet: str=None, quiet: bool=False, debug: bool=False):

    if access_wallet is not None:
        import pacli.db_utils as dbu
        datadir = access_wallet if type(access_wallet) == str else None

    for utxo in utxodata:
        spenttx = 0
        txid, vout = utxo[:]
        utxostr = "{}:{}".format(txid, vout)
        output = bu.get_utxo_from_data(utxo, debug=debug)
        addresses = bu.get_utxo_addresses(output)

        for address in addresses:
            if not quiet:
                print("Checking address {}, which received UTXO {} ...".format(address, utxostr))
                if not eu.is_mine(address):
                    ei.print_red("Warning: Address is not part of the current wallet. Results are likely to be incomplete.")

            if access_wallet is not None:
                txes = dbu.get_all_transactions(address=address, datadir=datadir, advanced=True, debug=debug)
            else:
                txes = get_address_transactions(addr_string=address, advanced=True, include_p2th=True, debug=debug)
            if not txes:
                continue
            elif not quiet:
                print("Searching utxo in", len(txes), "transactions ...")
            for tx in txes:
                if not quiet:
                    print("Searching TX:", tx.get("txid"))
                if bu.utxo_in_tx(utxo, tx):
                    if not quiet:
                        pprint("Transaction {} spends UTXO: {}".format(tx["txid"], utxostr))
                    else:
                        print(tx["txid"])
                    spenttx += 1
                    break
        if spenttx == 0:
            print("UTXO {} not found. Probably unspent.".format(utxostr))
    return





