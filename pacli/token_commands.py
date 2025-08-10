import pypeerassets as pa

from prettyprinter import cpprint as pprint
from decimal import Decimal
from pacli.provider import provider
from pacli.config import Settings
from pacli.tui import print_card_list
import pacli.extended_constants as c
import pacli.extended_utils as eu
import pacli.extended_interface as ei
import pacli.extended_commands as ec
import pacli.config_extended as ce
from pypeerassets.at.dt_misc_utils import list_decks_by_at_type

def get_default_tokens():
    decks = [pa.find_deck(provider, c.DEFAULT_POB_DECK[Settings.network], Settings.deck_version, Settings.production),
             pa.find_deck(provider, c.DEFAULT_POD_DECK[Settings.network], Settings.deck_version, Settings.production)]
    return decks


def all_balances(address: str=Settings.key.address,
                 exclude: list=[],
                 excluded_accounts: list=[],
                 include: list=[],
                 include_only: list=[],
                 decks: list=None,
                 wallet: bool=False,
                 keyring: bool=False,
                 no_labels: bool=False,
                 only_labels: bool=False,
                 only_tokens: bool=False,
                 no_tokens: bool=False,
                 empty: bool=False,
                 advanced: bool=False,
                 named: bool=False,
                 named_and_nonempty: bool=False,
                 wallet_only: bool=False,
                 add_p2th_account: bool=False,
                 p2th_dict: dict=None,
                 deck_type: int=None,
                 quiet: bool=False,
                 access_wallet: bool=False,
                 debug: bool=False):
    """Shows all token/card balances on this address.
    --wallet flag allows to show all balances of addresses
    which are part of the wallet."""
    # NOTE: decks needs to be always the list of all decks, not only the initialized decks or another subset.
    # NOTE: added named_and_nonempty parameter: includes always all named addresses, and also those which have either coins or tokens on it.

    if no_tokens:
        decks = []
    elif advanced is not True:
        # the quick mode displays only default PoB and PoD decks
        decks = get_default_tokens()
    elif deck_type is not None:
        if debug:
            print("Retrieving deck list ...")
        # Note: address list -w and -e will not trigger this branch, so the decks aren't searched twice.
        decks = list_decks_by_at_type(provider, deck_type)
    elif decks is None:
        if debug:
            print("Retrieving deck list ...")

        decks = pa.find_all_valid_decks(provider, Settings.deck_version,
                                        Settings.production)
    if advanced is True and not no_tokens:
        decks = eu.get_initialized_decks(decks, debug=debug)

    if debug:
        print("Retrieving addresses and/or labels ...")
    balances = False if only_tokens is True else True
    if wallet is True: # and no_labels is False:
        if debug:
            print("Parameters for address selection:")
            print("named:", named, "named_and_nonempty:", named_and_nonempty, "empty:", empty, "wallet_only:", wallet_only, "access wallet", access_wallet)
            print("exclude:", exclude)
            print("excluded accounts:", excluded_accounts)
            print("include:", include)
            print("include_only", include_only)
        addresses = ec.get_labels_and_addresses(access_wallet=access_wallet, prefix=Settings.network, keyring=keyring, named=named, empty=True, exclude=exclude, excluded_accounts=excluded_accounts, include=include, include_only=include_only, wallet_only=wallet_only, no_labels=no_labels, balances=balances, debug=debug)
    else:
        addresses = ec.get_labels_and_addresses(access_wallet=access_wallet, prefix=Settings.network, keyring=keyring, named=named, empty=True, include_only=[address], no_labels=no_labels, balances=balances, debug=debug)

    # NOTE: default view needs no deck labels
    # NOTE2: Quiet mode doesn't show labels.
    deck_labels = None
    if not no_labels and not quiet and not no_tokens:
        if advanced is True:
            deck_labels = ce.get_config()["deck"]
        elif wallet is False:
            try:
                deck_labels = c.default_token_labels(Settings.network)
            except KeyError:
                raise ei.PacliInputDataError("Default PoB and dPoD tokens are not supported on network '{}'.".format(Settings.network))

    for deck in decks:
        if (no_labels or quiet) or (not advanced) or (deck.id not in deck_labels.values()):
            deck_identifier = deck.id
        else:
            deck_label = [d for d in deck_labels if deck_labels[d] == deck.id][0]
            if only_labels:
                deck_identifier = deck_label
            else:
                deck_identifier = "{} ({})".format(deck_label, deck.id)
        if debug:
            print("Checking deck:", deck.id)
        try:
            eu.get_wallet_token_balances(deck, identifier=deck_identifier, include_named=True, address_dicts=addresses, no_labels=no_labels, debug=debug)
            #if debug:
            #    print("Address balances added:", addresses)

        except KeyError:
            if debug:
                print("Warning: Omitting deck with initialization problem:", deck.id)
            continue

    if not empty:
        non_empty_addresses = []
        for address in addresses:
            if named_and_nonempty and address.get("label", ""):
                if debug:
                    print(address["address"], "kept. Label:", address.get("label"))
                non_empty_addresses.append(address)
                continue # if named_and_nonempty is set, no empty named addresses will be deleted from output.
            if address.get("balance", "0") == "0":
                if debug:
                    print("Checking empty address:", address)
                if not address.get("tokens", None):
                    if debug:
                        print("Deleted empty address without tokens.")
                    continue
                else:
                    if debug:
                        print("Kept empty address with tokens.")
            else:
                if debug:
                    print("Kept address with coin balance.")
            non_empty_addresses.append(address)
        addresses = non_empty_addresses


    if len(addresses) > 1:
        addresses = eu.sort_address_items(addresses, debug=debug)

    if quiet:
        print(addresses)
    elif (advanced is True) or (not wallet):
        for item in addresses:
            ei.print_address_balances(item)
    elif no_tokens:
        if add_p2th_account == True:
            for item in addresses:
                item.update({"account" : p2th_dict.get(item["address"])})

        ei.print_address_list(addresses, p2th=add_p2th_account)
    else:
        ei.print_default_balances_list(addresses, decks, network_name=Settings.network, only_tokens=only_tokens)

def single_balance(deck: str, address: str=Settings.key.address, wallet: bool=False, keyring: bool=False, no_labels: bool=False, quiet: bool=False):
    """Shows the balance of a single token (deck) on the current main address or another address.
    --wallet flag allows to show all balances of addresses
    which are part of the wallet."""

    deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, quiet=quiet) if deck else None
    deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

    if wallet:
        # wallet_addresses = list(eu.get_wallet_address_set(empty=True, include_named=True)) # TODO: deactivated, wallet_addresses is currently not used.
        addresses = ec.get_labels_and_addresses(keyring=keyring)
        balances = eu.get_wallet_token_balances(deck, include_named=True)

        if quiet:
            print(balances)
        elif no_labels:
            pprint(balances)
        else:
            addresses_with_tokens = ei.add_token_balances(addresses, deck.id, balances, return_present=True)
            pprint([{a["addr_identifier"] : a["tokens"][deck.id]} for a in addresses_with_tokens])
            #for a in addresses:
            #    if "tokens" in a and deck.id in a["tokens"]:
            #        pprint({ a["addr_identifier"] : a["tokens"][deck.id] })
            return
    else:
        balance = eu.get_address_token_balance(deck, address)

        if quiet:
            print({address : balance})
        else:
            pprint({address : balance})

