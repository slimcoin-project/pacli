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


def all_balances(address: str=Settings.key.address, exclude: list=[], include_only: list=[], wallet: bool=False, keyring: bool=False, no_labels: bool=False, only_tokens: bool=False, advanced: bool=False, named: bool=False, only_labels: bool=False, deck_type: int=None, quiet: bool=False, empty: bool=False, debug: bool=False):
    """Shows all token/card balances on this address.
    --wallet flag allows to show all balances of addresses
    which are part of the wallet."""

    if debug:
        print("Retrieving deck list ...")
    if advanced is not True:
        # the quick mode displays only default PoB and PoD decks
        decks = get_default_tokens()
    elif deck_type is not None:
        decks = list_decks_by_at_type(provider, deck_type)
    else:
        decks = pa.find_all_valid_decks(provider, Settings.deck_version,
                                        Settings.production)
    if advanced is True:
        decks = eu.get_initialized_decks(decks, debug=debug)

    if debug:
        print("Retrieving addresses and/or labels ...")
    balances = False if only_tokens is True else True
    if wallet is True: # and no_labels is False:
        addresses = ec.get_labels_and_addresses(prefix=Settings.network, keyring=keyring, named=named, empty=empty, exclude=exclude, include_only=include_only, no_labels=no_labels, balances=balances, debug=debug)
    else:
        addresses = ec.get_labels_and_addresses(prefix=Settings.network, keyring=keyring, named=named, empty=empty, include_only=[address], no_labels=no_labels, balances=balances, debug=debug)
        #addresses = [{"address" : Settings.key.address}]
        #if not only_tokens:
        #    addresses[0].update({"balance" : provider.getbalance(address)})

    # NOTE: default view needs no deck labels
    # NOTE2: Quiet mode doesn't show labels.
    deck_labels = None
    if not no_labels and not quiet:
        if advanced is True:
            deck_labels = ce.get_config()["deck"]
        elif wallet is False:
            try:
                deck_labels = c.default_token_labels(Settings.network)
            except KeyError:
                raise ei.PacliInputDataError("Default PoB and dPoD tokens are not supported on network '{}'.".format(Settings.network))

    # address_list = [a["address"] for a in addresses]
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
            # token_balances = eu.get_wallet_token_balances(deck, include_named=True, addresses=address_list, debug=debug)
            eu.get_wallet_token_balances(deck, identifier=deck_identifier, include_named=True, address_dicts=addresses, no_labels=no_labels, debug=debug)
            # ei.add_token_balances(addresses, deck_identifier, token_balances, suppress_addresses=only_labels)
            # addr_balance = eu.get_address_token_balance(deck, address)

        except KeyError:
            if debug:
                print("Warning: Omitting deck with initialization problem:", deck.id)
            continue

        # if addr_balance:
        #    # support for deck labels
        #    #if (deck_labels) and (deck.id in deck_labels.values()):
        #    #    deck_label = [l for l in deck_labels if deck_labels[l] == deck.id][0]
        #    #    if only_labels:
        #    #        balances.update({deck_label : balance})
        #    #    else:
        #    #        balances.update({"{} ({})".format(deck_label, deck.id) : balance})
        #    #else:
        #    #    balances.update({deck.id : balance})

    # sorting
    #     if advanced is True:
    if len(addresses) > 1:
        addresses = eu.sort_address_items(addresses, debug=debug)

    if quiet:
        print(addresses)
    elif (advanced is True) or (not wallet):
        for item in addresses:
            ei.print_address_balances(item)
    else:
        ei.print_default_balances_list(addresses, decks, network_name=Settings.network, only_tokens=only_tokens)

def single_balance(deck: str, address: str=Settings.key.address, wallet: bool=False, keyring: bool=False, no_labels: bool=False, quiet: bool=False):
    """Shows the balance of a single token (deck) on the current main address or another address.
    --wallet flag allows to show all balances of addresses
    which are part of the wallet."""

    deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, quiet=quiet) if deck else None
    deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

    if wallet:
        wallet_addresses = list(eu.get_wallet_address_set(empty=True, include_named=True))
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

