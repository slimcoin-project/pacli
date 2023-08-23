import time
from decimal import Decimal
import pypeerassets as pa
from typing import Optional, Union
from prettyprinter import cpprint as pprint
from pypeerassets.transactions import sign_transaction
from pypeerassets.networks import net_query
from pypeerassets.at.protobuf_utils import serialize_deck_extended_data
from pypeerassets.at.constants import ID_AT, ID_DT
from pypeerassets.pautils import amount_to_exponent, exponent_to_amount
import pypeerassets.at.dt_misc_utils as dmu # TODO: refactor this, the "sign" functions could go into the TransactionDraft module.
import pacli.config_extended as ce
import pacli.extended_interface as ei
from pacli.provider import provider
from pacli.config import Settings
from pacli.utils import (sendtx, cointoolkit_verify)

# Utils which are used by both at and dt (and perhaps normal) tokens.

def create_deckspawn_data(identifier, epoch_length=None, epoch_reward=None, min_vote=None, sdp_periods=None, sdp_deckid=None, at_address=None, multiplier=None, addr_type=2, startblock=None, endblock=None):

    # note: we use an additional identifier only for this function, to avoid having to import extension
    # data into __main__.

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


def list_decks(identifier: str="dt"):
    # quick workaround for the problem that we don't want too much extension stuff in __main__.
    at_type = { "at" : ID_AT, "dt" : ID_DT }
    return dmu.list_decks_by_at_type(provider, at_type[identifier])

def init_deck(network, deckid, rescan=True):
    deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
    if deckid not in provider.listaccounts():
        provider.importprivkey(deck.p2th_wif, deck.id, rescan)
        print("Importing P2TH address from deck.")
    else:
        print("P2TH address was already imported.")
    check_addr = provider.validateaddress(deck.p2th_address)
    print("Output of validation tool:\n", check_addr)

def signtx_by_key(rawtx, label=None, key=None):
    # Allows to sign a transaction with a different than the main key.

    if not key:
        try:
           key = get_key(label)
        except ValueError:
           raise ei.PacliInputDataError("No key nor label provided.")

    return sign_transaction(provider, rawtx, key)

def get_input_types(rawtx):
    # gets the types of ScriptPubKey inputs of a transaction.
    # Not ideal in terms of resource consumption/elegancy, but otherwise we would have to change PeerAssets core code,
    # because it manages input selection (RpcNode.select_inputs)
    input_types = []
    try:
        for inp in rawtx.ins:
            prev_tx = provider.getrawtransaction(inp.txid, 1)
            prev_out = prev_tx["vout"][inp.txout]
            input_types.append(prev_out["scriptPubKey"]["type"])

        return input_types

    except KeyError:
        raise ei.PacliInputDataError("Transaction data not correctly given.")


def finalize_tx(rawtx: dict, verify: bool=False, sign: bool=False, send: bool=False, confirm: bool=False, redeem_script: str=None, label: str=None, key: str=None, input_types: list=None, ignore_checkpoint: bool=False, save: bool=False, debug: bool=False, silent: bool=False) -> object:
    # Important function called by all AT, DT and Dex transactions and groups several checks and the last steps (signing) together.

    if not ignore_checkpoint:
        # if a reorg/orphaned checkpoint is detected, require confirmation to continue.
        if reorg_check(silent=silent) and not confirm_continuation():
            return
        store_checkpoint(silent=silent)

    if verify:
        print(
            cointoolkit_verify(rawtx.hexlify())
             )  # link to cointoolkit - verify

    if (False in (sign, send)) and (not silent):
        print("NOTE: This is a dry run, your transaction will still not be broadcasted.\nAdd --sign --send to the command to broadcast it")

    dict_key = 'hex' # key of dict returned to the user.

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
        else:
            if input_types is None:
                input_types = get_input_types(rawtx)

            if "pubkey" not in input_types:
                tx = sign_transaction(provider, rawtx, Settings.key)
            else:
                tx = dmu.sign_mixed_transaction(provider, rawtx, Settings.key, input_types)

        if send:
            if not silent:
                pprint({'txid': sendtx(tx)})
            else:
                sendtx(tx)
            if confirm:
                ei.confirm_tx(tx, silent=silent)

        tx_hex = tx.hexlify()

        # return {'hex': tx.hexlify()}

    elif send:
        # this is when the tx is already signed (DEX use case)
        sendtx(rawtx)
        tx_hex = rawtx.hexlify()

        if confirm:
            ei.confirm_tx(tx, silent=silent)

        # return {'hex': rawtx.hexlify()}
    else:
        dict_key = 'raw hex'
        tx_hex = rawtx.hexlify()
        # return {'raw hex' : rawtx.hexlify()}

    if save:
        try:
            assert True in (sign, send) # even if an unsigned tx gets a txid, it doesn't make sense to save it
            txid = tx["txid"] if tx is not None else rawtx["txid"]
        except (KeyError, AssertionError):
            raise PacliInputDataError("You can't save a transaction which was not at least partly signed.")
        else:
            save_transaction(txid, tx_hex)


    return { dict_key : tx_hex }

def get_wallet_transactions(fburntx: bool=False):
    start = 0
    raw_txes = []
    while True:
        new_txes = provider.listtransactions(many=999, since=start, fBurnTx=fburntx) # option fBurnTx=burntxes doesn't work as expected
        raw_txes += new_txes
        if len(new_txes) == 999:
            start += 999
        else:
            break
    return raw_txes

def find_transaction_by_string(searchstring: str, only_start: bool=False):

    wallet_txids = set([tx.txid for tx in get_wallet_transactions()])
    for txid in wallet_txids:
       if (only_start and txid.startswith(searchstring)) or (searchstring in txid and not only_start):
           break
    return txid

def advanced_card_transfer(deck: object=None, deckid: str=None, receiver: list=None, amount: list=None,
                 asset_specific_data: str=None, locktime: int=0, verify: bool=False, change_address: str=Settings.change,
                 sign: bool=False, send: bool=False, debug: bool=False, silent: bool=False, confirm: bool=False) -> Optional[dict]:
    # allows some more options, and to use P2PK inputs.

    if not deck:
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

    if isinstance(deck, pa.Deck):
        card = pa.CardTransfer(deck=deck,
                               receiver=receiver,
                               amount=[amount_to_exponent(i, deck.number_of_decimals)
                                       for i in amount],
                               version=deck.version,
                               asset_specific_data=asset_specific_data
                               )

    else:

        raise ei.PacliInputDataError({"error": "Deck {deckid} not found.".format(deckid=deckid)})

    issue_tx = pa.card_transfer(provider=provider,
                                 inputs=provider.select_inputs(Settings.key.address, 0.02),
                                 card=card,
                                 change_address=change_address,
                                 locktime=locktime
                                 )

    return finalize_tx(issue_tx, verify=verify, sign=sign, send=send, silent=silent, confirm=confirm, debug=debug)


def advanced_deck_spawn(name: str, number_of_decimals: int, issue_mode: int, asset_specific_data: bytes, change_address: str=Settings.change,
                        verify: bool=False, sign: bool=False, send: bool=False, locktime: int=0) -> None:
    # idem card transfer, allows p2pk inputs.

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
    return finalize_tx(spawn_tx, verify, sign, send)


def store_checkpoint(height: int=None, silent: bool=False) -> None:
    if height is None:
        height = provider.getblockcount()
    blockhash = provider.getblockhash(height)
    if not silent:
        print("Storing hash of block as a checkpoint to control re-orgs.\n Height: {} Hash: {}".format(height, blockhash))
    try:
        ce.write_item(category="checkpoint", key=height, value=blockhash)
    except ei.ValueExistsError:
        if not silent:
            print("Checkpoint already stored (probably node block height has not changed).")

def retrieve_checkpoint(height: int=None, silent: bool=False) -> dict:
    config = ce.get_config()
    bheights = sorted([ int(h) for h in config["checkpoint"] ])
    if height is None:
        # default: show latest checkpoint
        height = max(bheights)
    else:
        height = int(height)
        if height not in bheights:
            # if height not in blockheights, show the highest below it
            for i, h in enumerate(bheights):
                if h > height:
                    new_height = bheights[i-1]
                    break
            else:
                # if the highest checkpoint is below the required height, use it
                new_height = bheights[-1]

            if not silent:
                print("No checkpoint for height {}, closest (lower) checkpoint is: {}".format(height, new_height))
            height = new_height

    return {height : config["checkpoint"][str(height)]}

def retrieve_all_checkpoints() -> dict:
    config = ce.get_config()
    return config["checkpoint"]

def prune_old_checkpoints(depth: int=2000, silent: bool=False) -> None:
    checkpoints = [int(cp) for cp in ce.get_config()["checkpoint"].keys()]
    checkpoints.sort()
    # print(checkpoints)
    current_block = provider.getblockcount()
    index = 0
    while len(ce.get_config()["checkpoint"]) > 5: # leave at least 5 checkpoints intact
       c = checkpoints[index]
       if c < current_block - depth:
           if not silent:
               print("Deleting checkpoint", c)
           ce.delete_item("checkpoint", str(c), now=True, silent=True)
           time.sleep(1)
       else:
           break # as checkpoints are sorted, we break out.
       index += 1

def reorg_check(silent: bool=False) -> None:
    if not silent:
        print("Looking for chain reorganizations ...")
    config = ce.get_config()

    try:
        bheights = sorted([ int(h) for h in config["checkpoint"] ])
        last_height = bheights[-1]
    except IndexError: # first reorg check
        if not silent:
            print("A reorg check was never performed on this node.")
            print("Saving first checkpoint.")
        return 0

    stored_bhash = config["checkpoint"][str(last_height)]

    if not silent:
        print("Last checkpoint found: height {} hash {}".format(last_height, stored_bhash))
    checked_bhash = provider.getblockhash(last_height)
    if checked_bhash == stored_bhash:
        if not silent:
            print("No reorganization found. Everything seems to be ok.")
        return 0
    else:
        if not silent:
            print("WARNING! Chain reorganization found.")
            print("Block hash for height {} in current blockchain: {}".format(last_height, checked_bhash))
            print("This is not necessarily an attack, it can also occur due to orphaned blocks.")
            print("Make sure you check token balances and other states.")
        return 1

def confirm_continuation() -> bool:
    print("Enter 'yes' to confirm to continue")
    cont = input()
    if cont == "yes":
        return True
    else:
        return False


def get_safe_block_timeframe(period_start, period_end, security_level=1):
    # looks for a safe blockheight to make attacks less likely.
    # security_level:
    # 0 is very risky (5 to 95%, no minimum distance in blocks to period border)
    # 1 is default (10 to 90%, 25 blocks minimum, equivalent to the recommended number of confirmations)
    # 2 is safe (20 to 80%, 50 blocks minimum)
    # 3 is very safe (30 to 70%, 100 blocks minimum)
    # 4 is optimal (50%), always in the block closest to the middle of each period
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

def save_transaction(identifier: str, tx_hex: str, partly: bool=False) -> None:
    # partly indicates partly signed transactions, which will be stored in the txhex category.
    # the identifier can be a txid or (in the case of partly signed transactions) an arbitrary string.
    cat = "txhex" if partly else "transaction"
    ce.write_item(cat, identifier, tx_hex)
    if not silent:
        print("Transaction {} saved. Retrieve it with 'pacli tools show_transaction TXID'.".format(txid))

def search_for_stored_tx_label(category: str, identifier: str, silent: bool=False) -> str:
    # if the identifier is a label stored in the extended config file, return the associated txid.
    # the try-except clause returns the identifier if it's already in txid format.

    if is_possible_txid(identifier):
        return identifier
    else:

        result = ce.read_item(category, identifier)

        if result is not None:
            if is_possible_txid(result):
                if not silent:
                    print("Using {} stored with label {} and ID {}.".format(category, identifier, result))
                return result
            else:
                raise ei.PacliInputDataError("The string stored for this label is not a valid transaction ID. Check if you stored it correctly.")
        else:
            raise ei.PacliInputDataError("Label not found.")

def is_possible_txid(txid: str) -> bool:
    try:

        assert len(txid) == 64
        hexident = int(txid, 16)
        return True

    except (ValueError, AssertionError):
        return False

def find_tx_senders(tx: dict) -> list:
    # find_tx_sender from pypeerassets only finds the first sender.
    # this variant returns a list of all input senders.

    senders = []
    for vin in tx["vin"]:
        try:
            sending_tx = provider.getrawtransaction(vin["txid"], 1)
            vout = vin["vout"]
            sender = sending_tx["vout"][vout]["scriptPubKey"]["addresses"]
            value = sending_tx["vout"][vout]["value"]
            senders.append({"sender" : sender, "value" : value})
        except KeyError: # coinbase transactions
            continue
    return senders

def get_address_token_balance(deck: object, address: str) -> Decimal:

    cards = pa.find_all_valid_cards(provider, deck)
    state = pa.protocol.DeckState(cards)

    for i in state.balances:
        if i == address:
            return exponent_to_amount(state.balances[i], deck.number_of_decimals)
    else:
        return 0

def get_wallet_token_balances(deck: object, addrdict: dict, use_addresses: bool=True) -> dict:

    cards = pa.find_all_valid_cards(provider, deck)
    state = pa.protocol.DeckState(cards)

    balances = {}
    for i in state.balances:
        for full_label in addrdict:
            address = addrdict[full_label]
            if i == address:
                if use_addresses:
                    balances.update({address : exponent_to_amount(state.balances[i], deck.number_of_decimals)})
                else:
                    prefix = Settings.network + "_"
                    # workaround until keystore_extended is finally removed
                    # remove key_, but only if it's at the start.
                    if full_label[:4] == "key_":
                        full_label = full_label[4:]
                    label = full_label.replace(prefix, "")
                    balances.update({label : exponent_to_amount(state.balances[i], deck.number_of_decimals)})
    return balances

