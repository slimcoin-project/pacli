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

    if advanced is not True:
        # the quick mode displays only default PoB and PoD decks
        decks = get_default_tokens()
    elif deck_type is not None:
        decks = list_decks_by_at_type(provider, deck_type)
    else:
        decks = pa.find_all_valid_decks(provider, Settings.deck_version,
                                        Settings.production)

    if wallet is True and no_labels is False:
        labeldict = ec.get_labels_and_addresses(keyring=keyring, named=named, empty=empty, exclude=exclude, include_only=include_only)

    if only_tokens:
        balances = {}
    else:
        # this section adds the coin balances
        coin_balances = {}

        if wallet is True:
            if no_labels is False:
                labeled_addresses = labeldict.values()
            else:
                labeled_addresses = eu.get_wallet_address_set(empty=empty, include_named=True)
        else:
            labeled_addresses = [address]

        for addr in labeled_addresses:
            balance = float(str(provider.getbalance(addr)))
            coin_balances.update({addr: balance})

        if (advanced is True) and (not no_labels):
            coin_balances = ei.format_balances(coin_balances, labeldict, suppress_addresses=only_labels)

        balances = { Settings.network : coin_balances }

    # NOTE: default view needs no deck labels
    # NOTE2: Quiet mode doesn't show labels.
    # if ((advanced is True) and not no_labels) and (not quiet):
    deck_labels = None
    if not no_labels and not quiet:
        if advanced is True:
            deck_labels = ce.get_config()["deck"]
        elif wallet is False:
            try:
                deck_labels = c.default_token_labels(Settings.network)
            except KeyError:
                raise ei.PacliInputDataError("Default PoB and dPoD tokens are not supported on network '{}'.".format(Settings.network))


    for deck in decks:
        if debug:
            print("Checking deck:", deck.id)
        try:
            if wallet:
                # Note: returns a dict, structure of balances var is thus different.
                balance = eu.get_wallet_token_balances(deck, include_named=True)

                if (advanced is True) and (not no_labels) and (not quiet):
                    balance = ei.format_balances(balance, labeldict, suppress_addresses=only_labels)
            else:
                balance = eu.get_address_token_balance(deck, address)
                # print(address, balance)
        except KeyError:
            if debug:
                print("Warning: Omitting not initialized deck:", deck.id)
            continue

        if balance:
            # support for deck labels
            if (deck_labels) and (deck.id in deck_labels.values()):
                deck_label = [l for l in deck_labels if deck_labels[l] == deck.id][0]
                if only_labels:
                    balances.update({deck_label : balance})
                else:
                    balances.update({"{} ({})".format(deck_label, deck.id) : balance})
            else:
                balances.update({deck.id : balance})

    if quiet:
        print(balances)
    elif (advanced is True) or (not wallet):
        pprint(balances)
    else:
        ei.print_default_balances_list(balances, labeldict, decks, network_name=Settings.network, only_tokens=only_tokens)

def single_balance(deck: str, address: str=Settings.key.address, wallet: bool=False, keyring: bool=False, no_labels: bool=False, quiet: bool=False):
    """Shows the balance of a single token (deck) on the current main address or another address.
    --wallet flag allows to show all balances of addresses
    which are part of the wallet."""

    deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, quiet=quiet) if deck else None
    deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

    if wallet:
        wallet_addresses = list(eu.get_wallet_address_set(empty=True, include_named=True))
        # addrdict = { address : label for label, address in ec.get_labels_and_addresses(keyring=keyring).items() }
        labeldict = ec.get_labels_and_addresses(keyring=keyring)
        balances = eu.get_wallet_token_balances(deck, include_named=True)

        if (not no_labels) and (not quiet):
            balances = ei.format_balances(balances, labeldict)

        if quiet:
            print(balances)
        else:
            pprint(balances)
            return
    else:
        balance = eu.get_address_token_balance(deck, address)

        if quiet:
            print({address : balance})
        else:
            pprint({address : balance})

