# at utils

from pypeerassets.at.mutable_transactions import TransactionDraft
from pypeerassets.at.protobuf_utils import serialize_card_extended_data
from pypeerassets.networks import net_query
from decimal import Decimal
from pacli.provider import provider
from pacli.config import Settings

def create_simple_transaction(amount: Decimal, dest_address: str, input_address: str, tx_fee: Decimal=None, change_address: str=None, debug: bool=False):

    dtx = TransactionDraft(fee_coins=tx_fee, provider=provider, debug=debug)
    dtx.add_p2pkh_output(dest_address, coins=amount)
    dtx.add_necessary_inputs(input_address)
    dtx.add_change_output(change_address)
    if debug:
        print("Transaction:", dtx.__dict__)
    return dtx.to_raw_transaction()


def show_txes_by_block(tracked_address: str, endblock: int=None, startblock: int=0, debug: bool=False):
    # VERY SLOW.

    if not endblock:
        endblock = provider.getblockcount()

    tracked_txes = []
    for bh in range(startblock, endblock + 1):
        if debug:
            if bh % 100 == 0:
                print("Block:", bh)
        blockhash = provider.getblockhash(bh)
        block = provider.getblock(blockhash)
        for txid in block["tx"]:
            tx = provider.getrawtransaction(txid, 1)
            total_amount_to_address = Decimal(0)
            try:
                vouts = tx["vout"]
            except KeyError:
                if debug:
                    print("Transaction not considered:", txid)
                continue
            for output in vouts:
                try:
                    output_addr = output["scriptPubKey"]["addresses"][0] # TODO: this only tracks simple scripts.
                except KeyError:
                    if output.get("value") == 0: # PoS coinstake txes
                        continue
                    if output["scriptPubKey"].get("type") == "nulldata":
                        continue # op_return
                    if debug:
                        print("Script not implemented.", txid, output)
                    continue

                if tracked_address == output_addr:
                    total_amount_to_address += Decimal(str(output["value"]))

            if total_amount_to_address == 0:
                continue

            if debug:
                print("TX {} added, value {}.".format(txid, total_amount_to_address))
            try:
                origin = [(inp["txid"], inp["vout"]) for inp in tx["vin"]]
            except KeyError:
                origin = [("coinbase", inp["coinbase"]) for inp in tx["vin"]]


            tracked_txes.append({"height" : bh,
                                 "txid" : txid,
                                 "origin" : origin,
                                 "amount" : total_amount_to_address
                                 })

    return tracked_txes


def create_at_issuance_data(deck, donation_txid: str, receiver: list=None, amount: list=None, donation_vout: int=None, debug: bool=False) -> tuple:
        # note: uses the "claim once per vout" approach instead of "claim once per transaction".

        spending_tx = provider.getrawtransaction(donation_txid, 1) # changed from txid

        spent_amount = 0
        if donation_vout is None:

            for n, output in enumerate(spending_tx["vout"]):
                print("Searching output {}: {}".format(n, output))
                if deck.at_address in output["scriptPubKey"]["addresses"]:
                    donation_vout = n
                    break

        if debug:
            print("AT Address:", deck.at_address)
            print("Donation vout:", donation_vout)

        try:
            assert deck.at_address in spending_tx["vout"][donation_vout]["scriptPubKey"]["addresses"]
            spent_amount = spending_tx["vout"][donation_vout]["value"]
        except (AssertionError, KeyError):
            raise ValueError("This transaction/vout combination does not spend to the tracked address.")

        # TODO: alternative. the next lines are for the donation_tx as a whole approach.
        #for output in spending_tx["vout"]:
        #    if deck.at_address in output["scriptPubKey"]["addresses"]: # changed from tracked_address
        #        # vout = output["n"]
        #        # vout = str(output["n"]).encode("utf-8") # encoding not necessary for protobuf.
        #        spent_amount += output["value"]
        #        # break # we want the complete amount to that address, which can be in more than 1 output.
        #else:
        #    raise Exception("No vout of this transaction spends to the tracked address")

        claimable_amount = spent_amount * deck.multiplier

        if not receiver: # if there is no receiver, spends to himself.
            receiver = [Settings.key.address]

        if not amount:
            amount = [spent_amount]

        if len(amount) != len(receiver):
            raise ValueError("Receiver/Amount mismatch: You have {} receivers and {} amounts.".format(len(receiver), len(amount)))

        if (sum(amount) != claimable_amount): # and (not force): # force option overcomplicates things.
            raise Exception("Amount of cards does not correspond to the spent coins. Use --force to override.")

        if debug:
            print("You are enabled to claim {} tokens.".format(claimable_amount))
            print("Parameters for claim: txid:", donation_txid, "vout:", donation_vout)

        # TODO: for now, hardcoded asset data; should be a pa function call
        # asset_specific_data = b"tx:" + txid.encode("utf-8") + b":" + vout
        asset_specific_data = serialize_card_extended_data(net_query(provider.network), txid=donation_txid, vout=donation_vout)
        return asset_specific_data, amount, receiver



