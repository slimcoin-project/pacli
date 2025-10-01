# this file bundles all x-specific (exchange) commands.
# SECOND version, where the exchange is initiated by the card seller, not the coin seller.

from binascii import hexlify, unhexlify
from prettyprinter import cpprint as pprint
from pacli.config import Settings
from pacli.provider import provider
from pacli.utils import sendtx
from pypeerassets.kutil import Kutil
from pypeerassets.protocol import Deck, CardTransfer
from btcpy.structs.sig import Sighash, P2pkSolver, P2pkhSolver
from btcpy.structs.transaction import ScriptSig, Locktime
from btcpy.lib.parsing import Parser, Stream # only for tests
from pypeerassets.provider.rpcnode import Sequence
import pypeerassets as pa
from pypeerassets.pautils import amount_to_exponent, exponent_to_amount
import pypeerassets.at.dt_misc_utils as dmu
import pypeerassets.hash_encoding as henc
import json
from decimal import Decimal
import pacli.extended_utils as eu
import pacli.extended_interface as ei
import pacli.blockexp_utils as bxu
from pypeerassets.pa_constants import param_query
from pypeerassets.networks import net_query
from pypeerassets.transactions import Transaction, MutableTransaction, MutableTxIn, tx_output, p2pkh_script, nulldata_script, make_raw_transaction


def card_lock(deckid: str, amount: str, lock: int, receiver: str=Settings.key.address, lockaddr: str=None, change: str=None, addrtype: str=None, absolute: bool=False, confirm: bool=False, sign: bool=True, send: bool=True, txhex: bool=False, force: bool=False, quiet: bool=False, debug: bool=False):

    # NOTE: cards are always locked at the receiver's address of the CardLock, like in CLTV.
    # returns a dict to be passed to self.card_transfer as kwargs
    change_address = Settings.change if change is None else change
    card_sender = Settings.key.address
    if not eu.is_mine(receiver) and not force:
        raise ei.PacliDataError("The receiver address {} is not part of your wallet. If you really want to transfer the coins to another wallet or person while locking, use the --force option.".format(receiver))

    quiet = True if True in (quiet, txhex) else False
    current_blockheight = provider.getblockcount()
    if absolute is True:
        locktime = lock
        if lock < current_blockheight:
             raise ei.PacliInputDataError("Aborted. Your chosen locktime {} is in the past. Current blockheight: {}".format(lock, current_blockheight))
    else:
        locktime = lock + current_blockheight
    if (locktime - current_blockheight) < 100 and not force:
        raise ei.PacliInputDataError("Aborted. Locktime is too low (< 100 blocks in the future). By default, a token buyer will not accept that lock. Use --force to override this check, e.g. if there is some trust between buyer and seller.")

    if not quiet:
        print("Locking tokens until block {} (current blockheight: {})".format(locktime, current_blockheight))
    try:
        lockhash_type = henc.HASHTYPE.index(addrtype)
    except IndexError:
        print("Address type incorrect. Supported types:", ", ".join(henc.HASHTYPE))
    if lockaddr is not None:
        if addrtype in ("p2pkh", "p2sh"):
           lockhash = henc.address_to_hash(lockaddr, lockhash_type, net_query(provider.network))
        else:
           print("Segwit, Taproot and hashlocks still not supported.")
           raise NotImplementedError

    deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
    unit_amount = amount_to_exponent(Decimal(amount), deck.number_of_decimals)

    if not force: # balance check, can be overridden with --force
        if not quiet:
            print("Checking balance and possible unavailable locked tokens ...")
        cards = pa.find_all_valid_cards(provider, deck)
        state = pa.protocol.DeckState(cards, cleanup_height=current_blockheight, debug=debug)
        balance = state.balances.get(card_sender, 0)
        locked_units = get_locked_amount(state.locks, card_sender)
        available_token_units = balance - locked_units
        if debug:
            print("Available token units: {} Token units to lock: {}".format(available_token_units, unit_amount))
        if unit_amount > available_token_units:
            balance_tokens = exponent_to_amount(balance, deck.number_of_decimals)
            locked_tokens = exponent_to_amount(locked_units, deck.number_of_decimals)
            available_tokens = exponent_to_amount(available_token_units, deck.number_of_decimals)
            raise ei.PacliDataError("Not enough tokens: Total balance: {}, Locked: {}, required: {}. Locked tokens can't be used for new locks.".format(balance_tokens, locked_tokens, amount))

    if isinstance(deck, pa.Deck):
        card = pa.CardTransfer(deck=deck,
                               sender=card_sender,
                               receiver=[receiver],
                               amount=[unit_amount],
                               version=deck.version,
                               locktime=locktime,
                               lockhash=lockhash,
                               lockhash_type=lockhash_type
                               )

    issue = pa.card_transfer(provider=provider,
                             inputs=provider.select_inputs(Settings.key.address, 0.03),
                             card=card,
                             change_address=change_address,
                             )

    return ei.output_tx(eu.finalize_tx(issue, verify=False, sign=sign, send=send, ignore_checkpoint=force, confirm=confirm), txhex=txhex)

# main function to be changed:
# - coinseller_address (formerly partner_address) is now the card receiver.
# - change of coinseller input must go to coinseller address.

def build_coin2card_exchange(deckid: str, coinseller_address: str, coinseller_input: str, card_amount: Decimal, coin_amount: Decimal, coinseller_change_address: str=None, save_identifier: str=None, sign: bool=False, debug: bool=False):
    # TODO: this should also get a quiet option, with the TXHEX stored in the extended config file.
    # the card seller builds the transaction
    my_key = Settings.key
    my_address = my_key.address
    my_change_address = Settings.change
    deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
    card = pa.CardTransfer(deck=deck,
                           sender=my_address,
                           receiver=[coinseller_address],
                           amount=[amount_to_exponent(card_amount, deck.number_of_decimals)])

    # coinseller can submit another change address if he wants, otherwise cardseller sends it to the coinseller addr.
    if coinseller_change_address is None:
        coinseller_change_address = coinseller_address

    print("Token seller:", card.sender, "Token buyer:", card.receiver[0])
    print("Change of the coins sold will be sent to address", coinseller_change_address)

    coinseller_input_values = coinseller_input.split(":")
    coinseller_input_txid, coinseller_input_vout = coinseller_input_values[0], int(coinseller_input_values[1])
    # coinseller's input becomes second input, as first must be card sender.
    coinseller_input = build_input(coinseller_input_txid, coinseller_input_vout)
    amount_str = str(provider.getrawtransaction(coinseller_input_txid, 1)["vout"][coinseller_input_vout]["value"])
    coinseller_input_amount = Decimal(amount_str)
    if coinseller_input_amount < coin_amount:
        raise ei.PacliInputDataError("The input provided by the token buyer has a lower balance than the requested payment (available amount: {}, requested payment {})".format(coinseller_input_amount, coin_amount))
    # first input comes from the card seller (i.e. the user who signs here)
    # We let pacli chose it automatically, based on the minimum amount. It should never give more than one, but it wouldn't matter if it's two or more.
    try:
        utxo = select_utxos(minvalue=Decimal("0.01"), address=my_address, utxo_type="pubkeyhash", quiet=True, debug=debug)[0] # first usable utxo is selected
    except IndexError:
        raise ei.PacliDataError("Not enough funds. Send enough coins to this address ({}) to pay the transaction fee.\nNOTE: If you have only mined coins on this address, you will have to transfer additional coins to it, as coinbase inputs can't be used for swaps due to an upstream bug (you can also send the coins to yourself).".format(my_address))
    utxo_value = Decimal(str(utxo["amount"]))
    own_input = MutableTxIn(txid=utxo['txid'], txout=utxo['vout'], sequence=Sequence.max(), script_sig=ScriptSig.empty())
    inputs = {"utxos" : [own_input, coinseller_input], "total": coinseller_input_amount + utxo_value}
    utxos = inputs["utxos"]

    unsigned_tx = create_card_exchange(inputs=inputs,
                                 card=card,
                                 coinseller_change_address=coinseller_change_address,
                                 coin_value=coin_amount,
                                 first_input_value=utxo_value,
                                 cardseller_change_address=my_change_address,
                                 debug=debug
                                 )

    network_params = net_query(provider.network)
    # print(network_params)
    # lock check: tokens need to be locked until at least 100 blocks (default) in the future
    print("Checking token balance ...")
    token_balance = eu.get_address_token_balance(deck, my_address)
    if token_balance < card_amount:
        raise ei.PacliDataError("Not enough token balance (balance: {}, required: {}).".format(token_balance, card_amount))
    print("Token balance of the sender:", token_balance)
    print("Checking locks ...")
    lockcheck_passed = check_lock(deck, my_address, coinseller_address, card_amount, blockheight=provider.getblockcount(), limit=100, debug=debug)
    if not lockcheck_passed:
        print("WARNING: Lock check failed, tokens were not properly locked before the swap creation (minimum: 100 blocks in the future). The buyer will probably reject the swap. You can still lock the coins after creating the hex string.")
    else:
        print("Lock check passed: Enough tokens are on the sender's address and properly locked.")


    if sign:
        # sighash has be ALL, otherwise the counterparty could modify it, and anyonecanpay must be False.
        for i in range(len(utxos) - 1): # we sign all inputs minus the last one which is from the coin_seller.
            if debug:
                print("Signing utxo", utxos[i])
            result = solve_single_input(index=i, prev_txid=utxos[i].txid, prev_txout_index=utxos[i].txout, key=Settings.key, network_params=network_params, debug=debug)
            unsigned_tx.spend_single(index=i, txout=result["txout"], solver=result["solver"])

        print("The following hex string contains the transaction which you signed with your keys only. Transmit it to your exchange partner via any messaging channel (there's no risk of your tokens or coins to be stolen).\n")
        tx_hex = unsigned_tx.hexlify()
        print(tx_hex) # prettyprint makes it more difficult to copy it
        if not lockcheck_passed:
            ei.print_red("\nNOTE: Before transmitting the hex string to the token buyer, lock the tokens with the following command:")
            ei.print_red("'pacli swap lock {} {} {}'.".format(deckid, str(card_amount), coinseller_address))
        if save_identifier:
            eu.save_transaction(save_identifier, tx_hex, partly=True)
    else:
        return unsigned_tx.hexlify()


def build_input(input_txid: str, input_vout: int):

    return MutableTxIn(txid=input_txid, txout=input_vout, script_sig=ScriptSig.empty(), sequence=Sequence.max())


def finalize_coin2card_exchange(txstr: str, confirm: bool=False, force: bool=False, send: bool=False, txhex: bool=False, quiet: bool=False, debug: bool=False):
    quiet = True in (quiet, txhex)
    # this is signed by the coin vendor. Basically they add their input and solve it.
    network_params = net_query(provider.network)
    tx = MutableTransaction.unhexlify(txstr, network=network_params)

    my_input = tx.ins[-1] # the coin seller's input is the last one
    my_input_index = len(tx.ins) - 1
    if not quiet:
        print("Index for the coin seller's input:", my_input_index)
    result = solve_single_input(index=my_input_index, prev_txid=my_input.txid, prev_txout_index=my_input.txout, key=Settings.key, network_params=network_params, quiet=quiet)
    tx.spend_single(index=my_input_index, txout=result["txout"], solver=result["solver"])

    return ei.output_tx(eu.finalize_tx(tx, verify=False, sign=False, send=send, ignore_checkpoint=force, confirm=confirm, quiet=quiet, debug=debug), txhex=txhex)

def solve_single_input(index: int, prev_txid: str, prev_txout_index: int, key: Kutil, network_params: tuple, sighash: str="ALL", anyonecanpay: bool=False, quiet: bool=False, debug: bool=False):

    if not quiet:
        print("Signing input {} from transaction {}, output {}".format(index, prev_txid, prev_txout_index))
    prev_tx_string = provider.getrawtransaction(prev_txid)
    prev_tx_json = provider.decoderawtransaction(prev_tx_string) # this workaround works! why?
    """#prev_tx_json = provider.getrawtransaction(utxos[i].txid, 1)
            # TODO: taking json directly from getrawtransaction gives an error: "txid not matching transaction data". Probably something related to network.
            # probably something with decimal places: we have 299.93 in the original tx, and 29993 in the "code" the error throws out. TXID changes in the "code" to 5994167b4a4210c8f87ef9bcf49ddb77d477b26f42bb2ab53d6d174a2a213b00.
            # ??? after "network" was added to TxOut.from_json, txid changes to dadb2e261edd52ac2afe6c032d0e1f24f94e1d56c4f8e037b33e508c90958eca and amounts are now correct, but error stays.
            # (this should be correct bugfix, because BaseTrackedTransaction.from_json did the same thing.
            # SlimcoinTxOut didn't change anything (was expected).
            # now it is possible that tx_output from PeerAssets contains a "hack" where the values are changed, to "override" network=network in TxIn.from_json. It would be interesting if if I do TxOut.from_json instead of tx_output, what happens.
            # difference also in "time" variable:
            # <     "time" : 1660024088, (with 1)
            # >     "time" : 1660024011, (without 1)
            # it seems 88 is the block time, in the original 11 is "time" and 88 "blocktime".
            # start of the string (only difference!):
            # 01000000cbf4f16... when using getrawtransaction without "1"
            # 0100000018f5f16 ... when using with 1, and then from_json tries to encode it again ..."""
    #print(str(provider), provider.__dict__)
    if debug:
        print("Previous transaction's JSON:", prev_tx_json)
    # TODO: this seems to have difficulties with Coinbase TXins. Re-check later. # NOTE: for now the previous step ignores utxos with coinbase txes.
    #print("tx string", provider.getrawtransaction(prev_txid, 0))
    #print(prev_tx_json.get("time"), prev_tx_json.get("blocktime"))
    try:
        assert "coinbase" not in prev_tx_json["vin"][0]
    except AssertionError:
        raise ei.PacliDataError("UTXOs coming from coinbase transactions are not supported due to a bug in the btcpy library. Please select another input.")
    except KeyError:
        raise ei.PacliDataError("Broken transaction:", prev_txid)

    prev_tx = Transaction.from_json(prev_tx_json, network=network_params)
    prev_txout = prev_tx.outs[prev_txout_index]

    if prev_txout.type == "p2pk":
        solver = P2pkSolver(key._private_key, sighash=Sighash(sighash, anyonecanpay))
    elif prev_txout.type == "p2pkh":
        solver = P2pkhSolver(key._private_key, sighash=Sighash(sighash, anyonecanpay))
    else:
        raise ValueError("TX type unknown or not implemented.")
    return { "txout" : prev_txout, "solver" : solver }


def create_card_exchange(card: CardTransfer, inputs: dict, coinseller_change_address: str, cardseller_change_address: str, coin_value: Decimal, first_input_value: Decimal, locktime: int=0, debug: bool=False) -> Transaction:
    # extended version of card_transfer which allows to add another output to the other party,
    # and allows signing only a part of the inputs.

    '''Prepare the CardTransfer Transaction object

       : card - CardTransfer object
       : inputs - utxos (first has to be owned by card issuer)
       : change_address - address to send the change to
       : locktime - tx locked until block n=int
       '''

    network_params = net_query(provider.network)
    pa_params = param_query(provider.network)

    ### LEGACY SUPPORT for blockchains where no 0-value output is permitted ###
    from pypeerassets.legacy import is_legacy_blockchain

    if is_legacy_blockchain(network_params.shortname, "nulldata"):
        # could perhaps be replaced with get_dust_threshold?
        min_value = network_params.min_tx_fee
    else:
        min_value = Decimal(0)

    if card.deck_p2th is None:
        raise Exception("card.deck_p2th required for tx_output")

    # TODO: we could unify outputs 3 and 4, at least if the card seller doesn't need a different change address.
    # This would make the transaction "less transparent", but make the transaction footprint smaller.
    outs = [
        tx_output(network=provider.network,
                  value=pa_params.P2TH_fee,
                  n=0, script=p2pkh_script(address=card.deck_p2th,
                                           network=provider.network)),  # deck p2th
        tx_output(network=provider.network,
                  value=min_value, n=1,
                  script=nulldata_script(card.metainfo_to_protobuf)),  # op_return

        tx_output(network=provider.network, value=min_value, n=2, # card transfer to coin sender/card receiver
                  script=p2pkh_script(address=card.receiver[0],
                                      network=provider.network)),

        tx_output(network=provider.network, value=coin_value, n=3, # coin transfer to coin receiver/card sender
                  script=p2pkh_script(address=card.sender,
                                      network=provider.network)),

        tx_output(network=provider.network, value=first_input_value, n=4, # change coins back to card sender
                  script=p2pkh_script(address=cardseller_change_address,
                                      network=provider.network))
    ]


    # TODO: this is probably not blockchain agnostic, as P2TH outputs can't be nonzero even in non-legacy blockchains.
    total_min_values = 2 * min_value # includes P2TH output + zero outputs to receivers

    #  first round of txn making is done by presuming minimal fee
    change_sum = Decimal(inputs['total'] - network_params.min_tx_fee - pa_params.P2TH_fee - first_input_value - coin_value - total_min_values)

    if change_sum > 0:

        outs.append(
            tx_output(network=provider.network,
                      value=change_sum, n=len(outs)+1,
                      script=p2pkh_script(address=coinseller_change_address,
                                          network=provider.network))
            )

    unsigned_tx = make_raw_transaction(network=provider.network,
                                       inputs=inputs["utxos"],
                                       outputs=outs,
                                       locktime=Locktime(locktime)
                                       )
    return unsigned_tx


def select_utxos(minvalue: Decimal,
                 address: str=None,
                 minconf: int=1,
                 maxconf: int=99999999,
                 maxvalue: object=None,
                 utxo_type: str=None,
                 show_address: bool=False,
                 ignore_coinbase: bool=True,
                 quiet: bool=False,
                 debug: bool=False):

    # NOTE: due to btcpy bug, UTXOs coming from coinbase transactions can't be supported currently.
    # Once the problem is solved, the ignore_coinbase flag can be set to False.

    utxos = provider.listunspent(address=address, minconf=minconf, maxconf=maxconf)
    selected_utxos = []

    for utxo in utxos:
        if minvalue is not None and utxo["amount"] < minvalue:
            continue
        if maxvalue is not None and utxo["amount"] > maxvalue:
            continue
        if utxo_type is not None or show_address is True:
            utxo_tx = provider.getrawtransaction(utxo["txid"], 1)
            if utxo_type:
                utype = utxo_tx["vout"][utxo["vout"]]["scriptPubKey"]["type"]
            if show_address:
                uaddr = utxo_tx["vout"][utxo["vout"]]["scriptPubKey"]["addresses"]
                utxo.update({"address" : uaddr})

            if ignore_coinbase and ("coinbase" in utxo_tx["vin"][0]):
                if debug:
                    print("UTXOs from tx {} ignored: coinbase transactions not supported.".format(utxo["txid"]))
                continue

            if utxo_type != utype:
                if debug:
                    print("UTXO {}:{} ignored: incorrect type ({}) instead of requested {}.".format(utxo["txid"], utxo["vout"], utype, utxo_type))
                continue
        if debug:
            print("UTXO {}:{} appended.".format(utxo["txid"], utxo["vout"]))

        selected_utxos.append(utxo)
    if quiet:
        return selected_utxos
    else:
        if len(selected_utxos) == 0:
            print("No usable utxos found.")
            print("Due to an upstream bug, this can happen if all UTXOs on this address come directly from coinbase outputs (mining or minting).")
            print("You can transfer the needed coins from any source, including the same address.")
            print("If you recently sent coins to this address and they are still not credited, restart the client with the -rescan option.")
            return
        print(len(selected_utxos), "matching utxos found.")
        print("Use this format (TXID:OUTPUT) to initiate a new exchange.")
        for utxo in selected_utxos:
            pprint("{}:{}".format(utxo.get("txid"), utxo.get("vout")))
            print("Amount: {} coins".format(utxo.get("amount")))
            if show_address and "address" in utxo:
                if len(utxo["address"]) == 1:
                    print("Address:", utxo["address"][0])
                else:
                    print("Addresses (e.g. multisig):", utxo["address"])

# locks

def get_locks(deckid: str, blockheight: int, return_deck: bool=False, debug: bool=False):
    deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
    cards = pa.find_all_valid_cards(provider, deck)
    state = pa.protocol.DeckState(cards, cleanup_height=blockheight, debug=debug)
    if return_deck:
        return (state.locks, deck)
    else:
        return state.locks


def prettyprint_locks(locks: dict, blockheight: int, decimals: int=None):
    print("Locks at blockheight {}:".format(blockheight))
    if len(locks) == 0:
        print("No locks found.")
    for address in locks.keys():
        print("Origin address: {}".format(address))
        for lock in locks.get(address):
            print("* Lock until block: {}".format(lock.get("locktime")))
            #try:
            #    lock_address = henc.hash_to_address(lock.get("lockhash"), lock.get("lockhash_type"), net_query(provider.network))
            lock_address = get_lock_address(lock)
            if lock_address is None:
                # except NotImplementedError:
                print("Non-standard lock or address type still not supported. Showing raw data:")
                print("* Lock hash: {}".format(lock.get("lockhash")))
                print("* Lock hash type: {}".format(lock.get("lockhash_type")))
            else:
                print("* Lock address (address to receive the tokens): {}".format(lock_address))
            if decimals:
                lock_amount = exponent_to_amount(lock["amount"], decimals) # Decimal(lock["amount"]) / (10 ** decimals)
                print("* Tokens locked (units): {}".format(lock_amount))
            else:
                print("* Tokens locked (minimum units): {}".format(lock.get("amount")))

def get_lock_address(lock: dict) -> str:
    try:
        lock_address = henc.hash_to_address(lock.get("lockhash"), lock.get("lockhash_type"), net_query(provider.network))
        return lock_address
    except NotImplementedError:
        return None


def get_locked_amount(locks: dict, card_sender: str) -> int:
    locks_on_address = locks.get(card_sender, [])
    locked_amounts = [l["amount"] for l in locks_on_address]
    return sum(locked_amounts)

def check_lock(deck: object, card_sender: str, card_receiver: str, amount: int, blockheight: int, limit: int=None, quiet: bool=False, debug: bool=False):
    # Checks if the lock is correct.
    # NOTE: amount is in token minimum units.
    deckid = deck.id
    decimals = deck.number_of_decimals
    locks = get_locks(deckid, blockheight)
    locktime_limit = blockheight + 100 if limit is None else blockheight + limit
    if debug:
         print("Expected values: sender", card_sender, "receiver", card_receiver, "amount", amount, "deckid", deckid, "block height limit" , locktime_limit)
    # NOTE 2: locktime limit default is blockheight + 100 blocks.
    # check 1: card_sender is the origin_address of the lock
    try:
        sender_locks = locks[card_sender]
        if debug:
            print("Current locks of sender:", card_sender, "for deck:", deckid)
            print(sender_locks)
    except KeyError:
        if not quiet:
            print("Lock check failed: Token seller is not present in the lock dictionary.")
        return False
    # check 2: card_receiver is the lock address and locktime blockheights are far enough in the future

    matching_locks, lock_amount, lock_heights = [], 0, []
    for lock in sender_locks:
        lock_address = get_lock_address(lock)
        formatted_single_lock = exponent_to_amount(lock_amount, decimals)
        if debug:
            print("Checking lock: {} tokens to address {}.".format(formatted_single_lock, lock_address))
        if lock_address == card_receiver:
            if lock["locktime"] < locktime_limit:
                if not quiet:
                    print("Lock of {} tokens ignored as the locktime {} is below the set limit of block {}.".format(formatted_single_lock, lock["locktime"], locktime_limit))
                continue
            matching_locks.append(lock)
            lock_amount += lock["amount"]
            lock_heights.append(lock["locktime"])

    if not matching_locks:
        if not quiet:
            ei.print_red("Lock check failed: No tokens locked to token receiver, or all locks are below the locktime limit.")
        return False
    # check 3: amount is correct
    formatted_lock_amount = exponent_to_amount(lock_amount, decimals)
    if amount > formatted_lock_amount:
        if not quiet:
            ei.print_red("Lock check failed: Locked tokens {}, but swap requires {} tokens.".format(formatted_lock_amount, amount))
        return False

    print("Lock check PASSED. Locked tokens to address {}: {} tokens until at least block {} (limit: {}, current block: {}).".format(card_receiver, formatted_lock_amount, min(lock_heights), locktime_limit, blockheight))
    return True

def check_swap(txhex: str,
               deckid: str=None,
               buyer_change_address: str=None,
               token_receiver_address: str=None,
               amount: str=None,
               token_amount: str=None,
               return_state: bool=False,
               presign_check: bool=False,
               debug: bool=False):
    """bundles most checks for swaps"""
    fail, notmine = False, False
    try:
        txjson = provider.decoderawtransaction(txhex)
        txstruct = bxu.get_tx_structure(tx=txjson, ignore_blockhash=True)
    except:
        raise ei.PacliInputDataError("No valid transaction hex string or label provided.")

    print("Checking swap ...")
    pprint("Senders and receivers of the swap transaction:")
    pprint(txstruct)
    try:
        # Note: outputs 2 and 4 go to the token seller, so they aren't checked here in detail.
        token_seller = txstruct["inputs"][0]["sender"][0]
        token_buyer = txstruct["inputs"][1]["sender"][0]
        amount_provided = Decimal(str(txstruct["inputs"][1]["value"]))
        p2th_address = txstruct["outputs"][0]["receivers"][0]
        token_receiver = txstruct["outputs"][2]["receivers"][0] # was 3

        all_inputs = sum([Decimal(str(i["value"])) for i in txstruct["inputs"]])
        all_outputs = sum([Decimal(str(o["value"])) for o in txstruct["outputs"]])
        tx_fee = all_inputs - all_outputs
        p2th_fee = Decimal(str(txstruct["outputs"][0]["value"]))

        op_return_fee = Decimal(str(txstruct["outputs"][1]["value"]))
        card_transfer_fee = Decimal(str(txstruct["outputs"][2]["value"]))

        all_fees = tx_fee + p2th_fee + op_return_fee + card_transfer_fee

        op_return_output = txjson["vout"][1]
    except (KeyError, IndexError):
        raise ei.PacliDataError("Incorrect transaction structure. Don't proceed with the transaction.")

    try:
        change_receiver = txstruct["outputs"][5]["receivers"][0]
        change_returned = Decimal(str(txstruct["outputs"][5]["value"]))
    except IndexError:
        change_receiver = None
        change_returned = 0


    pprint("Token seller's address: {}".format(token_seller))
    pprint("Token buyer's address: {}".format(token_buyer))
    pprint("Token receiver's address: {}".format(token_receiver))
    # presign check: check if you are currently able to sign the token buyer input
    if presign_check and (token_buyer != Settings.key.address):
        ei.print_red("The token buyer address is not your current Pacli main address, so you will not be able to sign the transaction.")
        ei.print_red("Switch to the correct address with 'pacli address set -a {}' and repeat the command.".format(token_buyer))
        print("Current Pacli main address:", Settings.key.address)
        fail = True
    if token_receiver != token_buyer:
        print("NOTE: The address providing the coins for the swap isn't identic to the address which will receive the tokens.")
        print("This may be intentionally set up by the token buyer, e.g. for privacy reasons.")
        print("If you are the token buyer, make sure the token receiver address {} belongs to you (will be checked in the ownership check).".format(token_receiver))

    if token_receiver_address is not None and (token_receiver != token_receiver_address):
        ei.print_red("The token receiver address you provided in this check isn't the address receiving the tokens in the swap transaction.")
        fail = True
    if change_receiver is not None:
        pprint("Change receiver's address: {}".format(change_receiver))
        pprint("Change returned: {}".format(change_returned))
        if buyer_change_address is not None and (change_receiver != buyer_change_address):
            ei.print_red("The change receiver address you provided in this check isn't the address receiving the change coins in the swap transaction.")
            fail = True
    pprint("Fees paid: {}".format(all_fees))
    paid_amount = amount_provided - change_returned - all_fees
    pprint("Amount paid for the tokens (not including fees): {}".format(paid_amount))
    if amount is not None:
        intended_amount = Decimal(str(amount))
        if intended_amount < paid_amount:
            ei.print_red("The token buyer didn't receive all the change or will pay more than expected.")
            ei.print_red("Missing amount: {}.".format(paid_amount - intended_amount))
            fail = True
        elif intended_amount > paid_amount:
            ei.print_red("The token buyer will receive more coins as change than expected, lowering the payment. Revise your settings for the expected tokens or communicate with the seller if they wanted to concede you a discount, in this case enter this command again with --force (you will not lose coins, but your counterparty may).")
            ei.print_red("Difference: {}.".format(intended_amount - paid_amount))
            fail = True

    for adr in [a for a in (token_receiver, change_receiver) if a is not None]:
        validation = provider.validateaddress(adr)
        if validation.get("ismine") != True:
            notmine = True
            fail = True
    if notmine is True:
        ei.print_red("Ownership check failed: At least one of the addresses which should be under the token buyer's control in this swap (token receiver and change receiver) isn't part of your current wallet.")
        print("This may be intentional if you provided an address of another wallet, or are using this command running the client with a different wallet than the swap's wallet, but can also be a manipulation by the token buyer.")
    else:
        print("Ownership check passed: Both the token receiver and the change address for the provided coins are part of your currently used wallet.")

    card_transfer = eu.decode_card(op_return_output)
    card_amount = card_transfer["amount"][0]
    decimals = card_transfer["number_of_decimals"]
    formatted_card_amount = Decimal(str(exponent_to_amount(card_amount, decimals)))
    if token_amount is not None:
        if formatted_card_amount != Decimal(str(token_amount)):
            fail = True
            ei.print_red("The number of tokens transferred is {}, while the expected token amount is {}.".format(formatted_card_amount, token_amount))
        else:
            print("Token transfer check passed: tokens transferred: {}, expected: {}.".format(formatted_card_amount, token_amount))

    if deckid:
        print("Deck ID and lock check (may take some time) ....")
        matching_decks = eu.find_decks_by_address(p2th_address, addrtype="p2th_main", debug=False)
        deck = matching_decks[0]["deck"]
        if deck.id != deckid:
            fail = True
            ei.print_red("Transferred token is not the expected one. Expected token: {}, transferred token: {}.".format(deckid, deck.id))

        # lock check: tokens need to be locked until at least 100 blocks (default) in the future
        blockheight = provider.getblockcount()
        if not check_lock(deck, token_seller, token_receiver, token_amount, blockheight, limit=100, debug=debug):
            fail = True
    else:
        print("No deck (token) ID or label provided, so no lock check will be performed.")

    if return_state is True:
        return fail
    else:
        if fail is True:
            ei.print_red("SWAP CHECK FAILED. If you are the token buyer and see this or any red warning, you cannot perform the swap or it is recommended to abandon it.")
        else:
            print("SWAP CHECK PASSED. If there is a warning, read it carefully to avoid any losses.")
