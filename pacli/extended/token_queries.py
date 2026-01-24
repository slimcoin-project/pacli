# queries involving tokens

import pypeerassets as pa
from prettyprinter import cpprint as pprint
from decimal import Decimal
from pypeerassets.pautils import exponent_to_amount
from pypeerassets.at.constants import ID_AT, ID_DT
from pypeerassets.at.dt_misc_utils import list_decks_by_at_type
import pacli.extended.constants as c
import pacli.extended.utils as eu
import pacli.extended.interface as ei
import pacli.extended.config as ce
import pacli.extended.queries as eq
import pacli.extended.handling as eh
from pacli.provider import provider
from pacli.config import Settings


def get_default_tokens():
    decks = [pa.find_deck(provider, c.DEFAULT_POB_DECK[Settings.network], Settings.deck_version, Settings.production),
             pa.find_deck(provider, c.DEFAULT_POD_DECK[Settings.network], Settings.deck_version, Settings.production)]
    return decks


def all_balances(address: str=None,
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
    # TODO: currently -w mode shows too few balances, even addresses with token balances are omitted.

    # address = ke.get_main_address() if address is None else address
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
        decks = get_initialized_decks(decks, debug=debug)

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
        addresses = eq.get_labels_and_addresses(access_wallet=access_wallet, prefix=Settings.network, keyring=keyring, named=named, empty=True, exclude=exclude, excluded_accounts=excluded_accounts, include=include, include_only=include_only, wallet_only=wallet_only, no_labels=no_labels, balances=balances, debug=debug)
    else:
        addresses = eq.get_labels_and_addresses(access_wallet=access_wallet, prefix=Settings.network, keyring=keyring, named=named, empty=True, include_only=[address], no_labels=no_labels, balances=balances, debug=debug)

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
                raise eh.PacliInputDataError("Default PoB and dPoD tokens are not supported on network '{}'.".format(Settings.network))

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
            get_wallet_token_balances(deck, identifier=deck_identifier, include_named=True, address_dicts=addresses, no_labels=no_labels, debug=debug)
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
        if len(addresses) == 0:
            print("No token balances found.")
        else:
            for item in addresses:
                ei.print_address_balances(item)
    elif no_tokens:
        if add_p2th_account == True:
            for item in addresses:
                item.update({"account" : p2th_dict.get(item["address"])})

        ei.print_address_list(addresses, p2th=add_p2th_account)
    else:
        ei.print_default_balances_list(addresses, decks, network_name=Settings.network, only_tokens=only_tokens)

def single_balance(deck: str, address: str=None, wallet: bool=False, named: bool=False, keyring: bool=False, no_labels: bool=False, quiet: bool=False):
    """Shows the balance of a single token (deck) on the current main address or another address.
    --wallet flag allows to show all balances of addresses which are part of the wallet."""

    # address = ke.get_main_address() if address is None else address
    deckid = eu.search_for_stored_tx_label("deck", deck, quiet=quiet) if deck else None
    deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

    if wallet or named:
        addresses = eq.get_labels_and_addresses(keyring=keyring, named=named, empty=True)
        balances = get_wallet_token_balances(deck, include_named=True)

        if quiet:
            print(balances)
        elif no_labels:
            pprint(balances)
        else:
            addresses_with_tokens = ei.add_token_balances(addresses, deck.id, balances, return_present=True)
            pprint([{a["addr_identifier"] : a["tokens"][deck.id]} for a in addresses_with_tokens])
                #for a in addresses:
                #    if "tokens" in a and deck.id in a["tokens"]:
                #            pprint({ a["addr_identifier"] : a["tokens"][deck.id] })
            return
    else:
        balance = get_address_token_balance(deck, address)

        if quiet:
            print({address : float(balance)})
        else:
            pprint({address : float(balance)})


def get_address_token_balance(deck: object, address: str, return_statedict: bool=False) -> Decimal:
    """Gets token balance of a single deck of an address, as a Decimal value."""

    cards = pa.find_all_valid_cards(provider, deck)
    state = pa.protocol.DeckState(cards)

    for i in state.balances:
        if i == address:
            balance = exponent_to_amount(state.balances[i], deck.number_of_decimals)
            result = Decimal(str(balance))
            break
    else:
        result = Decimal(0)
    if return_statedict is True:
        return {"state" : state, "balance" : result}
    else:
        return result

def get_wallet_token_balances(deck: object, addresses: list=None, address_dicts: list=None, identifier: str=None, include_named: bool=False, no_labels: bool=False, suppress_addresses: bool=False, debug: bool=False) -> dict:
    """Gets token balances of a single deck, of all wallet addresses, as a Decimal value."""

    cards = pa.find_all_valid_cards(provider, deck)
    state = pa.protocol.DeckState(cards)
    token_identifier = identifier if identifier is not None else deck.id
    if debug:
        print("Cards and deck state retrieved. Updating balances ...")
    if not address_dicts and not addresses:
        addresses = list(eq.get_wallet_address_set(empty=True, include_named=include_named)) # token balances can be on empty addresses, thus empty must be set to True
    balances = {}
    for address in state.balances:
        balance = exponent_to_amount(state.balances[address], deck.number_of_decimals)
        if address_dicts:
            for item in address_dicts:
                # NOTE: the address_identifier step should probably be better separated.
                ei.add_address_identifier(item, no_labels=no_labels, suppress_addresses=suppress_addresses)
                if address == item["address"]:
                    if "tokens" not in item:
                        item.update({"tokens" : {token_identifier: balance}})
                    else:
                        item["tokens"].update({token_identifier: balance})
                    break
        elif address in addresses:
            balances.update({address : balance})
    if not address_dicts: # if the address_dict is given, returning it is not necessary.
        return balances


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
        raise eh.PacliInputDataError("Invalid transaction ID.")

    if deck_str is None:
        raise eh.PacliInputDataError("No deck given, for --claim options the token/deck is mandatory.")

    if quiet or basic:
        param_names = {"txid" : "txid", "amount": "amount", "sender" : "sender", "receiver" : "receiver", "blocknum" : "blockheight"}
    else:
        param_names = {"txid" : "Claim transaction ID", "amount": "Token amount(s)", "sender" : "Sender", "receiver" : "Receiver(s)", "blocknum" : "Block height"}

    deck = eu.search_for_stored_tx_label("deck", deck_str, quiet=quiet, check_initialized=True, return_deck=True, abort_uninitialized=True)
    # deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

    if "at_type" not in deck.__dict__:
        raise eh.PacliInputDataError("{} is not a DT/dPoD or AT/PoB token.".format(deck.id))

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
        # NOTE: changed method to restrict result to wallet addresses, now ismine and P2TH exclusion is used.
        raw_claims = get_valid_cardissues(deck, only_wallet=True, excluded_senders=p2th_dict.keys(), debug=debug)
    else:
        raw_claims = get_valid_cardissues(deck, sender=address, debug=debug)

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
            raise eh.PacliInputDataError("Parameter does not exist in the JSON output of this mode, or you haven't entered a parameter. You have to enter the parameter after --param/-p.")
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


def get_initialized_decks(decks: list, debug: bool=False) -> list:
    # from the given list, checks which ones are initialized
    # decks have to be given completely, not as deck ids.
    accounts = provider.listaccounts()
    if debug:
        print("Accounts:", sorted(list(accounts.keys())))
    initialized_decks = []
    for deck in decks:
        if not deck.id in accounts.keys():
            if debug:
                print("Deck not initialized:", deck.id)
            continue
        elif "at_type" in deck.__dict__ and deck.at_type == ID_DT:
            derived_accounts = eu.get_dt_p2th_accounts(deck)
            if set(derived_accounts.values()).isdisjoint(accounts):
                if debug:
                    print("Deck not completely initialized", deck.id)
                continue
        if debug:
            print("Adding initialized deck", deck.id)
        initialized_decks.append(deck)
    return initialized_decks


def get_valid_cardissues(deck: object, sender: str=None, only_wallet: bool=False, allowed_senders: list=None, excluded_senders: list=None, debug: bool=False) -> list:
    """Gets all valid CardIssues of a deck."""
    # NOTE: wallet restriction "outsourced". only_wallet = True works only with allowed_senders now.

    wallet_senders = allowed_senders if (allowed_senders is not None and only_wallet) else []

    try:

        cards = pa.find_all_valid_cards(provider, deck)
        ds = pa.protocol.DeckState(cards)
    except KeyError:
        raise eh.PacliInputDataError("Deck not initialized. Initialize it with 'pacli deck init DECK'")

    claim_cards = []
    for card in ds.valid_cards:
        if card.type == "CardIssue":
            if (((sender is not None) and (card.sender == sender))
            or (only_wallet and (card.sender in wallet_senders))
            or (only_wallet and eu.is_mine(card.sender, debug=debug) and not card.sender in excluded_senders)
            or ((sender is None) and not only_wallet)):
                claim_cards.append(card)
                if debug:
                    print("Card added:", card.txid, "Sender:", card.sender)
            elif debug:
                print("Card rejected:", card.txid, "Sender:", card.sender)

    return claim_cards


def find_decks_by_address(address: str, addrtype: str=None, debug: bool=False) -> object:
    all_decks = pa.find_all_valid_decks(provider, Settings.deck_version, Settings.production)
    matching_decks = []
    for deck in all_decks:
        deck_addresses = get_deck_related_addresses(deck, advanced=True, debug=debug)
        if debug:
            print("Deck:", deck.id, "Addresses:", deck_addresses)

        for key, value in deck_addresses.items():
            if addrtype is not None and key != addrtype:
                continue
            if value == address:
                matching_decks.append({"deck" : deck, "type" : key})

    return matching_decks

def get_deck_related_addresses(deck, advanced: bool=False, debug: bool=False):
    """Gets all addresses relevant for a deck: main P2TH, DT P2TH and AT address."""

    if advanced:
        addresses = {"p2th_main": deck.p2th_address}
    else:
        addresses = [deck.p2th_address]

    if "at_type" in deck.__dict__:
        if deck.at_type == ID_DT:
            dt_p2th_addresses = eu.get_dt_p2th_addresses(deck)
            if advanced:
                addresses.update(dt_p2th_addresses)
            else:
                dt_p2th = list(dt_p2th_addresses.values())
                addresses += dt_p2th

        elif deck.at_type == ID_AT:

            if advanced:
                addresses.update({"gateway" : deck.at_address})
            else:
                # AT addresses can have duplicates, others not
                if deck.at_address not in addresses:
                    addresses.append(deck.at_address)
                if debug:
                    print("AT address appended:", deck.at_address)

    return addresses

