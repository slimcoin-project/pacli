from prettyprinter import cpprint as pprint
from decimal import Decimal
import pypeerassets as pa
import pypeerassets.at.at_parser as ap
import pypeerassets.at.dt_misc_utils as dmu
from pypeerassets.pautils import find_tx_sender
from pypeerassets.at.mutable_transactions import TransactionDraft
from pypeerassets.at.protobuf_utils import serialize_card_extended_data
from pypeerassets.at.constants import ID_AT
from pypeerassets.networks import net_query
from pypeerassets.exceptions import UnsupportedNetwork
import pacli.extended_utils as eu
import pacli.extended_interface as ei
from pacli.provider import provider
from pacli.config import Settings

def create_simple_transaction(amount: Decimal, dest_address: str, input_address: str, tx_fee: Decimal=None, change_address: str=None, debug: bool=False):
    """Creates a simple coin transaction from a pre-selected address."""

    dtx = TransactionDraft(fee_coins=tx_fee, provider=provider, debug=debug)
    dtx.add_p2pkh_output(dest_address, coins=amount)
    dtx.add_necessary_inputs(input_address)
    dtx.add_change_output(change_address)
    if debug:
        print("Transaction:", dtx.__dict__)
    return dtx.to_raw_transaction()


def show_wallet_dtxes(deckid: str=None, tracked_address: str=None, input_address: str=None, unclaimed: bool=False, silent: bool=False, debug: bool=False) -> list:

    if deckid:
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        if unclaimed:
            claimed_txes = get_claimed_txes(deck, input_address, only_wallet=True)
            if debug:
                print("Transactions you already claimed tokens for of this deck:", claimed_txes)
        try:
            if not tracked_address:
                tracked_address = deck.at_address
        except AttributeError:
            raise ei.PacliInputDataError("Deck ID {} does not reference an AT deck.".format(deckid))
    else:
        deck = None
        if unclaimed:
            raise ei.PacliInputDataError("You need to provide a Deck ID to show unclaimed transactions.")
        if not tracked_address:
            raise ei.PacliInputDataError("You need to provide a tracked address or a Deck ID for this command.")

    raw_txes = eu.get_wallet_transactions()

    valid_txes = []
    for tx in raw_txes:
        try:
            assert tx["category"] == "send"
            assert tx["address"] == tracked_address
            if deck is not None:
                full_tx = check_donation_tx_validity(tx["txid"], tracked_address, startblock=deck.startblock, endblock=deck.endblock, expected_sender=input_address)
                assert full_tx is not None
            else:
                full_tx = provider.getrawtransaction(tx["txid"], 1)
            if unclaimed:
                assert tx["txid"] not in claimed_txes
            valid_txes.append(full_tx)

        except AssertionError:
            continue

    txids = set([t["txid"] for t in valid_txes])
    tx_type_msg = "unclaimed" if unclaimed else "sent"

    if not silent:
        print("{} {} transactions to address {} in this wallet.".format(len(txids), tx_type_msg, tracked_address))
    if input_address is not None:
        print("Showing only transactions sent from the following address:", input_address)

    txes_to_address = []
    for tx in valid_txes:

        sender = find_tx_sender(provider, tx)
        try:
            height = provider.getblock(tx["blockhash"])["height"]
        except KeyError:
            height = None

        value, indexes = 0, []
        for index, output in enumerate(tx["vout"]):
            if output["scriptPubKey"]["addresses"][0] == tracked_address:
                value += Decimal(str(output["value"]))
                indexes.append(index)

        tx_dict = {"txid" : tx["txid"], "value" : value, "outputs" : indexes, "height" : height}
        if not input_address:
            tx_dict.update({"sender" : sender})
        txes_to_address.append(tx_dict)

    return txes_to_address


def show_txes_by_block(tracked_address: str, deckid: str=None, endblock: int=None, startblock: int=0, silent: bool=False, debug: bool=False) -> list:
    # VERY SLOW. When watchaddresses are available this should be replaced.

    if not endblock:
        endblock = provider.getblockcount()
    if (not silent) and ((endblock - startblock) > 10000):
        print("""
              NOTE: This commands cycles through all blocks and will take very long
              to finish. It's recommended to use it for block ranges of less than 10000 blocks.
              Abort and get results with CTRL-C.
              """)

    if deckid:
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        try:
            tracked_address = deck.at_address
        except AttributeError:
            raise ei.PacliInputDataError("Deck ID {} does not reference an AT deck.".format(deckid))

    tracked_txes = []

    for bh in range(startblock, endblock + 1):
        try:
            if not silent and bh % 100 == 0:
                print("Processing block:", bh)
            blockhash = provider.getblockhash(bh)
            block = provider.getblock(blockhash)

            try:
                block_txes = block["tx"]
            except KeyError:
                print("You have reached the tip of the blockchain.")
                return tracked_txes

            for txid in block_txes:
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
        except KeyboardInterrupt:
            break

    return tracked_txes

def check_donation_tx_validity(txid: str, tracked_address: str, startblock: int=None, endblock: int=None, expected_sender: str=None, debug: bool=False):
    # checks the validity of a donation/burn transaction
    try:
        raw_tx = ap.check_donation(provider, txid, tracked_address, startblock=startblock, endblock=endblock)
        if expected_sender:
            if not expected_sender == find_tx_sender(provider, raw_tx):
                if debug:
                    print("Unexpected sender", sender)
                return None
        return raw_tx
    except Exception as e:
        if debug:
            print("TX {} invalid:".format(txid), e)
        return None



def create_at_issuance_data(deck, donation_txid: str, sender: str, receivers: list=None, amounts: list=None, payto: str=None, payamount: Decimal=None, debug: bool=False, force: bool=False) -> tuple:
        # note: uses now the "claim once per transaction" approach.

        spending_tx = provider.getrawtransaction(donation_txid, 1) # changed from txid

        if sender != find_tx_sender(provider, spending_tx):
            raise ei.PacliInputDataError("You cannot claim coins for another sender.")

        if donation_txid in get_claimed_txes(deck, sender):
            raise ei.PacliInputDataError("Duplicate. You already have claimed the coins from this transaction successfully.")

        spent_amount = Decimal(0)

        vouts = []
        for output in spending_tx["vout"]:
            if deck.at_address in output["scriptPubKey"]["addresses"]: # changed from tracked_address
                # TODO: maybe we need a check for the script type
                vouts.append(output["n"]) # used only for debugging/printouts
                spent_amount += Decimal(str(output["value"]))

        if len(vouts) == 0:
            raise ei.PacliInputDataError("This transaction does not spend coins to the tracked address")

        if debug:
            print("AT Address:", deck.at_address)
            print("Donation output indexes (vouts):", vouts)

        claimable_amount = spent_amount * deck.multiplier

        if not receivers:
            # payto and payamount enable easy payment to a second address,
            # even if not the full amount is paid
            if payto:
               if (payamount is None) or (payamount == claimable_amount):
                   amounts = [claimable_amount]
                   receivers = [payto]
               elif payamount < claimable_amount:
                   amounts = [payamount, claimable_amount - payamount]
                   receivers = [payto, Settings.key.address]
               else:
                   raise ei.PacliInputDataError("Claimed amount {} higher than available amount {}.".format(payamount, claimable_amount))

            # if there is no receiver, spends to himself.
            else:
               receivers = [Settings.key.address]

        if not amounts:
            amounts = [claimable_amount]

        if len(amounts) != len(receivers):
            raise ei.PacliInputDataError("Receiver/Amount mismatch: You have {} receivers and {} amounts.".format(len(receivers), len(amount)))

        if (sum(amounts) != claimable_amount) and (not force): # force option overcomplicates things.
            raise ei.PacliInputDataError("Amount of cards does not correspond to the spent coins. Use --force to override.")

        if debug:
            print("You are enabled to claim {} tokens.".format(claimable_amount))
            print("TXID with transfer enabling claim:", donation_txid)

        asset_specific_data = serialize_card_extended_data(net_query(provider.network), txid=donation_txid)
        return asset_specific_data, amounts, receivers


def at_deckinfo(deckid):
    for deck in dmu.list_decks_by_at_type(provider, ID_AT):
        if deck.id == deckid:
            break
    else:
        print("Deck not found or not valid.")
        return

    for deck_param in deck.__dict__.keys():
        pprint("{}: {}".format(deck_param, deck.__dict__[deck_param]))

def get_valid_cardissues(deck: object, input_address: str=None, only_wallet: bool=False) -> list:
    # NOTE: Sender no longer necessary.

    wallet_txids = set([t["txid"] for t in eu.get_wallet_transactions()]) if (only_wallet and not input_address) else None

    cards = pa.find_all_valid_cards(provider, deck)
    ds = pa.protocol.DeckState(cards)
    claim_cards = []
    for card in ds.valid_cards:
        if card.type == "CardIssue":
            if (input_address and (card.sender == input_address)) \
            or (wallet_txids and (card.txid in wallet_txids)) \
            or ((input_address is None) and not wallet_txids):
                claim_cards.append(card)
    return claim_cards

def get_claimed_txes(deck: object, input_address: str, only_wallet: bool=False) -> set:
    # returns TXIDs of already claimed txes.
    return set([c.donation_txid for c in get_valid_cardissues(deck, input_address, only_wallet=only_wallet)])

def burn_address():
    if not provider.network.endswith("slm"):
        raise UnsupportedNetwork("Unsupported network for burn tokens.")
    if provider.network[0] == "t":
        return "mmSLiMCoinTestnetBurnAddress1XU5fu"
    else:
        return "SfSLMCoinMainNetworkBurnAddr1DeTK5"


