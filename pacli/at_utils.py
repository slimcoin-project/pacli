import pypeerassets as pa
from pypeerassets.pautils import find_tx_sender
from pypeerassets.at.mutable_transactions import TransactionDraft
from pypeerassets.at.protobuf_utils import serialize_card_extended_data
from pypeerassets.at.constants import ID_AT
from pypeerassets.networks import net_query
from decimal import Decimal
from pacli.provider import provider
from pacli.config import Settings
import pacli.extended_utils as eu
from prettyprinter import cpprint as pprint

def create_simple_transaction(amount: Decimal, dest_address: str, input_address: str, tx_fee: Decimal=None, change_address: str=None, debug: bool=False):

    dtx = TransactionDraft(fee_coins=tx_fee, provider=provider, debug=debug)
    dtx.add_p2pkh_output(dest_address, coins=amount)
    dtx.add_necessary_inputs(input_address)
    dtx.add_change_output(change_address)
    if debug:
        print("Transaction:", dtx.__dict__)
    return dtx.to_raw_transaction()


def show_wallet_txes(deckid: str=None, tracked_address: str=None, input_address: str=None, unclaimed: bool=False, burntxes: bool=False) -> list:
    # in this simple form it doesn't show from which address the originated, it shows all from the wallet.
    raw_txes = []
    print("input address:", input_address)
    if unclaimed and deckid: # works only with deckid!
        claims = get_claim_transactions(deckid, input_address)

    if deckid:
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        try:
            tracked_address = deck.at_address
        except AttributeError:
            raise ValueError("Deck ID {} does not reference an AT deck.".format(deckid))

    raw_txes = eu.get_wallet_transactions()
    # print([t["address"] for t in raw_txes if t["category"] == "send"])
    filtered_txes = [t for t in raw_txes if ((t["category"] == "send") and (t["address"] == tracked_address))]

    txids = set([t["txid"] for t in filtered_txes])
    print("{} sent transactions to address {} in this wallet.".format(len(txids), tracked_address))
    txes_to_address = []
    for txid in txids:
        rawtx = provider.getrawtransaction(txid, 1)
        # protocol defines that only address spending first input is counted.
        # so we can use find_tx_sender from pautils.
        if input_address:
            if find_tx_sender(provider, rawtx) != input_address:
                continue

        value, indexes = 0, []
        for index, output in enumerate(rawtx["vout"]):
            if output["scriptPubKey"]["addresses"][0] == tracked_address:
                value += Decimal(str(output["value"]))
                indexes.append(index)

        tx_dict = {"txid" : txid, "value" : value, "outputs" : indexes }
        txes_to_address.append(tx_dict)

    return txes_to_address


def show_txes_by_block(tracked_address: str, deckid: str=None, endblock: int=None, startblock: int=0, debug: bool=False) -> list:
    # VERY SLOW. When watchaddresses are available this should be replaced.

    if not endblock:
        endblock = provider.getblockcount()

    if deckid:
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        try:
            tracked_address = deck.at_address
        except AttributeError:
            raise ValueError("Deck ID {} does not reference an AT deck.".format(deckid))

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


def create_at_issuance_data(deck, donation_txid: str, receiver: list=None, amount: list=None, debug: bool=False) -> tuple:
        # note: uses now the "claim once per transaction" approach.

        spending_tx = provider.getrawtransaction(donation_txid, 1) # changed from txid

        spent_amount = 0

        # old protocol: claim once per vout
        #if donation_vout is None:
        #
        #    for n, output in enumerate(spending_tx["vout"]):
        #        print("Searching output {}: {}".format(n, output))
        #        if deck.at_address in output["scriptPubKey"]["addresses"]:
        #            donation_vout = n
        #            break

        vouts = []
        for output in spending_tx["vout"]:
            if deck.at_address in output["scriptPubKey"]["addresses"]: # changed from tracked_address
                # TODO: maybe we need a check for the script type
                vouts.append(output["n"]) # used only for debugging/printouts
                spent_amount += output["value"]

        if len(vouts) == 0:
            raise Exception("No vout of this transaction spends to the tracked address")

        if debug:
            print("AT Address:", deck.at_address)
            print("Donation output indexes (vouts):", vouts)
            # print("Donation vout:", donation_vout)

        # old protocol
        #try:
        #    assert deck.at_address in spending_tx["vout"][donation_vout]["scriptPubKey"]["addresses"]
        #    spent_amount = spending_tx["vout"][donation_vout]["value"]
        #except (AssertionError, KeyError):
        #    raise ValueError("This transaction/vout combination does not spend to the tracked address.")

        claimable_amount = spent_amount * deck.multiplier

        if not receiver: # if there is no receiver, spends to himself.
            receiver = [Settings.key.address]

        if not amount:
            amount = [claimable_amount]

        if len(amount) != len(receiver):
            raise ValueError("Receiver/Amount mismatch: You have {} receivers and {} amounts.".format(len(receiver), len(amount)))

        if (sum(amount) != claimable_amount): # and (not force): # force option overcomplicates things.
            raise Exception("Amount of cards does not correspond to the spent coins. Use --force to override.")

        if debug:
            print("You are enabled to claim {} tokens.".format(claimable_amount))
            print("TXID with transfer enabling claim:", donation_txid)

        asset_specific_data = serialize_card_extended_data(net_query(provider.network), txid=donation_txid)
        return asset_specific_data, amount, receiver


def at_deckinfo(deckid):
    #for deck in eu.list_decks("at"):
    for deck in dmu.list_decks_by_at_type(ID_AT):
        if deck.id == deckid:
            break

    for deck_param in deck.__dict__.keys():
        pprint("{}: {}".format(deck_param, deck.__dict__[deck_param]))

def get_claim_transactions(deckid: str, input_address: str):
    cards = pa.find_all_valid_cards(deckid)
    ds = pa.protocol.DeckState(cards)
    cards = ds.valid_cards()
    claim_txes = []
    for card in cards:
        if card.type == "CardIssue" and card.sender == input_address:
            claim_txes.append(card)
    return claim_txes


