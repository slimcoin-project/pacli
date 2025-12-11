# this file bundles all x-specific (exchange) commands.
# SECOND version, where the exchange is initiated by the token seller, not the token buyer.

from prettyprinter import cpprint as pprint
from pacli.config import Settings
from pacli.provider import provider
from pypeerassets.kutil import Kutil
from pypeerassets.protocol import CardTransfer
from btcpy.structs.sig import Sighash, P2pkSolver, P2pkhSolver
from btcpy.structs.transaction import ScriptSig, Locktime
from pypeerassets.provider.rpcnode import Sequence
import pypeerassets as pa
from pypeerassets.pautils import amount_to_exponent, exponent_to_amount
import pypeerassets.hash_encoding as henc
from decimal import Decimal
import pacli.extended_utils as eu
import pacli.extended_commands as ec
import pacli.extended_interface as ei
import pacli.extended_txtools as et
import pacli.blockexp_utils as bu
import pacli.extended_config as ce
import pacli.extended_handling as eh
import pacli.extended_keystore as ke
import pacli.extended_token_queries as etq
import pacli.extended_token_txtools as ett
from pypeerassets.networks import net_query
from pypeerassets.transactions import Transaction, MutableTransaction, MutableTxIn, tx_output, p2pkh_script, nulldata_script, make_raw_transaction


def card_lock(deckid: str,
              amount: str,
              lock: int,
              receiver: str=None,
              lockaddr: str=None,
              change: str=None,
              addrtype: str=None,
              absolute: bool=False,
              confirm: bool=False,
              sign: bool=True,
              send: bool=True,
              txhex: bool=False,
              return_txid: bool=False,
              force: bool=False,
              quiet: bool=False,
              debug: bool=False):

    card_sender = ke.get_main_address()
    receiver = card_sender if receiver is None else ec.process_address(receiver)
    # NOTE: cards are always locked at the receiver's address of the CardLock, like in CLTV.
    # returns a dict to be passed to self.card_transfer as kwargs
    if change and not eu.is_mine(change):
        ei.print_red("Custom change address {} is not part of your wallet.".format(change))
        if not force:
            raise eh.PacliDataError("Transaction aborted. If you want to lock the coins with this change address anyway, use -f option.")
        else:
            ei.print_red("-f option used. The change will be transferred to your selected change address.")

    change_address = Settings.change if change is None else change


    if not eu.is_mine(receiver) and not force:
        raise eh.PacliDataError("The receiver address {} is not part of your wallet. If you really want to transfer the coins to another wallet or person while locking, use the --force option.".format(receiver))

    quiet = True if True in (quiet, txhex) else False
    current_blockheight = provider.getblockcount()
    if absolute is True:
        locktime = lock
        if lock < current_blockheight:
             raise eh.PacliInputDataError("Aborted. Your chosen locktime {} is in the past. Current blockheight: {}".format(lock, current_blockheight))
    else:
        locktime = lock + current_blockheight
    if (locktime - current_blockheight) < 100 and not force:
        raise eh.PacliInputDataError("Aborted. Locktime is too low (< 100 blocks in the future). By default, a token buyer will not accept that lock. If using the 'swap lock' command to lock the tokens, you can use --force to override this check, e.g. if there is some trust between buyer and seller.")

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
    amount_dec = Decimal(str(amount))
    unit_amount = amount_to_exponent(amount_dec, deck.number_of_decimals)

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
            # available_tokens = exponent_to_amount(available_token_units, deck.number_of_decimals) # unused
            raise eh.PacliDataError("Not enough tokens on main address. Total balance: {}, Locked: {}, required: {}. Locked tokens can't be used for new locks.".format(balance_tokens, locked_tokens, amount))

    txdict = ett.advanced_card_transfer(deck,
                                      receiver=[receiver],
                                      amount=[amount_dec],
                                      locktime=0,
                                      card_locktime=locktime,
                                      card_lockhash=lockhash,
                                      card_lockhash_type=lockhash_type,
                                      change=change_address,
                                      balance_check=False,
                                      sign=sign,
                                      send=send,
                                      force=force,
                                      debug=debug)

    txdata = eh.output_tx(txdict, txhex=txhex or return_txid) # return_txid also needs the "neutral" hex data given by txhex=True
    if return_txid:
        txjson = provider.decoderawtransaction(txdata)
        return txjson["txid"]
    else:
        return txdata

# main function to be changed:
# - tokenbuyer_address (formerly partner_address) is now the card receiver.
# - change of tokenbuyer input must go to tokenbuyer address.

def build_coin2card_exchange(deckid: str,
                             tokenbuyer_address: str,
                             tokenbuyer_input: str,
                             card_amount_raw: Decimal,
                             coin_amount: Decimal,
                             change: str=None,
                             tokenbuyer_change_address: str=None,
                             save_identifier: str=None,
                             lock_tx: str=None,
                             new_payment_address: bool=True,
                             without_checks: bool=False,
                             sign: bool=False,
                             debug: bool=False):

    # the card seller builds the transaction
    my_key = Settings.key
    my_address = my_key.address
    if change is not None and not eu.is_mine(change):
        ei.print_red("WARNING: Custom change address {} is not part of your current wallet. If you are in doubt, don't submit the hex string to your exchange partner and repeat the command with another change address.".format(change))

    deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
    card_units = amount_to_exponent(card_amount_raw, deck.number_of_decimals)
    card = pa.CardTransfer(deck=deck,
                           sender=my_address,
                           receiver=[tokenbuyer_address],
                           amount=[card_units])

    card_amount =  Decimal(str(exponent_to_amount(card_units, deck.number_of_decimals)))
    if card_amount != card_amount_raw:
        ei.print_red("WARNING: The token amount you entered ({}) has more decimal places than the token supports ({}). Rounded to {}.".format(card_amount_raw, deck.number_of_decimals, card_amount))

    # tokenbuyer can submit another change address if he wants, otherwise cardseller sends it to the tokenbuyer addr.
    if tokenbuyer_change_address is None:
        tokenbuyer_change_address = tokenbuyer_address

    print("Token seller:", card.sender, "Token receiver:", card.receiver[0])

    try:
        if not ":" in tokenbuyer_input: # this treats tokenbuyer_input as a label for a stored utxo
            tokenbuyer_input = ce.show("utxo", tokenbuyer_input)
        tokenbuyer_input_values = tokenbuyer_input.split(":")
        tokenbuyer_input_txid, tokenbuyer_input_vout = tokenbuyer_input_values[0], int(tokenbuyer_input_values[1])
    except:
        raise eh.PacliInputDataError("Partner input (UTXO provided by the token seller) provided in a wrong format. Use TXID:OUTPUT or a label for a stored UTXO.")

    # tokenbuyer's input becomes second input, as first must be card sender.
    tokenbuyer_input = build_input(tokenbuyer_input_txid, tokenbuyer_input_vout)
    min_amount = eu.min_amount("output_value")
    min_tx_fee = eu.min_amount("tx_fee")
    min_opreturn = eu.min_amount("op_return_value")
    all_fees = min_amount * 2 + min_opreturn + min_tx_fee
    tokenbuyer_input_tx = provider.getrawtransaction(tokenbuyer_input_txid, 1)
    # added ismine check for the utxo. Cannot normally be used for scams.
    tokenbuyer_utxo = bu.get_utxo_from_data((tokenbuyer_input_txid, int(tokenbuyer_input_vout)), tx=tokenbuyer_input_tx)
    tokenbuyer_utxo_addresses = bu.get_utxo_addresses(tokenbuyer_utxo)
    for taddr in tokenbuyer_utxo_addresses:
        if eu.is_mine(taddr):
            ei.print_red("The swap uses funds from the token seller's address {} to pay for the tokens.".format(taddr))
            ei.print_red("This cannot normally be used for scams, as the token buyer won't be able to sign the transaction fully. It is probably a mistake (or a private test/privacy-related swap).")
            ei.print_red("Nevertheless, don't proceed if in doubt. Re-check the partner input of the swap carefully.")
            break

    print("Token buyer's input address(es): {} (can be different from the token receiver's address)".format(tokenbuyer_utxo_addresses))
    print("Change of the coins sold will be sent to address", tokenbuyer_change_address)

    try:
        amount_str = str(tokenbuyer_utxo["value"])
    except (KeyError, IndexError):
        raise eh.PacliDataError("Incorrect input provided by the token buyer, either the transaction doesn't exist or it has less outputs than expected.")
    tokenbuyer_input_amount = Decimal(amount_str)
    if tokenbuyer_input_amount < coin_amount + all_fees: # NOTE: token buyer pays fees!
        raise eh.PacliInputDataError("The input provided by the token buyer has a lower balance than the requested payment plus fees (available amount: {}, requested payment {}, fees: {})".format(tokenbuyer_input_amount, coin_amount, all_fees))
    # first input comes from the card seller (i.e. the user who signs here)
    # We let pacli chose it automatically, based on the minimum amount. It should never give more than one, but it wouldn't matter if it's two or more.

    try:
        own_utxo = select_utxos(minvalue=min_amount, address=my_address, utxo_type="pubkeyhash", quiet=True, debug=debug)[0] # first usable utxo is selected
    except IndexError:
        ei.print_red("Not enough funds. Send at least the minimum amount of coins allowed by your network for transactions ({} {}) to this address ({}).".format(min_amount, Settings.network.upper(), my_address))
        ei.print_red("NOTE 1: If you have only mined coins on this address, you will have to transfer additional coins to it, as coinbase inputs can't be used for swaps due to an upstream bug (you can also send the coins to yourself).")
        ei.print_red("NOTE 2: If you recently locked tokens or sent coins to your current main address and this error appears, you may have already enough coins on this address but have to restart your client with -rescan for it to become aware of the coins. After the restart, repeat the 'swap create' command without the -w option.")
        raise eh.PacliDataError("Swap creation aborted.")
    own_utxo_value = Decimal(str(own_utxo["amount"]))
    own_input = MutableTxIn(txid=own_utxo['txid'], txout=own_utxo['vout'], sequence=Sequence.max(), script_sig=ScriptSig.empty())
    inputs = {"utxos" : [own_input, tokenbuyer_input], "total": tokenbuyer_input_amount + own_utxo_value}
    utxos = inputs["utxos"]

    # payment address is, by default, the Settings.change address,
    # i.e. it depends on the change policy if it is a new address ("newaddress" mode) or the current main address ("legacy" mode)
    my_change_address = Settings.change if change is None else change
    # payment_address = et.generate_new_change_address(debug=debug, alt_address=my_address) if new_payment_address else my_address
    payment_address = Settings.change if new_payment_address is True else my_address

    unsigned_tx = create_card_exchange(inputs=inputs,
                                 card=card,
                                 tokenbuyer_change_address=tokenbuyer_change_address,
                                 coin_value=coin_amount,
                                 first_input_value=own_utxo_value,
                                 cardseller_change_address=my_change_address,
                                 cardseller_payment_address=payment_address,
                                 min_output_value=min_amount,
                                 min_opreturn_value=min_opreturn,
                                 min_tx_fee=min_tx_fee,
                                 debug=debug
                                 )

    network_params = net_query(provider.network)
    # lock check: tokens need to be locked until at least 100 blocks (default) in the future
    if without_checks:
        ei.print_orange("Warning: No checks selected. Token balance and locks will not be verified. Swap may become invalid.")
    elif lock_tx is not None:
        print("Balance and lock check skipped as tokens were already locked.")
    else:
        print("Checking token balance ...")
        statedict = etq.get_address_token_balance(deck, my_address, return_statedict=True)
        token_balance, state = statedict["balance"], statedict["state"]

        if token_balance < card_amount:
             raise eh.PacliDataError("Not enough token balance (balance: {}, required: {}).".format(token_balance, card_amount))
        print("Token balance of the sender:", str(token_balance))
    if lock_tx is None:
        if not without_checks:
            print("Checking locks ...")
            lockcheck_passed = check_lock(deck, my_address, tokenbuyer_address, card_amount, blockheight=provider.getblockcount(), limit=100, locks=state.locks, quiet=True, debug=debug)
            if not lockcheck_passed:
                ei.print_red("WARNING: Lock check failed, tokens were not properly locked before the swap creation (minimum: 100 blocks in the future). The buyer will probably reject the swap. You can still lock the coins after creating the hex string. If the tokens were locked, it's possible the lock transaction is still unconfirmed, or the locktime is too short.")
        else:
            print("Lock check passed: Enough tokens are on the sender's address and properly locked.")

    if sign:
        # sighash has be ALL, otherwise the counterparty could modify it, and anyonecanpay must be False.
        for i in range(len(utxos) - 1): # we sign all inputs minus the last one which is from the coin_seller.
            if debug:
                print("Signing utxo", utxos[i])
            result = solve_single_input(index=i, prev_txid=utxos[i].txid, prev_txout_index=utxos[i].txout, key=Settings.key, network_params=network_params, debug=debug)
            unsigned_tx.spend_single(index=i, txout=result["txout"], solver=result["solver"])

        print("The following hex string contains the transaction which you signed with your keys only. Transmit it to your exchange partner via any messaging channel (there's no risk of your tokens or coins to be stolen, but a secure channel is preferrable for more privacy).\n")
        tx_hex = unsigned_tx.hexlify()
        print(tx_hex) # prettyprint makes it more difficult to copy it
        if lock_tx is None and (without_checks or not lockcheck_passed):
            ei.print_red("\nNOTE: Before transmitting the hex string to the token buyer, if the tokens weren't locked or the lock blockheight is too close, lock them with the following command:")
            ei.print_red("'pacli swap lock {} {} {}'.".format(deckid, str(card_amount), tokenbuyer_address))
            print("NOTE: The lock check can also fail when the locking transaction is still unconfirmed. If you are sure that you have locked the tokens already, check the confirmation status of the transaction before locking the tokens again.")
        if save_identifier is not None:
            if type(save_identifier) in (str, int):
                eu.save_transaction(save_identifier, tx_hex, partly=True)
            else:
                print("\nNOTE: The label to save the transaction has to be a string or an integer. Transaction was not saved, you can save it manually with the 'transaction set' command.")
    else:
        print(unsigned_tx.hexlify())

    if lock_tx is not None:
        print("\nChecking confirmation status of lock transaction ...")
        #lockcheck_passed = check_lock(deck, my_address, tokenbuyer_address, card_amount, blockheight=provider.getblockcount(), limit=100, debug=debug)
        txjson = provider.getrawtransaction(lock_tx, 1)
        if "confirmations" not in txjson:
            ei.print_red("Lock transaction is still unconfirmed. Wait for the transaction to confirm before transmitting the TX hex string to the token buyer.")
            ei.print_red("To see if the transaction was confirmed, use 'pacli transaction show {} -s' and check the output for the 'blockheight' value.".format(lock_tx))
        else:
            print("Lock transaction correctly confirmed. The hex string can be transferred to the token buyer.")
    print("NOTE: Be aware that if you move the funds used in the swap transaction before the swap is finalized and broadcast, the swap will never confirm, because this will constitute a double spend attempt. This can happen accidentally if you use slimcoin-qt or slimcoind commands like 'sendtoaddress' or 'sendfrom'. Try to use coin control if you need to make a payment in this timeframe, or use the pacli commands like 'coin sendto'.")

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

    spenttx = eh.output_tx(et.finalize_tx(tx, verify=False, sign=False, send=send, ignore_checkpoint=force, confirm=confirm, quiet=quiet, debug=debug), txhex=txhex)
    return spenttx

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
        raise eh.PacliDataError("UTXOs coming from coinbase transactions are not supported due to a bug in the btcpy library. Please select another input.")
    except KeyError:
        raise eh.PacliDataError("Broken transaction:", prev_txid)

    prev_tx = Transaction.from_json(prev_tx_json, network=network_params)
    prev_txout = prev_tx.outs[prev_txout_index]

    if prev_txout.type == "p2pk":
        solver = P2pkSolver(key._private_key, sighash=Sighash(sighash, anyonecanpay))
    elif prev_txout.type == "p2pkh":
        solver = P2pkhSolver(key._private_key, sighash=Sighash(sighash, anyonecanpay))
    else:
        raise ValueError("TX type unknown or not implemented.")
    return { "txout" : prev_txout, "solver" : solver }


def create_card_exchange(card: CardTransfer,
                         inputs: dict,
                         tokenbuyer_change_address: str,
                         cardseller_change_address: str,
                         cardseller_payment_address: str,
                         coin_value: Decimal,
                         first_input_value: Decimal,
                         min_output_value: Decimal,
                         min_opreturn_value: Decimal,
                         min_tx_fee: Decimal,
                         locktime: int=0,
                         debug: bool=False) -> Transaction:
    # extended version of card_transfer which allows to add another output to the other party,
    # and allows signing only a part of the inputs.

    '''Prepare the CardTransfer Transaction object

       : card - CardTransfer object
       : inputs - utxos (first has to be owned by card issuer)
       : change_address - address to send the change to
       : locktime - tx locked until block n=int
       '''

    if card.deck_p2th is None:
        raise Exception("card.deck_p2th required for tx_output")

    # TODO: we could unify outputs 3 and 4, at least if the card seller doesn't need a different change address.
    # This would make the transaction "less transparent", but make the transaction footprint smaller.
    outs = [
        tx_output(network=provider.network,
                  value=min_output_value, # pa_params.P2TH_fee,
                  n=0, script=p2pkh_script(address=card.deck_p2th,
                                           network=provider.network)),  # deck p2th
        tx_output(network=provider.network,
                  value=min_opreturn_value, n=1,
                  script=nulldata_script(card.metainfo_to_protobuf)),  # op_return

        tx_output(network=provider.network, value=min_output_value, n=2, # card transfer to coin sender/card receiver
                  script=p2pkh_script(address=card.receiver[0],
                                      network=provider.network)),

        tx_output(network=provider.network, value=coin_value, n=3, # coin transfer to coin receiver/card sender
                  script=p2pkh_script(address=cardseller_payment_address,
                                      network=provider.network)),

        tx_output(network=provider.network, value=first_input_value, n=4, # change coins back to card sender
                  script=p2pkh_script(address=cardseller_change_address,
                                      network=provider.network))
    ]

    #  first round of txn making is done by presuming minimal fee
    # change_sum = Decimal(inputs['total'] - network_params.min_tx_fee - pa_params.P2TH_fee - first_input_value - coin_value - total_min_values)
    change_sum = Decimal(inputs['total'] - first_input_value - coin_value - 2 * min_output_value - min_opreturn_value - min_tx_fee)
    if debug:
        print("Change sum:", change_sum, "Total inputs:", inputs["total"], "First input:", first_input_value, "Coin value:", coin_value)

    if change_sum > 0:

        outs.append(
            tx_output(network=provider.network,
                      value=change_sum, n=len(outs)+1,
                      script=p2pkh_script(address=tokenbuyer_change_address,
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
                 fees: bool=False,
                 quiet: bool=False,
                 debug: bool=False):

    # NOTE: due to btcpy bug, UTXOs coming from coinbase transactions can't be supported currently.
    # Once the problem is solved, the ignore_coinbase flag can be set to False.

    utxos = provider.listunspent(address=address, minconf=minconf, maxconf=maxconf)
    selected_utxos = []
    if fees is True:
        swap_fees = eu.calc_cardtransfer_fees()
        minvalue += swap_fees
        if not quiet:
            print("Added swap fees of {} coins to the amount. Minimum amount for UTXOs to be displayed: {} coins.".format(swap_fees, minvalue))

    for utxo in utxos:
        utxo_amount = Decimal(str(utxo["amount"])) # str is necessary
        if minvalue is not None and utxo_amount < minvalue:
            continue
        if maxvalue is not None and utxo_amount > maxvalue:
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

        for utxo in selected_utxos:
            pprint("{}:{}".format(utxo.get("txid"), utxo.get("vout")))
            print("Amount: {} coins".format(utxo.get("amount")))
            if show_address and "address" in utxo:
                if len(utxo["address"]) == 1:
                    print("Address:", utxo["address"][0])
                else:
                    print("Addresses (e.g. multisig):", utxo["address"])

        print("Use this format (TXID:OUTPUT) to initiate a new swap.")
        print("NOTE: Be aware that if you move the funds of the selected UTXO before you finalize the swap, the swap will never confirm, because this will constitute a double spend attempt. This can happen accidentally if you use slimcoin-qt or slimcoind commands like 'sendtoaddress' or 'sendfrom'. Try to use coin control if you need to make a payment in this timeframe, or use the pacli commands like 'coin sendto'.")

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

def check_lock(deck: object, card_sender: str, card_receiver: str, amount: Decimal, blockheight: int, limit: int=None, locks: list=None, quiet: bool=False, debug: bool=False):
    # Checks if the lock is correct.
    # NOTE: amount is in tokens and thus in Decimal format, not minimum units.
    deckid = deck.id
    decimals = deck.number_of_decimals
    if not locks:
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

    matching_locks, lock_amount, lock_heights = [], Decimal(0), []
    for lock in sender_locks:
        lock_address = get_lock_address(lock)
        formatted_single_lock = exponent_to_amount(Decimal(str(lock["amount"])), decimals)
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
               ignore_lock: bool=False,
               utxo_check: bool=False,
               debug: bool=False):
    """bundles most checks for swaps"""
    fail, notmine = False, False
    # min_amount = eu.min_amount("output_value") # unused, but could be useful for additional check
    min_tx_fee = eu.min_amount("tx_fee")
    # min_opreturn = eu.min_amount("op_return_value") # unused, but could be useful for additional check
    try:
        txjson = provider.decoderawtransaction(txhex)
        txstruct = bu.get_tx_structure(tx=txjson, ignore_blockhash=True)
    except:
        raise eh.PacliInputDataError("No valid transaction hex string or label provided.")

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
        tokenreceiver_value = txstruct["outputs"][2]["value"]

        all_inputs = sum([Decimal(str(i["value"])) for i in txstruct["inputs"]])
        all_outputs = sum([Decimal(str(o["value"])) for o in txstruct["outputs"]])
        tx_fee = all_inputs - all_outputs
        p2th_fee = Decimal(str(txstruct["outputs"][0]["value"]))

        op_return_fee = Decimal(str(txstruct["outputs"][1]["value"]))
        card_transfer_fee = Decimal(str(txstruct["outputs"][2]["value"]))

        all_fees = tx_fee + p2th_fee + op_return_fee + card_transfer_fee

        op_return_output = txjson["vout"][1]
    except (KeyError, IndexError):
        raise eh.PacliDataError("Incorrect transaction structure. Don't proceed with the transaction.")

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
    if presign_check and (token_buyer != ke.get_main_address()):
        ei.print_red("The token buyer address is not your current Pacli main address, so you will not be able to sign the transaction.")
        ei.print_red("Switch to the correct address with 'pacli address set -a {}' and repeat the command.".format(token_buyer))
        print("Current Pacli main address:", ke.get_main_address())
        fail = True
    if token_receiver != token_buyer:
        print("NOTE: The address providing the coins for the swap isn't identic to the address which will receive the tokens.")
        print("This may be intentionally set up by the token buyer, e.g. for privacy reasons.")
        print("If you are the token buyer, make sure the token receiver address {} belongs to you (will be checked in the ownership check).".format(token_receiver))

    if token_receiver_address is not None and (token_receiver != token_receiver_address):
        ei.print_red("The token receiver address you provided in this check isn't the address receiving the tokens in the swap transaction.")
        fail = True
    if change_receiver is not None:
        pprint("Change address for payment (normally controlled by token buyer): {}".format(change_receiver))
        pprint("Change returned: {}".format(change_returned))
        if buyer_change_address is not None and (change_receiver != buyer_change_address):
            ei.print_red("The change receiver address you provided in this check isn't the address receiving the change coins in the swap transaction.")
            fail = True
        else:
            print("Change check passed: change address is correct.")
    pprint("Fees paid: {}".format(all_fees))
    # netparams = net_query(Settings.network)
    # min_tx_fee = netparams.min_tx_fee
    if tx_fee < min_tx_fee:
        ei.print_red("Transaction fee is too low. The transaction will probably never confirm. The token seller has to repeat the swap creation with a fee of at least {} coins.".format(min_tx_fee))
        fail = True
    payment_with_fees = amount_provided - change_returned
    paid_amount = payment_with_fees - all_fees
    pprint("Coins paid for the tokens (not including fees): {}".format(paid_amount))
    pprint("Coins returned to token receiver (required by PeerAssets): {}".format(tokenreceiver_value))
    pprint("Fees paid by the token buyer: {}.".format(all_fees))
    pprint("Total paid: {} minus {} coins".format(payment_with_fees, tokenreceiver_value))
    if amount is not None:
        intended_amount = Decimal(str(amount))
        if intended_amount != paid_amount:
            if intended_amount < paid_amount:
                ei.print_red("WARNING: The token buyer would pay {} coins more than expected in this swap.".format(paid_amount - intended_amount))
            elif intended_amount > paid_amount:
                ei.print_red("WARNING: The token seller would receive {} coins less than expected in this swap.".format(intended_amount - paid_amount))
            ei.print_red("The token buyer is expecting to pay {} coins for the tokens but by finalizing the swap with this hex string they'll have to pay {} coins (excluding fees of {} coins). Please negotiate or create another hex string or change the expected payment value.".format(intended_amount, paid_amount, all_fees))
            fail = True

    for adr in [a for a in (token_receiver, change_receiver) if a is not None]:
        validation = provider.validateaddress(adr)
        if validation.get("ismine") != True:
            notmine = True
            fail = True
    if notmine is True:
        ei.print_red("Ownership check failed: At least one of the addresses which should be under the token buyer's control in this swap (token receiver and change receiver) isn't part of your current wallet.")
        print("This may be intentional if you provided an address of another wallet, or are using this command running the client with a different wallet than the swap's wallet, but can also be a manipulation by the token buyer.")
        print("Ignore this warning if you are not the token buyer.")
    else:
        print("Ownership check passed: Both the token receiver and the change address for the provided coins are part of your currently used wallet.")


    if utxo_check:
        spending_utxo = txjson["vin"][1]
        if et.check_if_spent(spending_utxo["txid"], spending_utxo["vout"], address=token_buyer):
            fail = True
            ei.print_red("The UTXO provided by you (the token buyer) has already been spent. Swap transaction will never confirm.")
            ei.print_red("Repeat the swap creation transmitting another UTXO to the token seller.")
        else:
            print("UTXO check passed. Token buyer's utxos are unspent.")

    # card transfer checks: those take more time and thus are performed last.

    card_transfer = eu.decode_card(op_return_output)
    card_amount = card_transfer["amount"][0]
    decimals = card_transfer["number_of_decimals"]
    token_amount = Decimal(str(token_amount)) if token_amount is not None else None

    formatted_card_amount = Decimal(str(exponent_to_amount(card_amount, decimals)))
    if token_amount is not None:
        token_units = amount_to_exponent(token_amount, decimals)
        if formatted_card_amount != token_amount:
            expected_decimals = -token_amount.as_tuple().exponent
            fail = True
            if expected_decimals == decimals or token_units != card_amount:
                ei.print_red("The number of tokens transferred is {}, while the expected token amount is {}.".format(formatted_card_amount, token_amount))
            else:
                ei.print_red("WARNING: The token only supports {} decimals, while your expected token amount has {} decimals. Amount must be rounded to {}.".format(decimals, expected_decimals, formatted_card_amount))
                ei.print_red("Please repeat the command with the correct amount.")

        else:
            print("Token transfer check passed: tokens transferred: {}, expected: {}.".format(formatted_card_amount, token_amount))

    if deckid:
        print("Deck ID and lock check (may take some time) ....")
        matching_decks = etq.find_decks_by_address(p2th_address, addrtype="p2th_main", debug=False)
        deck = matching_decks[0]["deck"]
        if deck.id != deckid:
            fail = True
            ei.print_red("Transferred token is not the expected one. Expected token: {}, transferred token: {}.".format(deckid, deck.id))

        # lock check: tokens need to be locked until at least 100 blocks (default) in the future
        # we use the real card amount in the swap tx here, because the consistency with the real swap was already tested
        if not ignore_lock:
            #if not token_amount:
            #    print("Lock check needs the token amount. No lock check will be performed.")
            #else:
            blockheight = provider.getblockcount()
            if not check_lock(deck, token_seller, token_receiver, formatted_card_amount, blockheight, limit=100, debug=debug):
                fail = True
    else:
        print("No deck (token) ID or label provided, so no lock check will be performed.")

    if return_state is True:
        return fail
    else:
        if fail is True:
            ei.print_red("SWAP CHECK FAILED. If you are the token buyer and see this or any red warning, you cannot perform the swap or it is recommended to abandon it.")
        else:
            print("Swap check passed. If there is a warning, read it carefully to avoid any losses.")


