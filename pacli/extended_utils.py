import re, hashlib
from decimal import Decimal
import pypeerassets as pa
from prettyprinter import cpprint as pprint
from pypeerassets.transactions import NulldataScript
from pypeerassets.networks import net_query
from pypeerassets.pa_constants import param_query
from pypeerassets.at.constants import ID_DT
from pypeerassets.pautils import parse_card_transfer_metainfo, read_tx_opreturn
from pypeerassets.__main__ import get_card_transfer
from pypeerassets.legacy import is_legacy_blockchain, legacy_mintx
import pypeerassets.at.dt_misc_utils as dmu # TODO: refactor this, the "sign" functions could go into the TransactionDraft module.
import pacli.extended_config as ce
import pacli.extended_interface as ei
import pacli.extended_handling as eh
from pacli.provider import provider
from pacli.config import Settings

# Utils which are used by both at and dt (and perhaps normal) tokens.

# Deck tools

def init_deck(network: str, deckid: str, label: str=None, rescan: bool=True, quiet: bool=False, no_label: bool=True, debug: bool=False):
    """Initializes a 'common' deck (also AT/PoB). dPoD decks need further initialization of more P2TH addresses."""
    # NOTE: Default is now storing the deck name as a label, if it doesn't exist.

    if not quiet:
        print("Importing deck:", deckid)

    deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
    if debug:
        print("Deck private key WIF (publicly available, so this is not a security leak):", deck.p2th_wif)
    if deckid not in provider.listaccounts():
        err = provider.importprivkey(deck.p2th_wif, deck.id, rescan)
        if type(err) == dict and err.get("code") == -13:
            raise eh.PacliDataError("Wallet locked, initializing deck is not possible. Please unlock the wallet and repeat the command.")
        if not quiet:
            print("Importing P2TH address from deck.")
    else:
        if not quiet:
            print("P2TH address was already imported.")
    check_addr = provider.validateaddress(deck.p2th_address)

    if debug:
        print("Output of validation tool:\n", check_addr)

    if not quiet:
        print("Deck correctly initialized. It is recommended to restart the {} client with -rescan to avoid issues.".format(Settings.network.upper()))

    if not no_label:
        store_deck_label(deck, label=label, quiet=quiet, alt=False, debug=debug)


def store_deck_label(deck: object, label: str=None, alt: bool=False, quiet: bool=False, debug: bool=False):

    value_exists_errmsg = "Storage of deck ID {} failed, label {} already exists for a deck.\nStore manually using 'pacli deck set LABEL {}' with a custom LABEL value."

    if not label:
        if not quiet:
            print("Trying to store global deck name {} as a local label for this deck ...".format(deck.name))

        existing_labels = ce.list("deck", quiet=True, debug=debug)

        if alt is False:
            local_name = ce.find("deck", deck.id, quiet=True, debug=debug)

            if local_name: # is empty list if no label is found
               if not quiet:
                   print("Label not stored. There is already at least one local name (label) for the deck: {}".format(local_name))
                   return

        if deck.name in existing_labels:
            raise eh.PacliInputDataError(value_exists_errmsg.format(deck.id, deck.name, deck.id))
        else:
            label = deck.name

        for d in pa.find_all_valid_decks(provider, Settings.deck_version, Settings.production):
            if (d.name == deck.name) and (d.id != deck.id) and (d.issue_time <= deck.issue_time):
                if not quiet:
                    print("{} was already used as a global name by another earlier deck: {}".format(deck.name, d.id))
                    print("Earlier decks have priority to be used as local labels, thus no local label was stored.")
                    print("If you anyway want to use this name as local label, store it manually:")
                    print("pacli deck set {} {}".format(deck.name, deck.id))
                return

    try:
        ce.setcfg("deck", label, deck.id, quiet=quiet, debug=debug)
    except eh.ValueExistsError:
        print(value_exists_errmsg.format(deck.id, label, deck.id))
    except eh.PacliDataError as e:
        print("Deck initialized but label not stored:", e)


def get_deckinfo(d, p2th: bool=False):
    """Returns basic deck info dictionary, optionally with P2TH addresses for dPoD tokens."""
    # d = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
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

def search_global_deck_name(identifier: str, prioritize: bool=False, return_deck: bool=False, check_initialized: bool=True, abort_uninitialized: bool=False, quiet: bool=False):

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
                if not prioritize:
                    # prioritize is currently not supported, but may be useful for later.
                    raise eh.PacliInputDataError("Deck global name ambiguity, please use the deck's id or its local label.")

                if deck.issue_time != matching_decks[1].issue_time:
                    print("Using first issued deck with this global name with id:", deck.id)
                else:
                    print("There are several decks with the same name and issue time.")
                    print("Using the deck with the lowest value of the TXID.", deck.id)
            else:
                print("Using matching deck with global name {}, with id: {}".format(identifier, deck.id))
            if check_initialized:
                from pacli.extended_token_queries import get_initialized_decks
                idecks = [di.id for di in get_initialized_decks(decks)]
                if deck.id not in idecks:
                    print("WARNING: This deck was never initialized. Most commands will not work properly, they may output no information at all.")
                    print("Initialize the deck with 'pacli deck init {}'".format(deck.id))
                    if abort_uninitialized:
                        raise eh.PacliDataError("Cannot show requested information for uninitialized token(s).")

        result = deck if return_deck is True else deck.id
        return result
    else:
        return None


# Transaction retrieval tools

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
        raise eh.PacliInputDataError("Transaction data not correctly given.")

# Transaction storage tools

def save_transaction(identifier: str, tx_hex: str, partly: bool=False, quiet: bool=False) -> None:
    """Stores transaction in configuration file.
    'partly' indicates that it's a partly signed transaction"""
    # the identifier can be a txid or (in the case of partly signed transactions) an arbitrary string.
    # cat = "txhex" if partly else "transaction"
    cat = "transaction"
    ce.write_item(category=cat, key=identifier, value=tx_hex)
    if not quiet:
        print("Transaction saved. Retrieve it with 'pacli transaction show {}'.".format(identifier))

def search_for_stored_tx_label(category: str, identifier: str, quiet: bool=False, check_deck: bool=True, return_deck: bool=False, check_initialized: bool=True, abort_uninitialized: bool=False, debug: bool=False) -> str:
    """If the identifier is a label stored in the extended config file, return the associated txid."""
    # returns first the identifier if it's already in txid format.
    if identifier is None:
        raise eh.PacliInputDataError("No label provided. Please provide a valid {}.".format(category))

    identifier = str(identifier) # will not work with int values, but we want ints to be possible as identifiers
    if is_possible_txid(identifier):
        if category == "deck" and (check_deck or return_deck):
            # could also be implemented this way for proposals
            deck = pa.find_deck(provider, identifier, Settings.deck_version, Settings.production)
            if deck is not None:
                if return_deck is True:
                    return deck
                else:
                    return identifier
        else:
            return identifier

    result = ce.read_item(category, identifier)

    if result is not None:
        if is_possible_txid(result):
            if not quiet:
                print("Using {} stored locally with label {} and ID {}.".format(category, identifier, result))
            if return_deck is True:
                return pa.find_deck(provider, result, Settings.deck_version, Settings.production)
            else:
                return result
        else:
            raise eh.PacliDataError("The string stored for this label is not a valid transaction ID. Check if you stored it correctly.")

    elif category == "deck":
        result = search_global_deck_name(identifier, check_initialized=check_initialized, abort_uninitialized=abort_uninitialized, return_deck=return_deck, quiet=quiet)
        if result:
            return result
        else:
            raise eh.PacliDataError("Deck '{}' not found or not confirmed on the blockchain.".format(identifier))


    raise eh.PacliDataError("Label '{}' not found. Please provide a valid {}.".format(identifier, category))

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


def is_possible_txid(txid: str) -> bool:
    """Very simple TXID format verification."""
    try:

        assert len(txid) == 64
        hexident = int(txid, 16) # check
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
        # raise eh.PacliInputDataError("No valid address string or non-existing label.")
        return False

def is_mine(address: str, debug: bool=False) -> bool:
    try:
        if provider.validateaddress(address).get("ismine") == True:
            return True
    except:
        pass
    return False

def get_p2th_dict(decks: list=None, check_auxiliary: bool=False) -> dict:
    pa_params = param_query(Settings.network)
    auxiliary = {pa_params.P2TH_addr : "PAPROD",
              pa_params.test_P2TH_addr : "PATEST"}
    if check_auxiliary:
        result = {a : auxiliary[a] for a in auxiliary if auxiliary[a] in provider.listaccounts()}
    else:
        result = auxiliary

    if decks is None:
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


def get_claim_tx(txid: str, deck: object, quiet: bool=False, debug: bool=False):
    """Parses a claim transaction, even if it's not recognized as a card."""
    #TODO for now only supports AT/PoB.

    #if not is_possible_txid(txid):
    #    raise eh.PacliInputDataError("No valid transaction ID provided.")
    # deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

    if "at_type" not in deck.__dict__ or deck.at_type != 2:
        raise eh.PacliDataError("{} is not a PoB or AT token and thus not supported for this command.".format(deck.id))

    rawtx = provider.getrawtransaction(txid, 1)
    if not quiet:
        pprint("Complete transaction:")
        pprint(rawtx)

    fails = 0
    # Step 1: check P2TH address
    expected_p2th_addr = deck.p2th_address
    used_p2th_addr = rawtx["vout"][0]["scriptPubKey"]["addresses"][0]
    if used_p2th_addr != expected_p2th_addr:
        fails += 1
        if not quiet:
            print("P2TH address wrong: expected {}, used {}".format(expected_p2th_addr, used_p2th_addr))
    elif not quiet:
        print("P2TH address correct:", used_p2th_addr)

    # Step 2: Get cards in this transfer
    cardid = txid
    cards = list(get_card_transfer(provider, deck, cardid))
    for card in cards:
        pprint(card.to_json())

        print(card.type)
        #if card.type != "CardIssue":
        #    continue # normally this should not be triggered, but in the case there are cards in the same tx which are no Issuances they are ignored
        try:
            donation_txid = card.extended_data["txid"].hex()
        except KeyError:
            continue


    try:
        donationtx = provider.getrawtransaction(donation_txid, 1)
        print("Spending txid:", donation_txid)
    except UnboundLocalError:
        fails += 1
        if not quiet:
            if not cards:
                print("This is not a valid PeerAssets token transaction, it contains no card data. Stopping.")
            else:
                print("Extended data wrong: no txid found. Probably not a claim transaction but a regular token transfer. Stopping.")
            ei.print_red("Claim transactions appears invalid. Checks failed: {} from 2.".format(fails))
            return
        else:
            return fails


    # Step 3: check donation transaction, address & amount
    if deck.at_type == 2:
        expected_daddr = deck.at_address

    spent_value = 0
    for output in donationtx["vout"]:
        if expected_daddr == output["scriptPubKey"]["addresses"][0]:
            spent_value += Decimal(str(output["value"]))


    if spent_value == 0:
        fails += 1
        if not quiet:
            print("Donation/Gateway/Burn address wrong: no output spends to expected address {}.".format(expected_daddr))
    elif not quiet:
        print("Donation/Gateway/Burn address correct:", expected_daddr)

    claimed_amount = sum([card.amount[0] for card in cards])
    expected_claim_amount = int(spent_value * deck.multiplier * Decimal(str(10 ** deck.number_of_decimals)))
    if claimed_amount != expected_claim_amount:
        fails += 1
        if not quiet:
            print("Claimed value wrong: expected {}, claimed {}.".format(expected_claim_amount, claimed_amount))
    elif not quiet:
        print("Claimed value correct: {}.".format(claimed_amount))

    if quiet:
        return fails
    else:
        if fails == 0:
            pprint("Claim transaction appears valid. All 3 checks passed.")
        else:
            ei.print_red("Claim transactions appears invalid. Checks failed: {} from 3.".format(fails))


def sort_address_items(addresses: list, debug: bool=False) -> list:
    # this requires that "address" is a key in all entries!
    if debug:
        print("Sorting addresses ...")
    named = []
    unnamed = []
    for item in addresses:
        if "label" in item and item["label"] not in (None, ""):
            named.append(item)
        else:
            unnamed.append(item)
    named.sort(key=lambda x: x["label"])
    unnamed.sort(key=lambda x: x["address"])
    sorted_addresses = named + unnamed
    return sorted_addresses

def decode_card(op_return_output):
    try:
        encoded = op_return_output["scriptPubKey"]["hex"]
        script = NulldataScript.unhexlify(encoded).decompile().split(' ')[1]
    except:
        raise eh.PacliDataError("Incorrect OP_RETURN output. Re-check the transaction, it may be corrupted.")

    return parse_card_transfer_metainfo(bytes.fromhex(script),
                                            Settings.deck_version)

def read_all_tx_opreturns(txid: str=None, tx: str=None):
    if txid and not tx:
        tx = provider.getrawtransaction(txid, 1)
    opreturns = {}
    for n, output in enumerate(tx["vout"]):
        try:
            opreturn = read_tx_opreturn(output)
            opreturns.update({n : opreturn})
        except:
            pass
    return opreturns

def min_amount(amount_type: str, network_name: str=Settings.network) -> Decimal:
    netparams = net_query(network_name)
    if amount_type == "tx_fee":
        return netparams.min_tx_fee
    min_value = dmu.sats_to_coins(legacy_mintx(network_name), network_name=network_name)
    if not min_value:
        min_value = net_query(network_name).from_unit
    if amount_type == "op_return_value":
        if is_legacy_blockchain(network_name, "nulldata"):
            return min_value
        else:
            return 0

    elif amount_type == "output_value":
        return min_value

def check_tx_acceptance(txid: str, tx_hex: str, quiet: bool=False):
    # checks if a tx was accepted by the client
    try:
        mempool = provider.getmemorypool()
        mempooltxes = mempool["transactions"]
        if tx_hex in mempooltxes:
            return True
    except AttributeError:
        mempooltxes = None # coin doesn't support getmemorypool command
    except KeyError:
        if mempool.get("code") == -9:
            if not quiet:
                ei.print_red("Warning: Client is not connected. Check your internet connection or connect manually to a node. Broadcasting the transaction will probably take longer than expected.")
                ei.print_red("Use the 'sendrawtransaction' command with the complete transaction hex string (get it with the 'getrawtransaction' command of your cryptocurrency client if you only have the TXID) to broadcast it manually.")
        mempooltxes = None # means there was no access to the mempool. Thus if the tx was not found, it should be confirmed or rejected.

    txtest = provider.getrawtransaction(txid, 1)
    if "information" in txtest:
        return False
    if (mempooltxes is not None) and (tx_hex not in mempooltxes) and ("confirmations" not in txtest):
        return False
    else:
        return True

def check_extradata_hash(stored_hash: bytes, origstring: str, quiet: bool=False, debug: bool=False) -> None:

    if not quiet:
        print("Original string:")
        print(origstring)
        print("Stored hash (hex):")
        print(stored_hash.hex())
    s256hash = hashlib.sha256()
    s256hash.update(str(origstring).encode())
    correct_hash = s256hash.digest()
    correct_hash_hex = s256hash.hexdigest()
    if debug:
        print("Hashing data:", origstring)
        print("SHA256 hash:", correct_hash, "Hex:", correct_hash_hex)

    if stored_hash == correct_hash:
        if not quiet:
            print("Hash is correct.")
        else:
            return 0
    else:
        if not quiet:
            ei.print_red("Hash incorrect. Correct hash: {}".format(correct_hash_hex))
        else:
            return 1

def calc_cardtransfer_fees(network: str=Settings.network, legacyfix: bool=False):
    # legacyfix option added to be able to use this for regular card transfers who use the flawed vanilla algorithm (who needs 1 output more)
    min_output = min_amount("output_value", network)
    min_tx_fee = min_amount("tx_fee", network)
    min_opreturn = min_amount("op_return_value", network)
    all_fees = min_output * 2 + min_opreturn + min_tx_fee # p2th, PA transfer fee, op_return, tx_fee
    if legacyfix is True:
        all_fees += min_output
    return all_fees


def filter_confirmed_txes(txdict: dict, minconf: int=1, debug: bool=False):
    # takes a list of txes in a dict in format label: txhex
    # and filters all txes out with > minconf confirmations
    for label, txhex in txdict.items():
        try:
            tx_json_raw = provider.decoderawtransaction(txhex)
            tx_json = provider.getrawtransaction(tx_json_raw["txid"], 1)
            if int(tx_json["confirmations"]) >= minconf:
                yield {"label" : label, "txhex" : txhex}
        except Exception as e:
            if debug:
                print("Exception:", e)

def prune_confirmed_stored_txes(minconf: int=1, now: bool=False, debug: bool=False):
    txdict = ce.list("transaction", debug=debug, quiet=True)
    for item in filter_confirmed_txes(txdict, minconf=minconf, debug=debug):
        label = item["label"] # a bit ugly!
        # (category: str, label: str, now: bool=False, debug: bool=False)
        ce.delete("transaction", label, now=now, debug=debug)




