# this file bundles all x-specific (exchange) commands.
# SECOND version, where the exchange is initiated by the card seller, not the coin seller.

from binascii import hexlify, unhexlify
from prettyprinter import cpprint as pprint
from pacli.config import Settings
from pacli.provider import provider
from pacli.utils import sendtx
from pypeerassets.kutil import Kutil
from pypeerassets.provider import Provider
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
from pypeerassets.at.dt_entities import SignallingTransaction, LockingTransaction, DonationTransaction, VotingTransaction, TrackedTransaction, ProposalTransaction
import pacli.extended_utils as eu
import pacli.extended_interface as ei
from pypeerassets.pa_constants import param_query
from pypeerassets.networks import net_query
from pypeerassets.transactions import Transaction, MutableTransaction, MutableTxIn, tx_output, p2pkh_script, nulldata_script, make_raw_transaction


def card_lock(deckid: str, amount: str, lock: int, receiver: str=Settings.key.address, lockaddr: str=None, change: str=None, addrtype: str=None, absolute: bool=False, confirm: bool=False, sign: bool=True, send: bool=True, txhex: bool=False, force: bool=False, quiet: bool=False, debug: bool=False):

    # NOTE: cards are always locked at the receiver's address of the CardLock, like in CLTV.
    # returns a dict to be passed to self.card_transfer as kwargs
    change_address = Settings.change if change is None else change
    card_sender = Settings.key.address

    quiet = True if True in (quiet, txhex) else False
    current_blockheight = provider.getblockcount()
    if absolute:
        locktime = lock
        if lock < current_blockheight:
             print("ERROR: Your chosen locktime {} is in the past. Current blockheight: {}".format(lock, current_blockheight))
    else:
        locktime = lock + current_blockheight
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
        locked_amount = get_locked_amount(state.locks, card_sender)
        available_token_units = balance - locked_amount
        if debug:
            print("Available token units: {} Token units to lock: {}".format(available_token_units, unit_amount))
        if unit_amount > available_token_units:
            raise ei.PacliDataError("Not enough funds. Balance may be too low, and already locked tokens can't be used for locks.")

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

    print("Change of the coins sold will be sent to address", coinseller_change_address)

    coinseller_input_values = coinseller_input.split(":")
    coinseller_input_txid, coinseller_input_vout = coinseller_input_values[0], int(coinseller_input_values[1])
    # coinseller's input becomes second input, as first must be card sender.
    coinseller_input = build_input(coinseller_input_txid, coinseller_input_vout)
    amount_str = str(provider.getrawtransaction(coinseller_input_txid, 1)["vout"][coinseller_input_vout]["value"])
    coinseller_input_amount = Decimal(amount_str)
    # print("second_input_amount", second_input_amount)
    # first input comes from the card seller (i.e. the user who signs here)
    # We let pacli chose it automatically, based on the minimum amount. It should never give more than one, but it wouldn't matter if it's two or more.
    # own_inputs = provider.select_inputs(my_address, Decimal('0.01'))
    try:
        utxo = select_utxos(minvalue=Decimal("0.01"), address=my_address, utxo_type="pubkeyhash", quiet=True, debug=debug)[0] # first usable utxo is selected
    except IndexError:
        raise ei.PacliDataError("Not enough funds. Send enough coins to this address ({}) to pay the transaction fee.\nNOTE: If you have only mined coins on this address, you will have to transfer additional coins to it, as coinbase inputs can't be used for swaps due to an upstream bug (you can also send the coins to yourself).".format(my_address))
    utxo_value = Decimal(str(utxo["amount"]))
    own_input = MutableTxIn(txid=utxo['txid'], txout=utxo['vout'], sequence=Sequence.max(), script_sig=ScriptSig.empty())
    # inputs = {"utxos" : own_inputs["utxos"] + [coinseller_input], "total": coinseller_input_amount + own_inputs["total"]}
    inputs = {"utxos" : [own_input, coinseller_input], "total": coinseller_input_amount + utxo_value}
    utxos = inputs["utxos"]

    unsigned_tx = create_card_exchange(provider=provider,
                                 inputs=inputs,
                                 card=card,
                                 coinseller_change_address=coinseller_change_address,
                                 coin_value=coin_amount,
                                 first_input_value=utxo_value,
                                 cardseller_change_address=my_change_address
                                 )

    network_params = net_query(provider.network)
    # print(network_params)
    if sign:
        # sighash has be ALL, otherwise the counterparty could modify it, and anyonecanpay must be False.
        for i in range(len(utxos) - 1): # we sign all inputs minus the last one which is from the coin_seller.
            if debug:
                print("Signing utxo", utxos[i])
            result = solve_single_input(index=i, prev_txid=utxos[i].txid, prev_txout_index=utxos[i].txout, key=Settings.key, network_params=network_params, debug=debug)
            unsigned_tx.spend_single(index=i, txout=result["txout"], solver=result["solver"])

        print("The following hex string contains the transaction which you signed with your keys only. Transmit it to your exchange partner via any messaging channel (there's no risk of your tokens or coins to be stolen).\n")
        print(unsigned_tx.hexlify()) # prettyprint makes it more difficult to copy it
        if save_identifier:
            eu.save_transaction(save_identifier, tx_hex, partly=True)
    else:
        return unsigned_tx.hexlify()


def build_input(input_txid: str, input_vout: int):

    return MutableTxIn(txid=input_txid, txout=input_vout, script_sig=ScriptSig.empty(), sequence=Sequence.max())


def finalize_coin2card_exchange(txstr: str, confirm: bool=False, force: bool=False, send: bool=False, txhex: bool=False):
    quiet = True if True in (quiet, txhex) else False
    # this is signed by the coin vendor. Basically they add their input and solve it.
    network_params = net_query(provider.network)
    tx = MutableTransaction.unhexlify(txstr, network=network_params)

    my_input = tx.ins[-1] # the coin seller's input is the last one
    my_input_index = len(tx.ins) - 1
    if not quiet:
        print(my_input_index)
    result = solve_single_input(index=my_input_index, prev_txid=my_input.txid, prev_txout_index=my_input.txout, key=Settings.key, network_params=network_params)
    tx.spend_single(index=my_input_index, txout=result["txout"], solver=result["solver"])

    return ei.output_tx(eu.finalize_tx(tx, verify=False, sign=False, send=send, ignore_checkpoint=force, confirm=confirm), txhex=txhex)

def solve_single_input(index: int, prev_txid: str, prev_txout_index: int, key: Kutil, network_params: tuple, sighash: str="ALL", anyonecanpay: bool=False, debug: bool=False):

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


def create_card_exchange(provider: Provider, card: CardTransfer, inputs: dict, coinseller_change_address: str, cardseller_change_address: str, coin_value: Decimal, first_input_value: Decimal, locktime: int=0) -> Transaction:
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
    print("card sender", card.sender, "card receiver", card.receiver)

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
        if utxo_type is not None:
            utxo_tx = provider.getrawtransaction(utxo["txid"], 1)
            utype = utxo_tx["vout"][utxo["vout"]]["scriptPubKey"]["type"]

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
            print("Due to an upstream bug, this can happen if all UTXOs on this address come directly from coinbase outputs (mining or minting)."
            print("You can transfer the needed coins from any source, including the same address.")
            return
        print(len(selected_utxos), "matching utxos found.")
        print("Use this format (TXID:OUTPUT) to initiate a new exchange.")
        for utxo in selected_utxos:
            pprint("{}:{}".format(utxo.get("txid"), utxo.get("vout")))
            print("Amount: {} coins".format(utxo.get("amount")))


def prettyprint_locks(locks: dict, blockheight: int, decimals: int=None):
    print("Locks at blockheight {}:".format(blockheight))
    if len(locks) == 0:
        print("No locks found.")
    for address in locks.keys():
        pprint("Address: {}".format(address))
        for lock in locks.get(address):
            pprint("* Lock until block: {}".format(lock.get("locktime")))
            #try:
            #    lock_address = henc.hash_to_address(lock.get("lockhash"), lock.get("lockhash_type"), net_query(provider.network))
            lock_address = get_lock_address(lock)
            if lock_address is None:
                # except NotImplementedError:
                print("Non-standard lock or address type still not supported. Showing raw data:")
                print("* Lock hash: {}".format(lock.get("lockhash")))
                print("* Lock hash type: {}".format(lock.get("lockhash_type")))
            else:
                pprint("* Lock address: {}".format(lock_address))
            if decimals:
                lock_amount = exponent_to_amount(lock["amount"], decimals) # Decimal(lock["amount"]) / (10 ** decimals)
                pprint("* Lock amount (tokens): {}".format(lock_amount))
            else:
                pprint("* Lock amount (token minimum units): {}".format(lock.get("amount")))

def get_lock_address(lock: dict) -> str:
    try:
        lock_address = henc.hash_to_address(lock.get("lockhash"), lock.get("lockhash_type"), net_query(provider.network))
        return lock_address
    except NotImplementedError:
        return None


def get_locked_amount(locks: dict, card_sender: str) -> int:
    locks_on_address = locks.get(card_sender)
    locked_amounts = [l["amount"] for l in locks_on_address]
    return sum(locked_amounts)
