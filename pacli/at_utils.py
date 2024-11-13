from prettyprinter import cpprint as pprint
from btcpy.structs.address import InvalidAddress
from decimal import Decimal
import pypeerassets as pa
import pypeerassets.at.at_parser as ap
import pypeerassets.at.dt_misc_utils as dmu
import pypeerassets.at.constants as c
from pypeerassets.pautils import find_tx_sender
from pypeerassets.at.mutable_transactions import TransactionDraft
from pypeerassets.at.protobuf_utils import serialize_card_extended_data
from pypeerassets.networks import net_query
from pypeerassets.exceptions import UnsupportedNetwork
import pacli.extended_utils as eu
import pacli.extended_interface as ei
import pacli.extended_commands as ec
import pacli.extended_constants as extc
import pacli.blockexp_utils as bu
from pacli.provider import provider
from pacli.config import Settings

def create_simple_transaction(amount: Decimal, dest_address: str, tx_fee: Decimal=None, change_address: str=None, debug: bool=False):
    """Creates a simple coin transaction from a pre-selected address."""

    try:
        dtx = TransactionDraft(fee_coins=tx_fee, provider=provider, debug=debug)
        dtx.add_p2pkh_output(dest_address, coins=amount)
        dtx.add_necessary_inputs(Settings.key.address)
        dtx.add_change_output(change_address)
        if debug:
            print("Transaction:", dtx.__dict__)
        return dtx.to_raw_transaction()
    except InvalidAddress:
        if debug:
            raise
        else:
            raise ei.PacliInputDataError("Invalid address string. Please provide a correct address or label.")


def show_wallet_dtxes(deckid: str=None, tracked_address: str=None, sender: str=None, unclaimed: bool=False, quiet: bool=False, no_labels: bool=False, advanced: bool=False, wallet: bool=False, keyring: bool=False, debug: bool=False) -> list:
    """Shows donation/burn/payment transactions."""

    # MODIF: behaviour is now that if --wallet is chosen, address labels are used when possible.
    # MODIF: if neither sender not wallet is chosen then the P2TH accounts are included (leading to all initialized txes been shown).
    # MODIF: command now includes all non-P2TH addresses which are named.
    if wallet or (not sender and not no_labels):
        excluded_accounts = eu.get_p2th(accounts=True) if wallet is True else []
        excluded_addresses = eu.get_p2th() if wallet is True else []
        addresses = ec.get_labels_and_addresses(empty=True, keyring=keyring, exclude=excluded_addresses)
        if wallet:
            allowed_addresses = set([a["address"] for a in addresses])

    else:
        excluded_accounts = None

    if deckid:
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        if unclaimed:
            claimed_txes = get_claimed_txes(deck, sender, only_wallet=True)
            if debug:
                print("Transactions you already claimed tokens for of this deck:", claimed_txes)
        try:
            if not tracked_address:
                tracked_address = deck.at_address
            elif tracked_address != deck.at_address:
                error_message = "Gateway address mismatch."
                if tracked_address == burn_address():
                    error_message += " Probably you are using a command for PoB tokens for an AT token. Please use the command/flag for AT tokens instead."
                raise ei.PacliInputDataError(error_message)


            assert deck.at_type == c.ID_AT

        except (AttributeError, AssertionError):
            raise ei.PacliInputDataError("Deck {} is not an AT or PoB token deck.".format(deckid))


    else:
        deck = None
        if unclaimed:
            raise ei.PacliInputDataError("You need to provide a Deck to show unclaimed transactions.")
        if not tracked_address:
            raise ei.PacliInputDataError("You need to provide a tracked address or a Deck for this command.")

    if tracked_address == burn_address():
        burn_txes = get_burn_transactions(create_txes=True, debug=debug)
        if debug:
            print("{} burn transactions found.".format(len(burn_txes)))
        raw_txes = burn_txes
    else:
        raw_txes = eu.get_wallet_transactions(exclude=excluded_accounts, debug=debug)

    if debug:
        print(len(raw_txes), "wallet transactions found.")

    valid_txes = []
    processed_txids = []
    for tx in raw_txes:
        try:
            assert tx["txid"] not in processed_txids
            assert tx["category"] not in ("generate", "orphan")
            assert tx["address"] == tracked_address
            if wallet or sender:
                assert tx["category"] != "receive"

        except (AssertionError, KeyError):
            continue
        try:
            if deck is not None:
                full_tx = check_donation_tx_validity(tx["txid"], tracked_address, startblock=deck.startblock, endblock=deck.endblock, expected_sender=sender, debug=debug)
                assert full_tx is not None
            else:
                full_tx = provider.getrawtransaction(tx["txid"], 1)
            if unclaimed:
                assert tx["txid"] not in claimed_txes

            processed_txids.append(tx["txid"])
            valid_txes.append(full_tx)

        except AssertionError:
            if debug:
                print("Transaction did not pass checks:", tx["txid"])
            continue

    tx_type_msg = "unclaimed" if unclaimed else "sent"

    if not quiet:
        print("{} {} total transactions to address {} tracked by this wallet.".format(len(valid_txes), tx_type_msg, tracked_address))
        if sender is not None:
            print("Showing only transactions sent from the following address:", sender)
        elif wallet is True:
            print("Showing only transaction sent from this wallet (excluding P2TH addresses).")

    txes_to_address = []
    #if not sender:
    #    if not no_labels:
    #        addresses = ec.get_labels_and_addresses(keyring=keyring, empty=True)

    for tx in valid_txes:

        txstruct = bu.get_tx_structure(tx=tx, tracked_address=tracked_address, human_readable=False)

        if txstruct is None:
            continue
        elif debug:
            print("Burn/Gateway TX found:", txstruct)

        # MODIF: sender is always the first sender, as specified in AT protocol.
        tx_sender = txstruct["sender"]["sender"][0]
        if wallet:
            if tx_sender not in allowed_addresses:
                if debug:
                    print("Transaction {} excluded: no wallet transaction proper.".format(tx["txid"]))
                continue

        if advanced is True:
            tx_dict = tx
        else:
            tx_dict = {"txid" : tx["txid"], "value" : txstruct["ovalue"], "outputs" : txstruct["oindices"], "blockheight" : txstruct["blockheight"]}

            if not sender:
                if not no_labels:
                    for item in addresses:
                        if item["address"] == tx_sender:
                            if ("label" in item) and (item["label"] not in (None, "")):
                                tx_dict.update({"sender_label" : item["label"]})
                            break

                tx_dict.update({"sender_address" : tx_sender})
        txes_to_address.append(tx_dict)

    return txes_to_address

def check_donation_tx_validity(txid: str, tracked_address: str, startblock: int=None, endblock: int=None, expected_sender: str=None, debug: bool=False):
    # checks the validity of a donation/burn transaction
    try:
        raw_tx = ap.check_donation(provider, txid, tracked_address, startblock=startblock, endblock=endblock, debug=debug)
        if expected_sender:
            sender = find_tx_sender(provider, raw_tx)
            if not expected_sender == sender:
                if debug:
                    print("Unexpected sender", sender)
                return None
        return raw_tx
    except Exception as e:
        if debug:
            print("TX {} invalid:".format(txid), e)
        return None


def create_at_issuance_data(deck, donation_txid: str, sender: str, receivers: list=None, amounts: list=None, payto: str=None, payamount: Decimal=None, debug: bool=False, force: bool=False) -> tuple:
        # note: uses the "claim once per transaction" approach.

        spending_tx = provider.getrawtransaction(donation_txid, 1) # changed from txid

        try:
            assert sender == find_tx_sender(provider, spending_tx)
        except AssertionError:
            raise ei.PacliInputDataError("You cannot claim coins for another sender.")
        except KeyError:
            raise ei.PacliInputDataError("The transaction you referenced is invalid.")

        if donation_txid in get_claimed_txes(deck, sender):
            raise ei.PacliInputDataError("Duplicate. You already have claimed the coins from this transaction successfully.")

        spent_amount = Decimal(0)

        vouts = []
        for output in spending_tx["vout"]:
            try:
                if deck.at_address in output["scriptPubKey"]["addresses"]: # changed from tracked_address
                    # TODO: maybe we need a check for the script type
                    vouts.append(output["n"]) # used only for debugging/printouts
                    spent_amount += Decimal(str(output["value"]))
            except KeyError: # OP_RETURN or other non-P2[W]PKH outputs
                continue

        if len(vouts) == 0:
            raise ei.PacliInputDataError("This transaction does not spend coins to the tracked address")

        if debug:
            print("AT Address:", deck.at_address)
            print("Donation output indexes (vouts):", vouts)

        # min_claimable_amount = Decimal(str(1 / (10 ** deck.number_of_decimals)))
        min_claimable_amount = 10 ** -Decimal(str(deck.number_of_decimals))
        claimable_amount = ((spent_amount * deck.multiplier) // min_claimable_amount) * (10**-Decimal(str(deck.number_of_decimals)))

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
            amounts_sum = claimable_amount
        else:
            amounts_sum = Decimal("0")
            for amount in amounts:
                amounts_sum  += Decimal(str(amount))

        if debug:
           print("Amount(s) to send:", amounts)
           print("Receiver(s):", receivers)

        if len(amounts) != len(receivers):
            raise ei.PacliInputDataError("Receiver/Amount mismatch: You have {} receivers and {} amounts.".format(len(receivers), len(amounts)))

        if (amounts_sum != claimable_amount) and (not force): # force option overcomplicates things.
            if abs(amounts_sum - claimable_amount) < min_claimable_amount:
                msg_decimals = " You cannot claim amounts with more than {} decimals for this token. Please round the provided amount(s).".format(deck.number_of_decimals)
            else:
                msg_decimals = ""
            raise ei.PacliInputDataError("The sum of the claimed tokens ({}) does not correspond to the claimable amount ({}).{}".format(amounts_sum, claimable_amount, msg_decimals))

        if debug:
            print("You are enabled to claim {} tokens.".format(claimable_amount))
            print("TXID with transfer enabling claim:", donation_txid)

        asset_specific_data = serialize_card_extended_data(net_query(provider.network), txid=donation_txid)
        return asset_specific_data, amounts, receivers


def at_deckinfo(deckid):
    for deck in dmu.list_decks_by_at_type(provider, c.ID_AT):
        if deck.id == deckid:
            break
    else:
        print("Deck not found or not valid.")
        return

    for deck_param in deck.__dict__.keys():
        pprint("{}: {}".format(deck_param, deck.__dict__[deck_param]))


def get_claimed_txes(deck: object, sender: str, only_wallet: bool=False) -> set:
    # returns TXIDs of already claimed txes.
    return set([c.donation_txid for c in eu.get_valid_cardissues(deck, sender, only_wallet=only_wallet)])

def burn_address():
    if not provider.network.endswith("slm"):
        raise UnsupportedNetwork("Unsupported network for burn tokens.")
    return extc.BURN_ADDRESS[provider.network]

def get_burn_transactions(create_txes: bool=False, debug: bool=False) -> list:
    # EXPERIMENTAL. Seeks to complement the other tx tools.
    burndata = provider.getburndata()
    burntxes = []
    burnaddr = burn_address()
    for entry in burndata:
        if "txid" in entry:
            if create_txes:
                tx_dict = {"txid" : entry["txid"],
                           "category" : "burn",
                           "address" : burnaddr}
                burntxes.append(tx_dict)
            else:
                burntxes.append(entry["txid"])
    return burntxes


# API commands

def my_txes(address: str=None, deck: str=None, sender: str=None, unclaimed: bool=False, wallet: bool=False, no_labels: bool=False, keyring: bool=False, advanced: bool=False, quiet: bool=False, debug: bool=False, burns: bool=False) -> None:
    '''Shows all transactions from your wallet to an address.'''
    # TODO this could be simply removed and show_wallet_dtxes accessed directly with au.burn_address().

    if burns:
         if debug:
             print("Using burn address.")
         address = burn_address()

    deckid = eu.search_for_stored_tx_label("deck", deck, quiet=quiet) if deck else None
    #if sender is None:
    #    sender = Settings.key.address if not wallet else None
    txes = show_wallet_dtxes(tracked_address=address, deckid=deckid, unclaimed=unclaimed, sender=sender, no_labels=no_labels, keyring=keyring, advanced=advanced, wallet=wallet, quiet=quiet, debug=debug)

    return txes

