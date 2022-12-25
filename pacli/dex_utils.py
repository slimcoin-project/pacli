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
import json
from decimal import Decimal
from pypeerassets.at.dt_entities import SignallingTransaction, LockingTransaction, DonationTransaction, VotingTransaction, TrackedTransaction, ProposalTransaction
from pypeerassets.at.dt_parser_utils import deck_from_tx
import pacli.dt_utils as du
import pacli.dt_interface as di
import pacli.keystore_extended as ke
from pypeerassets.pa_constants import param_query
from pypeerassets.networks import net_query
from pypeerassets.transactions import Transaction, MutableTransaction, MutableTxIn, tx_output, p2pkh_script, nulldata_script, make_raw_transaction


def card_lock(deckid: str, amount: int, lock: int, receiver: str=Settings.key.address, lockaddr: str=None, sign: bool=False, send: bool=False):
    # NOTE: cards are always locked at the receiver's address of the CardLock, like in CLTV.
    # returns a dict to be passed to self.card_transfer as kwargs
    """data = b"L"
    data += lock.to_bytes(4, "big")
    if lockaddr is not None:
        data += lockaddr.encode("utf-8")"""
    #if lockaddr is not None:
    #    lockaddr_bytes = lockaddr.encode("utf-8") # TODO: change to base58!
    #else:
    #    lockaddr_bytes = None


    deck = deck_from_tx(deckid, provider)

    if isinstance(deck, pa.Deck):
        card = pa.CardTransfer(deck=deck,
                               sender=Settings.key.address,
                               receiver=[receiver],
                               amount=[amount_to_exponent(amount, deck.number_of_decimals)],
                               version=deck.version,
                               locktime=lock,
                               lock_address=lockaddr
                               )

    issue = pa.card_transfer(provider=provider,
                             inputs=provider.select_inputs(Settings.key.address, 0.03),
                             card=card,
                             change_address=Settings.change,
                             )

    return du.finalize_tx(issue, verify=False, sign=sign, send=send)

# main function to be changed:
# - coinseller_address (formerly partner_address) is now the card receiver.
# - change of coinseller input must go to coinseller address.

def build_coin2card_exchange(deckid: str, coinseller_address: str, coinseller_input: str, card_amount: Decimal, coin_amount: Decimal, coinseller_change_address: str=None, sign: bool=False):
    # the card seller builds the transaction
    my_key = Settings.key
    my_address = my_key.address
    my_change_address = Settings.change
    deck = deck_from_tx(deckid, provider)
    card = pa.CardTransfer(deck=deck, sender=my_key.address, receiver=[coinseller_address], amount=[amount_to_exponent(card_amount, deck.number_of_decimals)])

    # coinseller can submit another change address if he wants, otherwise cardseller sends it to the coinseller addr.
    if coinseller_change_address is None:
        coinseller_change_address = coinseller_address

    print("Change of the coins sold will be sent to address", coinseller_change_address)
    # print("Card data:", card)

    coinseller_input_values = coinseller_input.split(":")
    coinseller_input_txid, coinseller_input_vout = coinseller_input_values[0], int(coinseller_input_values[1])
    # coinseller's input becomes second input, as first must be card sender.
    coinseller_input = build_input(coinseller_input_txid, coinseller_input_vout)
    amount_str = str(provider.getrawtransaction(coinseller_input_txid, 1)["vout"][coinseller_input_vout]["value"])
    coinseller_input_amount = Decimal(amount_str)
    # print("second_input_amount", second_input_amount)
    # first input comes from the card seller (i.e. the user who signs here)
    # We let pacli chose it automatically, based on the minimum amount. It should never give more than one, but it wouldn't matter if it's two or more.
    own_inputs = provider.select_inputs(my_address, Decimal('0.01'))
    inputs = {"utxos" : own_inputs["utxos"] + [coinseller_input], "total": coinseller_input_amount + own_inputs["total"]}
    utxos = inputs["utxos"]

    unsigned_tx = create_card_exchange(provider=provider,
                                 inputs=inputs,
                                 card=card,
                                 coinseller_change_address=coinseller_change_address,
                                 coin_value=coin_amount,
                                 first_input_value=own_inputs["total"],
                                 cardseller_change_address=my_change_address
                                 )

    network_params = net_query(provider.network)
    # print(network_params)
    # input_types = du.get_input_types(unsigned_tx)
    if sign:
        # sighash has be ALL, otherwise the counterparty could modify it, and anyonecanpay must be False.
        for i in range(len(utxos) - 1): # we sign all inputs minus the last one which is from the coin_seller.
            result = solve_single_input(index=i, prev_txid=utxos[i].txid, prev_txout_index=utxos[i].txout, key=Settings.key, network_params=network_params)
            unsigned_tx.spend_single(index=i, txout=result["txout"], solver=result["solver"])

        print("The following string contains the transaction which you signed with your keys only. Transmit it to your exchange partner via any messaging channel (there's no risk of your tokens or coins to be stolen).")
        return unsigned_tx.hexlify()
    else:
        return unsigned_tx.hexlify()


def build_input(input_txid: str, input_vout: int):

    return MutableTxIn(txid=input_txid, txout=input_vout, script_sig=ScriptSig.empty(), sequence=Sequence.max())


def finalize_coin2card_exchange(txstr: str, send: bool=False):
    # this is signed by the coin vendor. Basically they add their input and solve it.
    network_params = net_query(provider.network)
    tx = MutableTransaction.unhexlify(txstr, network=network_params)

    my_input = tx.ins[-1] # the coin seller's input is the last one
    my_input_index = len(tx.ins) - 1
    print(my_input_index)
    result = solve_single_input(index=my_input_index, prev_txid=my_input.txid, prev_txout_index=my_input.txout, key=Settings.key, network_params=network_params)
    tx.spend_single(index=my_input_index, txout=result["txout"], solver=result["solver"])
    if send:
        print("Sending transaction.")
        pprint({'txid': sendtx(tx)})

    return tx.hexlify() # this one should be fully signed, or not? Is something like .to_immutable necessary?

def solve_single_input(index: int, prev_txid: str, prev_txout_index: int, key: Kutil, network_params: tuple, sighash: str="ALL", anyonecanpay: bool=False):

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
    # print("tx JSON", prev_tx_json)
    # TODO: this seems to have difficulties with Coinbase TXins. Re-check later.
    #print("tx string", provider.getrawtransaction(prev_txid, 0))
    #print(prev_tx_json.get("time"), prev_tx_json.get("blocktime"))
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



