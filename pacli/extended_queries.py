# bundles most functions acceding directly to queries like listtransactions, listunspent etc.
# queries involving PeerAssets features are in extended_token_queries.py

from pacli.provider import provider
from pacli.config import Settings


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
            wallet_addresses = get_wallet_address_set(empty=empty, excluded_accounts=excluded_accounts)

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

    # preprocessing step added
    txes = {}
    if (sent and not received) or (received and not sent):
        cats = ["send"] if sent is True else ["receive"]
    else:
        cats = ["send", "receive"]
    if include_coinbase is True:
        cats += ["generate", "immature"]
    if debug:
        print("Categories of txes to query:", cats)

    if not wallet and not raw:
        address = process_address(addr_string, keyring=keyring, try_alternative=False)
        if not address:
            raise ei.PacliInputDataError("You must provide either a valid address or a valid label.")
    else:
        address = None

    all_txes = True if (not sent) and (not received) else False
    if not include_p2th:
        if debug:
            print("Getting P2TH addresses to be excluded ...")
        p2th_dict = eu.get_p2th_dict()
    if wallet:
        wallet_addresses = get_wallet_address_set(empty=True)
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
                        if txstruct:
                            txdict = bu.get_tx_structure(tx=tx, human_readable=False, add_txid=True)
                        elif advanced:
                            txdict = tx
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

                # P2TH addresses don't have to be added to out_addresses
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
                    if txstruct:
                        txdict = bu.get_tx_structure(tx=tx, human_readable=False, add_txid=True)
                    elif advanced:
                        txdict = tx
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


def get_wallet_transactions(fburntx: bool=False, exclude: list=None, debug: bool=False):
    """Gets all transactions stored in the wallet."""

    raw_txes = []
    all_accounts = list(provider.listaccounts().keys())
    # all_accounts = [a for a in list(provider.listaccounts().keys()) if is_possible_address(a) == False]
    # print(all_accounts)
    all_accounts.reverse() # retrieve relevant accounts first, then the rest of the txes in "" account
    for account in all_accounts:
        if exclude and (account in exclude):
            if debug:
                print("Account excluded:", account)
            continue
        start = 0
        while True:
            new_txes = provider.listtransactions(many=500, since=start, account=account) # option fBurnTx=burntxes doesn't work as expected # removed fBurnTx=fburntx,
            if debug:
                print("{} new transactions found in account {}.".format(len(new_txes), account))
            raw_txes += new_txes
            #if len(new_txes) == 999:
            #    start += 999
            # TODO: the new variant should be more reliable, for example if there is an error with one transaction
            if len(new_txes) == 0:
                break
            else:
                start += len(new_txes)

    return raw_txes


def get_wallet_address_set(empty: bool=False, include_named: bool=False, use_accounts: bool=False, excluded_accounts: list=None) -> set:
    """Returns a set (without duplicates) of all addresses which have received coins eventually, in the own wallet."""
    # listreceivedbyaddress seems to be unreliable but is around 35% faster.

    if use_accounts is True:
        addresses = []
        accounts = provider.listaccounts(0)
        for account in accounts:
            if excluded_accounts is not None and account in excluded_accounts:
                continue
            addresses += provider.getaddressesbyaccount(account)
    else:
        addr_entries = provider.listreceivedbyaddress(0, empty)
        addresses = [e["address"] for e in addr_entries]

    if include_named:
        named_addresses = ce.list("address", quiet=True).values()
        addresses += named_addresses

    return set(addresses)
