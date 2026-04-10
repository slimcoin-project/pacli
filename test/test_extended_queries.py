import pytest
from decimal import Decimal
import pacli.extended.queries as q
import pacli.extended.utils as eu
import pacli.extended.config as ce
from pacli.provider import provider
from pacli.config import Settings
from pypeerassets.networks import net_query

# Note: keyring is unsupported, won't be tested.

ADDR1 = ["mwuSYLvG9cVPiFR5W1mquxxYLfN1HK9B52", "mn9AffRiy8EFxkz3f8pdVFdUncnfu3A6fJ", "mqThr4L1aYnBXoz2xVKtYyQDP2RMtse7Zb", "mo3GueEE7Cymiaumn716z5JeG8QJkbpJPu"] # all valid, no duplicates
ADDR2 = ["mihDqYWMLpNS8kwXk88ZVcF61SzmJZD473", "mkfuTykT6anzsRjYH7Lktc2hFuTqcGpha7", "mu5kdgPoJJcYc2SL7tqy6QNNHSD7tyuE6b", "mihDqYWMLpNS8kwXk88ZVcF61SzmJZD473"] # 1 duplicate
ADDRINV = ["mmBwLVyqZWuUDuTpmmpzBvT41azKBevZhh", "mqGtiV8aTVXheBTX4W6pbbQbTFhBA5R5BN", "mfiuCJwyTWGNSthNWzRkPtHjMfSR64i6AQ", "mvxzWVnSZuoVBxgNqLw1VzdjgE1UBNU2ba"] # one invalid address, correct one is mvxzWVnSZuoVBxgNqLw1VzdjgE1UBNU2bv
ACCOUNTS = ["fb93cce7aceb9f7fda228bc0c0c2eca8c56c09c1d846a04bd6a59cae2a895974",
            "a2459e054ce0f600c90be458915af6bad36a6863a0ce0e33ab76086b514f765a",
            "a2459e054ce0f600c90be458915af6bad36a6863a0ce0e33ab76086b514f765aDONATION",
            "a2459e054ce0f600c90be458915af6bad36a6863a0ce0e33ab76086b514f765aLOCKING",
            "a2459e054ce0f600c90be458915af6bad36a6863a0ce0e33ab76086b514f765aPROPOSAL"]


@pytest.mark.parametrize(("labels", "full_labels"),
                          [(True, False),
                          (False, True)])
def test_get_labels_and_addresses_labels(labels, full_labels):

    result = q.get_labels_and_addresses(prefix=Settings.network,
                             exclude=[],
                             excluded_accounts=[],
                             include_only=[],
                             include=[],
                             access_wallet=None,
                             keyring=False,
                             named=False,
                             wallet_only=True,
                             empty=False,
                             mark_duplicates=False,
                             labels=labels,
                             full_labels=full_labels,
                             no_labels=False,
                             balances=False,
                             debug=False)

    assert type(result) == list
    assert len(result[0]) == 2
    assert type(result[0]) == tuple
    assert type(result[0][0]) == str
    if full_labels is True:
        assert result[0][0].startswith(Settings.network)
    assert sorted(result) == result # test sorting


# Note: the no_labels arg does not eliminate the label param from the dict.
# Note 2: the empty param is better tested without the prioritize named enabled.
@pytest.mark.parametrize(("balances", "no_labels", "len_result", "empty", "prio"),
                          [(False, False, 3, False, True),
                           (False, True, 3, False, True),
                           (True, False, 4, True, False),
                           (True, False, 4, False, False)])
def test_get_labels_and_addresses_all(balances, no_labels, len_result, empty, prio):

    result = q.get_labels_and_addresses(prefix=Settings.network,
                             exclude=[],
                             excluded_accounts=[],
                             include_only=[],
                             include=[],
                             access_wallet=None,
                             prioritize_named=prio,
                             keyring=False,
                             named=False,
                             wallet_only=True,
                             empty=empty,
                             mark_duplicates=False,
                             labels=False,
                             full_labels=False,
                             no_labels=no_labels,
                             balances=balances,
                             debug=False)

    assert type(result) == list
    assert len(result[0]) == len_result
    assert type(result[0]) == dict
    params = ["address", "network"]
    if balances:
        params.append("balance")
        b = []
        for item in result:
            test_addr = item["address"]
            balance = Decimal(str(item["balance"]))
            assert balance == Decimal(str(provider.getbalance(test_addr)))
            b.append(balance)
        if not empty:
            assert Decimal("0") not in set(b) # no empty balances allowed if empty is false

    if no_labels:
        label_set = set([item["label"] for item in result])
        assert label_set == set([""])
        # assert result[0]["label"] == ""
    for k in params:
        assert k in result[0] # each item is a dict
    # test wallet_only with eu.is_mine(address)!
    addresses = set([item["address"] for item in result])
    ismine = set([eu.is_mine(a) for a in addresses])
    assert False not in ismine

# Note: if the "excluded" address is named, the test will fail,
# as it is standard behaviour currently to include all named addresses (prioritize_named).
@pytest.mark.parametrize(("include_only", "exclude", "include", "has_invalid"),
                          [(ADDR1, ["mwuSYLvG9cVPiFR5W1mquxxYLfN1HK9B52"], [], False),
                           (ADDR2, [], ["mn9AffRiy8EFxkz3f8pdVFdUncnfu3A6fJ"], False),
                           (ADDRINV, ["AAAAA"], ["BBBBB"], True)])
def test_get_labels_and_addresses_include_exclude(include_only, exclude, include, has_invalid):

    result = q.get_labels_and_addresses(exclude=exclude,
                             prioritize_named=True,
                             include_only=include_only,
                             include=include,
                             access_wallet=None,
                             named=False,
                             wallet_only=False,
                             empty=True,
                             mark_duplicates=False,
                             balances=False)

    addresses = [item["address"] for item in result]
    if include_only and not has_invalid:
        assert set(addresses) == set(include_only) - set(exclude)
    for included in include:
        if (not include_only) or (included in include_only):
            assert included in addresses
    for excluded in exclude:
        assert excluded not in addresses

# as mark_duplicates only applies to named addresses, we test it only with the named parameter
# prioritize_named obviously only works with named set to False.
@pytest.mark.parametrize(("named", "mark_duplicates", "prioritize_named"),
                          [(True, True, False),
                           (True, False, False),
                           (False, False, True),
                           (False, False, False)])
def test_get_labels_and_addresses_named(named, mark_duplicates, prioritize_named):

    result = q.get_labels_and_addresses(prioritize_named=prioritize_named,
                             include_only=[],
                             named=named,
                             wallet_only=False,
                             empty=False,
                             mark_duplicates=mark_duplicates)
    if named:
        for item in result:
            assert item["label"] # will fail if label is '' or None
    if mark_duplicates:
        addresses = {}
        for item in result:
            address = item["address"]
            if address in addresses:
                addresses[address].append(item["label"])
            else:
                addresses.update({address : [item["label"]]})
        duplicates = [a for a in addresses.values() if len(a) > 1]
        for d in duplicates:
            marked = False
            for label in d:
                if "[D]" in label:
                    marked = True
                    break
            assert marked == True
    if prioritize_named: # checks if there's an empty address -> if it's named then the priority failed.
        for item in result:
            if provider.getbalance(item["address"]) == 0:
                assert item["label"]

# try to use some (wallet) addresses with balance here.
@pytest.mark.parametrize("address", ["mkfuTykT6anzsRjYH7Lktc2hFuTqcGpha7", "n4KxYDAQZ3s59DoRuVkyTU2MsUBsUAkpth", "mgC4E4fh4zkq4KiVF4PzX8692NwVMh4unG"])
def test_retrieve_balance(address):
    balance = q.retrieve_balance(address)
    assert type(balance) == str
    if balance != "0":
        assert balance[-1] != 0


# include_named should not be combined with "empty=False"
# because named addresses are allowed to be empty in the standard setting.
@pytest.mark.parametrize(("empty", "include_named"),
                          [(True, True),
                           (True, False),
                           (False, False)])
def test_get_wallet_address_set(empty, include_named):
    address_set = q.get_wallet_address_set(empty=empty,
                                           include_named=include_named,
                                           use_accounts=False)
    assert type(address_set) == set
    params = net_query(Settings.network)
    for a in address_set:
        assert type(a) == str
        assert a[0] in params.base58_prefixes.keys()
    if include_named:
        named_addresses = ce.list("address", quiet=True).values()
        for n in named_addresses:
            assert n in address_set

    if not empty: # we cannot really test if non-empty addresses are correctly found.
        # TODO: the getbalance command doesn't work the same way than the listaddressesbyaccount one.
        # listreceivedbyaddresses seems to be 0 only if the address was never used,
        # so addresses with 0 balance which were used are not seen here.
        # Skipping for now.
        pytest.skip()
        empty_addresses = [a for a in address_set if provider.getbalance(a) == 0]
        print(empty_addresses)
        assert len(empty_addresses) == 0


# make sure to initialize the decks used as excluded_accounts here!
@pytest.mark.parametrize(("include_named", "excluded_accounts"),
                          [(True, []),
                           (False, ACCOUNTS),
                           (True, ACCOUNTS)])
def test_get_wallet_address_set_accounts(include_named, excluded_accounts):
    address_set = q.get_wallet_address_set(empty=True,
                                           include_named=include_named,
                                           use_accounts=True,
                                           excluded_accounts=excluded_accounts)

    assert type(address_set) == set
    included_accounts = set(provider.listaccounts().keys()) - set(excluded_accounts)
    included_addresses = set([adr for acc in included_accounts for adr in provider.getaddressesbyaccount(acc)])
    if include_named:
        named_addresses = set(ce.list("address", quiet=True).values())
        included_addresses |= named_addresses
    for exc in excluded_accounts:
        for address in provider.getaddressesbyaccount(exc):
            if address not in included_addresses:
                assert address not in address_set


# this function is unsupported, will not be tested for now:
# def search_change_addresses(known_addresses: list, wallet_txes: list=None, balances: bool=False, debug: bool=False) -> list:


