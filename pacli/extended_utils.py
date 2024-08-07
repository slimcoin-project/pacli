import time, re, sys
from decimal import Decimal
import pypeerassets as pa
from typing import Optional, Union
from prettyprinter import cpprint as pprint
from pypeerassets.transactions import sign_transaction
from pypeerassets.networks import net_query
from pypeerassets.pa_constants import param_query
from pypeerassets.at.protobuf_utils import serialize_deck_extended_data
from pypeerassets.at.constants import ID_AT, ID_DT
from pypeerassets.pautils import amount_to_exponent, exponent_to_amount
from pypeerassets.exceptions import InsufficientFunds
import pypeerassets.at.dt_misc_utils as dmu # TODO: refactor this, the "sign" functions could go into the TransactionDraft module.
import pacli.config_extended as ce
import pacli.extended_constants as c
import pacli.extended_interface as ei
from pacli.provider import provider
from pacli.config import Settings
from pacli.utils import (sendtx, cointoolkit_verify)

# Utils which are used by both at and dt (and perhaps normal) tokens.

# Deck tools

def create_deckspawn_data(identifier, epoch_length=None, epoch_reward=None, min_vote=None, sdp_periods=None, sdp_deckid=None, at_address=None, multiplier=None, addr_type=2, startblock=None, endblock=None, debug: bool=False):
    """Creates a Protobuf datastring with the deck metadata."""

    # note: we use an additional identifier only for this function, to avoid having to import extension
    # data into __main__.
    # TODO: this note is obsolete as we now have extended_classes. Can be refactored.
    if multiplier % 1 != 0:
        raise ei.PacliInputDataError("The multiplier has to be an integer number.")

    if identifier == ID_DT:

        params = {"at_type" : ID_DT,
                 "epoch_length" : int(epoch_length),
                 "epoch_reward": int(epoch_reward),
                 "min_vote" : int(min_vote) if min_vote else 0,
                 "sdp_deckid" : bytes.fromhex(sdp_deckid) if sdp_deckid else b"",
                 "sdp_periods" : int(sdp_periods) if sdp_periods else 0 }

    elif identifier == ID_AT:

        params = {"at_type" : ID_AT,
                  "multiplier" : int(multiplier),
                  "at_address" : at_address,
                  "addr_type" : int(addr_type),
                  "startblock" : int(startblock) if startblock else 0,
                  "endblock" : int(endblock) if endblock else 0}

    data = serialize_deck_extended_data(net_query(provider.network), params=params)
    return data

def advanced_deck_spawn(name: str, number_of_decimals: int, issue_mode: int, asset_specific_data: bytes, change_address: str=Settings.change,
                        confirm: bool=True, verify: bool=False, sign: bool=False, send: bool=False, locktime: int=0, debug: bool=False) -> None:
    """Alternative function for deck spawns. Allows p2pk inputs."""

    network = Settings.network
    production = Settings.production
    version = Settings.deck_version

    new_deck = pa.Deck(name, number_of_decimals, issue_mode, network,
                           production, version, asset_specific_data)

    spawn_tx = pa.deck_spawn(provider=provider,
                          inputs=provider.select_inputs(Settings.key.address, 0.02),
                          deck=new_deck,
                          change_address=change_address,
                          locktime=locktime
                          )

    return finalize_tx(spawn_tx, confirm=confirm, verify=verify, sign=sign, send=send)


def init_deck(network: str, deckid: str, label: str=None, rescan: bool=True, quiet: bool=False, no_label: bool=True, debug: bool=False):
    """Initializes a 'common' deck (also AT/PoB). dPoD decks need further initialization of more P2TH addresses."""
    # NOTE: Default is now storing the deck name as a label, if it doesn't exist.

    if not quiet:
        print("Importing deck:", deckid)

    deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
    if deckid not in provider.listaccounts():
        provider.importprivkey(deck.p2th_wif, deck.id, rescan)
        if not quiet:
            print("Importing P2TH address from deck.")
    else:
        if not quiet:
            print("P2TH address was already imported.")
    check_addr = provider.validateaddress(deck.p2th_address)

    if debug:
        print("Output of validation tool:\n", check_addr)

    if not no_label:
        store_deck_label(deck, label=label, quiet=quiet, alt=False, debug=debug)

    if not quiet:
        print("Done.")

def store_deck_label(deck: object, label: str=None, alt: bool=False, quiet: bool=False, debug: bool=False):

    value_exists_errmsg = "Storage of deck ID {} failed, label {} already exists for a deck.\nStore manually using 'pacli deck set LABEL {}' with a custom LABEL value."

    if not label:
        if not quiet:
            print("Trying to store global deck name {} as a local label for this deck.".format(deck.name))

        existing_labels = ce.list("deck", quiet=True, debug=debug)

        if alt is False:
            local_name = ce.find("deck", deck.id, quiet=True, debug=debug)

            if local_name: # is empty list if no label is found
               if not quiet:
                   print("Label not stored. There is already at least one local name (label) for the deck: {}".format(local_name))
                   return

        if deck.name in existing_labels:
            raise ei.PacliInputDataError(value_exists_errmsg.format(deck.id, deck.name, deck.id))
        else:
            label = deck.name

        for d in pa.find_all_valid_decks(provider, Settings.deck_version, Settings.production):
            if (d.name == deck.name) and (d.id != deck.id) and (d.issue_time <= deck.issue_time):
                if not quiet:
                    print("{} was already used as a global name by another earlier deck: {}".format(deck.name, d.id))
                    print("It can be still used as a local label.")
                    print("Confirm the name typing [ENTER], or input another name.")
                    input_name = input()
                    if len(input_name.strip()) > 0: # strip avoids that space is entered
                        label = input_name

    try:
        ce.setcfg("deck", label, deck.id, quiet=quiet, debug=debug)
    except ei.ValueExistsError:
        raise ei.PacliInputDataError(value_exists_errmsg.format(deck.id, label, deck.id))


def get_deckinfo(deckid, p2th: bool=False):
    """Returns basic deck info dictionary, optionally with P2TH addresses for dPoD tokens."""
    d = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
    d_dict = d.__dict__
    if p2th:
        print("Showing P2TH addresses.")
        # the following code generates the addresses, so it's not necessary to add them to the dict.
        # TODO shouldn't it be possible simply to use a list?
        p2th_dict = {"p2th_main": d.p2th_address}
        try:
            if d.at_type == 1:
                p2th_dict.update(get_dt_p2th_addresses(d))
        except AttributeError:
            pass

    return d_dict

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
            derived_accounts = get_dt_p2th_accounts(deck)
            if set(derived_accounts.values()).isdisjoint(accounts):
                if debug:
                    print("Deck not completely initialized", deck.id)
                continue
        if debug:
            print("Adding initialized deck", deck.id)
        initialized_decks.append(deck)
    return initialized_decks

def search_global_deck_name(identifier: str, quiet: bool=False, check_initialized: bool=True):

    if not quiet:
        print("Deck not named locally. Searching global deck name ...")
    # this will only search in confirmed decks
    decks = [d for d in list(pa.find_all_valid_decks(provider, Settings.deck_version, Settings.production)) if d.issue_time > 0]
    decks.sort(key = lambda x: (x.issue_time, x.id))
    matching_decks = [d for d in decks if d.name == identifier]
    if len(matching_decks) > 0:
        deck = matching_decks[0]
        if not quiet:
            if len(matching_decks) > 1:
                print("More than one matching deck found:", [d.id for d in matching_decks])
                if deck.issue_time != matching_decks[1].issue_time:
                    print("Using first issued deck with this global name with id:", deck.id)
                else:
                    print("There are several decks with the same name and issue time.")
                    print("Using the deck with the lowest value of the TXID.", deck.id)
            else:
                print("Using matching deck with global name {}, with id: {}".format(identifier, deck.id))
            if check_initialized:
                idecks = [di.id for di in get_initialized_decks(decks)]
                if deck.id not in idecks:
                    print("WARNING: This deck was never initialized. Most commands will not work properly, they may output no information at all.")
                    print("Initialize the deck with 'pacli deck init {}'".format(deck.id))

        return deck.id
    else:
        return None

# Transaction signing and sending tools

def signtx_by_key(rawtx, label=None, key=None):
    """Allows to sign a transaction with a different than the main key."""

    if not key:
        try:
           key = get_key(label)
        except ValueError:
           raise ei.PacliInputDataError("No key nor label provided.")

    return sign_transaction(provider, rawtx, key)

def finalize_tx(rawtx: dict, verify: bool=False, sign: bool=False, send: bool=False, confirm: bool=False, redeem_script: str=None, label: str=None, key: str=None, input_types: list=None, ignore_checkpoint: bool=False, save: bool=False, debug: bool=False, quiet: bool=False) -> object:
    """Final steps of a transaction creation. Checks, verifies, signs and sends the transaction, and waits for confirmation if the 'confirm' option is used."""
    # Important function called by all AT, DT and Dex transactions and groups several checks and the last steps (signing) together.

    if verify:
        if Settings.network in ("ppc", "tppc"):

            print(
                cointoolkit_verify(rawtx.hexlify())
                 )  # link to cointoolkit - verify

        else:
            raise ei.PacliInputDataError("Verifying by Cointoolkit is not possible on other chains than Peercoin.")


    if (False in (sign, send)) and (not quiet):
        print("NOTE: This is a dry run, your transaction will still not be broadcasted.\nAdd --sign --send to the command to broadcast it")

    dict_key = 'hex' # key of dict returned to the user.

    if not ignore_checkpoint and (send is True):
        # if a reorg/orphaned checkpoint is detected, require confirmation to continue.
        from pacli.extended_checkpoints import reorg_check, store_checkpoint
        if reorg_check(quiet=quiet) and not ei.confirm_continuation():
            return

        store_checkpoint(quiet=quiet)

    if sign:

        if redeem_script is not None:
            if debug: print("Signing with redeem script:", redeem_script)
            # TODO: in theory we need to solve inputs from --new_inputs separately from the p2sh inputs.
            # For now we can only use new_inputs OR spend the P2sh.
            # MODIF: no more the option to use a different key!
            try:
                tx = dmu.sign_p2sh_transaction(provider, rawtx, redeem_script, Settings.key)
            except NameError as e:
                raise ei.PacliInputDataError("Invalid redeem script.")

        elif (key is not None) or (label is not None): # sign with a different key
            tx = signtx_by_key(rawtx, label=label, key=key)
            # we need to check the type of the input, as the Kutil method cannot sign P2PK
            # TODO: do we really want to preserve this option? Re-check DEX
        else:
            if input_types is None:
                input_types = get_input_types(rawtx)

            if "pubkey" not in input_types:
                tx = sign_transaction(provider, rawtx, Settings.key)
            else:
                tx = dmu.sign_mixed_transaction(provider, rawtx, Settings.key, input_types)

        if send:
            if not quiet:
                pprint({'txid': sendtx(tx)})
            else:
                sendtx(tx)
            if confirm:
                ei.confirm_tx(tx, quiet=quiet)

        tx_hex = tx.hexlify()

    elif send:
        # this is when the tx is already signed (DEX use case)
        sendtx(rawtx)
        tx_hex = rawtx.hexlify()

        if confirm:
            ei.confirm_tx(tx, quiet=quiet)

    else:
        dict_key = 'raw hex'
        tx_hex = rawtx.hexlify()


    if save:
        try:
            assert True in (sign, send) # even if an unsigned tx gets a txid, it doesn't make sense to save it
            txid = tx["txid"] if tx is not None else rawtx["txid"]
        except (KeyError, AssertionError):
            raise PacliInputDataError("You can't save a transaction which was not at least partly signed.")
        else:
            save_transaction(txid, tx_hex)

    return { dict_key : tx_hex }


# Transaction retrieval tools

def get_wallet_transactions(fburntx: bool=False, exclude: list=None, debug: bool=False):
    """Gets all transactions stored in the wallet."""

    raw_txes = []
    all_accounts = list(provider.listaccounts().keys())
    # all_accounts = [a for a in list(provider.listaccounts().keys()) if is_possible_address(a) == False]
    # print(all_accounts)
    all_accounts.reverse() # retrieve relevant accounts first, then the rest of the txes in "" account
    for account in all_accounts:
        if exclude and (account in exclude):
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

def find_transaction_by_string(searchstring: str, only_start: bool=False):
    """Returns transactions where the TXID matches a string."""

    wallet_txids = set([tx.txid for tx in get_wallet_transactions()])
    matches = []
    for txid in wallet_txids:
       if (only_start and txid.startswith(searchstring)) or (searchstring in txid and not only_start):
           matches.append(txid)
    return matches

def get_input_types(rawtx):
    """Gets the types of ScriptPubKey inputs of a transaction.
       Not ideal in terms of resource consumption/elegancy, but otherwise we would have to change PeerAssets core code,
       because it manages input selection (RpcNode.select_inputs)"""
    input_types = []
    try:
        for inp in rawtx.ins:
            prev_tx = provider.getrawtransaction(inp.txid, 1)
            prev_out = prev_tx["vout"][inp.txout]
            input_types.append(prev_out["scriptPubKey"]["type"])

        return input_types

    except KeyError:
        raise ei.PacliInputDataError("Transaction data not correctly given.")


# CardTransfer tools

def advanced_card_transfer(deck: object=None, deckid: str=None, receiver: list=None, amount: list=None,
                 asset_specific_data: str=None, locktime: int=0, verify: bool=False, change_address: str=Settings.change,
                 sign: bool=False, send: bool=False, balance_check: bool=False, debug: bool=False, quiet: bool=False, confirm: bool=False) -> Optional[dict]:
    """Alternative function for card transfers. Allows some more options than the vanilla PeerAssets features, and to use P2PK inputs."""

    if not deck:
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

    amount_list = [amount_to_exponent(i, deck.number_of_decimals) for i in amount]

    # balance check
    if balance_check:
        if not quiet:
            print("Checking sender balance ...")
        balance = Decimal(str(get_address_token_balance(deck, Settings.key.address)))
        if balance < sum(amount):
            raise ei.PacliInputDataError("Not enough balance of this token.")

    if isinstance(deck, pa.Deck):
        card = pa.CardTransfer(deck=deck,
                               receiver=receiver,
                               amount=amount_list,
                               version=deck.version,
                               asset_specific_data=asset_specific_data
                               )

    else:

        raise ei.PacliInputDataError({"error": "Deck {deckid} not found.".format(deckid=deckid)})

    try:
        issue_tx = pa.card_transfer(provider=provider,
                                 inputs=provider.select_inputs(Settings.key.address, 0.02),
                                 card=card,
                                 change_address=change_address,
                                 locktime=locktime
                                 )

    except InsufficientFunds:
        raise ei.PacliInputDataError("Insufficient funds.")

    return finalize_tx(issue_tx, verify=verify, sign=sign, send=send, quiet=quiet, confirm=confirm, debug=debug)


def get_valid_cardissues(deck: object, input_address: str=None, only_wallet: bool=False) -> list:
    """Gets all valid CardIssues of a deck."""
    # NOTE: Sender no longer necessary.
    # TODO: seems the restriction to wallet does not work correctly, also other txes are shown.

    if (only_wallet and not input_address):
        p2th_accounts = get_p2th(accounts=True)
        wallet_txids = set([t["txid"] for t in get_wallet_transactions(exclude=p2th_accounts)])
    else:
        wallet_txids = None

    try:
        cards = pa.find_all_valid_cards(provider, deck)
        ds = pa.protocol.DeckState(cards)
    except KeyError:
        raise ei.PacliInputDataError("Deck not initialized. Initialize it with 'pacli deck init DECK'")

    claim_cards = []
    for card in ds.valid_cards:
        if card.type == "CardIssue":
            if (input_address and (card.sender == input_address)) \
            or (wallet_txids and (card.txid in wallet_txids)) \
            or ((input_address is None) and not wallet_txids):
                claim_cards.append(card)
    return claim_cards

# Transaction storage tools

def save_transaction(identifier: str, tx_hex: str, partly: bool=False) -> None:
    """Stores transaction in configuration file.
    'partly' indicates that it's a partly signed transaction"""
    # the identifier can be a txid or (in the case of partly signed transactions) an arbitrary string.
    cat = "txhex" if partly else "transaction"
    ce.write_item(cat, identifier, tx_hex)
    if not quiet:
        print("Transaction {} saved. Retrieve it with 'pacli tools show_transaction TXID'.".format(txid))

def search_for_stored_tx_label(category: str, identifier: str, quiet: bool=False, check_deck: bool=True, debug: bool=False) -> str:
    """If the identifier is a label stored in the extended config file, return the associated txid."""
    # returns first the identifier if it's already in txid format.

    identifier = str(identifier) # will not work with int values, but we want ints to be possible as identifiers
    if is_possible_txid(identifier):
        if check_deck and category == "deck":
            # TODO: this is not ideal, it should return the deck object eventually
            # could also be implemented this way for proposals
            if pa.find_deck(provider, identifier, Settings.deck_version, Settings.production) is not None:
                return identifier
        else:
            return identifier

    result = ce.read_item(category, identifier)

    if result is not None:
        if is_possible_txid(result):
            if not quiet:
                print("Using {} stored locally with label {} and ID {}.".format(category, identifier, result))
            return result
        else:
            raise ei.PacliInputDataError("The string stored for this label is not a valid transaction ID. Check if you stored it correctly.")

    elif category == "deck":
        result = search_global_deck_name(identifier, quiet=quiet)
        if result:
            return result


    raise ei.PacliInputDataError("Label '{}' not found.".format(identifier))

# General token tools

def get_address_token_balance(deck: object, address: str) -> Decimal:
    """Gets token balance of a single deck of an address, as a Decimal value."""

    cards = pa.find_all_valid_cards(provider, deck)
    state = pa.protocol.DeckState(cards)

    for i in state.balances:
        if i == address:
            return exponent_to_amount(state.balances[i], deck.number_of_decimals)
    else:
        return 0

def get_wallet_token_balances(deck: object, include_named: bool=False) -> dict:
    """Gets token balances of a single deck, of all wallet addresses, as a Decimal value."""

    cards = pa.find_all_valid_cards(provider, deck)
    state = pa.protocol.DeckState(cards)
    addresses = list(get_wallet_address_set(empty=True, include_named=include_named)) # token balances can be on empty addresses, thus empty must be set to True
    balances = {}
    for address in state.balances:

        if address in addresses:
            balances.update({address : exponent_to_amount(state.balances[address], deck.number_of_decimals)})

    return balances

def show_claims(deck_str: str, address: str=None, wallet: bool=False, full: bool=False, param: str=None, quiet: bool=False, debug: bool=False):
    '''Shows all valid claim transactions for a deck, with rewards and TXIDs of tracked transactions enabling them.'''

    if deck_str is None:
        raise ei.PacliInputDataError("No deck given, for --claim options the deck is mandatory.")

    param_names = {"txid" : "TX ID", "amount": "Token amount(s)", "receiver" : "Receiver(s)", "blocknum" : "Block height"}

    deckid = search_for_stored_tx_label("deck", deck_str)
    deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

    if "at_type" not in deck.__dict__:
        raise ei.PacliInputDataError("{} is not a DT/dPoD or AT/PoB deck.".format(deckid))

    try:
        assert deck.at_address == c.BURN_ADDRESS[provider.network]
        param_names.update({"donation_txid" : "Burn transaction"})
        if debug:
            print("PoB token detected.")
    except (AssertionError, AttributeError) as e:
        # AssertionError gets thrown by a non-PoB AT token, AttributeError by dPoD token
        param_names.update({"donation_txid" : "Referenced transaction"})
        if debug:
            token_type = "dPoD" if type(e) == AttributeError else "AT"
            print("{} token detected.".format(token_type))

    raw_claims = get_valid_cardissues(deck, input_address=address, only_wallet=wallet)
    claim_txids = set([c.txid for c in raw_claims])
    if debug:
        print("{} claim transactions found.".format(len(claim_txids)))
    claims = []

    for claim_txid in claim_txids:
        bundle = [c for c in raw_claims if c.txid == claim_txid]
        claim = bundle[0]
        if len(bundle) > 1:
            for b in bundle[1:]:
                claim.amount.append(b.amount[0])
                claim.receiver.append(b.receiver[0])
        claims.append(claim)

    if full:
        result = [c.__dict__ for c in claims]
    elif param:
        # TODO: this now is unnecessary based on the transaction list command
        # re-check other commands
        try:
            result = [{ claim.txid : claim.__dict__.get(param) } for claim in claims]
        except KeyError:
            raise ei.PacliInputDataError("Parameter does not exist in the JSON output of this mode, or you haven't entered a parameter. You have to enter the parameter after --param/-p.")
    else:
        result = [{param_names["txid"] : claim.txid,
                   param_names["donation_txid"] : claim.donation_txid,
                   param_names["amount"] : [exponent_to_amount(a, claim.number_of_decimals) for a in claim.amount],
                   param_names["receiver"] : claim.receiver,
                   param_names["blocknum"] : claim.blocknum} for claim in claims]

    if (not quiet) and len(result) == 0:
        print("No claim transactions found.")

    return result

# Misc tools

def get_safe_block_timeframe(period_start, period_end, security_level=1):
    """Returns a safe blockheight for TrackedTransactions to make reorg attacks less likely.
    Security levels:

    0 is very risky (5 to 95%, no minimum distance in blocks to period border)
    1 is default (10 to 90%, 25 blocks minimum, equivalent to the recommended number of confirmations)
    2 is safe (20 to 80%, 50 blocks minimum)
    3 is very safe (30 to 70%, 100 blocks minimum)
    4 is optimal (50%), always in the block closest to the middle of each period"""
    security_levels = [(5, 0),
                       (10, 25),
                       (20, 50),
                       (30, 100),
                       (50, 0)]

    period_length = period_end - period_start
    level = security_levels[security_level]
    safe_start = period_start + max(period_length * level[0], level[1])
    safe_end = period_end - max(period_length * level[0], level[1])
    return (safe_start, safe_end)

def get_wallet_address_set(empty: bool=False, include_named: bool=False) -> set:
    """Returns a set (without duplicates) of all addresses which have received coins eventually, in the own wallet."""
    # TODO: listreceivedbyaddress seems to be unreliable.
    addr_entries = provider.listreceivedbyaddress(0, empty)
    addresses = [e["address"] for e in addr_entries]

    if include_named:
        named_addresses = ce.list("address", quiet=True).values()
        addresses += named_addresses

    return set(addresses)

def is_possible_txid(txid: str) -> bool:
    """Very simple TXID format verification."""
    try:

        assert len(txid) == 64
        hexident = int(txid, 16)
        return True

    except (ValueError, AssertionError):
        return False

def is_possible_base58_address(address: str, network_name: str):
    """Very simple address format validation, without checksum test."""

    not_b58 = re.compile(r"[^123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]")
    network = net_query(network_name)

    if address[0] not in network.base58_prefixes:
        return False
    elif re.search(not_b58, address):
        return False
    else:
        return True

def is_possible_address(address: str, network_name: str=Settings.network, validate: bool=True):

    if validate is True:
        try:
            if provider.validateaddress(address).get("isvalid") == True:
                return True
            else:
                return False
        except:
             # if validateaddress command is not supported on blockchain, this fallbacks to the old method
             pass

    try:
        assert len(address) > 0
        assert is_possible_base58_address(address, network_name)
        return True
    except AssertionError:
        # raise ei.PacliInputDataError("No valid address string or non-existing label.")
        return False

def get_p2th(accounts: bool=False):

    if accounts:
        result = ["PAPROD", "PATEST"] # default P2TH accounts for deck spawns
    else:
        pa_params = param_query(Settings.network)
        result = [pa_params.P2TH_addr, pa_params.test_P2TH_addr]

    decks = pa.find_all_valid_decks(provider, Settings.deck_version,
                                        Settings.production)
    for deck in decks:
        if accounts:
            result.append(deck.id) # Deck P2TH account
        else:
            result.append(deck.p2th_address) # Deck P2TH addr.

        # derived P2THs of DT tokens
        if getattr(deck, "at_type", None) == ID_DT:
            if accounts:
                result += get_dt_p2th_accounts(deck).values()
            else:
                result += get_dt_p2th_addresses(deck).values()

    return result

def get_p2th_dict():
    pa_params = param_query(Settings.network)
    result = {pa_params.P2TH_addr : "PAPROD",
              pa_params.test_P2TH_addr : "PATEST"}

    decks = pa.find_all_valid_decks(provider, Settings.deck_version,
                                        Settings.production)
    for deck in decks:
        result.update({ deck.p2th_address : deck.id })

        if getattr(deck, "at_type", None) == ID_DT:
            for tx_type in ("proposal", "signalling", "locking", "donation", "voting"):
                value = deck.id + tx_type.upper()
                key = deck.derived_p2th_address(tx_type)
                result.update ({ key : value })

    return result

def get_dt_p2th_addresses(deck):
    return {"p2th_proposal" : deck.derived_p2th_address("proposal"),
            "p2th_signalling" : deck.derived_p2th_address("signalling"),
            "p2th_locking" : deck.derived_p2th_address("locking"),
            "p2th_donation" : deck.derived_p2th_address("donation"),
            "p2th_voting" : deck.derived_p2th_address("voting")}

def get_dt_p2th_accounts(deck):
    return {"p2th_proposal" : deck.id + "PROPOSAL",
            "p2th_signalling" : deck.id + "SIGNALLING",
            "p2th_locking" : deck.id + "LOCKING",
            "p2th_donation" : deck.id + "DONATION",
            "p2th_voting" : deck.id + "VOTING"}

def get_deck_p2th_addresses(deck, debug: bool=False):
    addresses = [deck.p2th_address]

    if "at_type" in deck.__dict__:
        if deck.at_type == ID_DT:
            dt_p2th = list(get_dt_p2th_addresses(deck).values())
            addresses += dt_p2th
        elif deck.at_type == ID_AT:
            # AT addresses can have duplicates, others not
            if deck.at_address not in addresses:
                addresses.append(deck.at_address)
            if debug:
                print("AT address appended:", deck.at_address)

    return addresses


def manage_send(sign, send):
    result = []
    for setting in [sign, send]:
        if setting is None:
            if Settings.compatibility_mode is True:
                setting = False
            else:
                setting = True
        result.append(setting)
    return result



