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
import pacli.extended_txtools as et
import pacli.blockexp_utils as bu
import pacli.db_utils as dbu
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


def show_wallet_dtxes(deckid: str=None,
                      tracked_address: str=None,
                      sender: str=None,
                      unclaimed: bool=False,
                      no_labels: bool=False,
                      advanced: bool=False,
                      wallet: bool=False,
                      keyring: bool=False,
                      quiet: bool=False,
                      # include_change_addresses: bool=False,
                      access_wallet: bool=False,
                      debug: bool=False) -> list:
    """Shows burn/gateway transactions."""

    # MODIF: behaviour is now that if --wallet is chosen, address labels are used when possible.
    # MODIF: if neither sender not wallet is chosen then the P2TH accounts are included (leading to all initialized txes been shown).
    # MODIF: --wallet option now includes all non-P2TH addresses which are named. # TODO re-check if this works here in contrast to claims which have a P2TH to query!

    tx_type_msg = "unclaimed" if unclaimed else "sent"
    txes_to_address = []
    use_db = access_wallet is not None
    datadir = None if type(access_wallet) == bool else access_wallet

    if wallet or (not sender and not no_labels):
        if debug:
            print("Retrieving excluded addresses ...")
        all_decks = pa.find_all_valid_decks(provider, Settings.deck_version, Settings.production)
        if debug:
            print("Processing P2TH ...")
        if wallet is True:
            p2th_dict = eu.get_p2th_dict(decks=all_decks) if wallet is True else {}
            excluded_accounts = p2th_dict.values() # if wallet is True else []
            excluded_addresses = p2th_dict.keys() # if wallet is True else []
        else:
            excluded_accounts, excluded_addresses = [], []
        if debug:
            print("Retrieving labels and wallet addresses (except change) ...")
        addresses = ec.get_labels_and_addresses(empty=True, keyring=keyring, exclude=excluded_addresses, excluded_accounts=excluded_accounts, access_wallet=access_wallet)
        if wallet:
            allowed_addresses = set([a["address"] for a in addresses])
            if debug:
                print("Allowed addresses:", allowed_addresses)

    else:
        excluded_accounts = None

    if deckid:
        if debug:
            print("Retrieving deck data ...")
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        if unclaimed:
            claimed_txes = get_claimed_txes(deck, sender, only_wallet=False)
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

    valid_txes = []
    if use_db is True:
        if debug:
            print("Retrieving transactions from wallet.dat ...")
        # NOTE: set advanced to False to retrieve only the transactions.
        db_txes = dbu.get_all_transactions(firstsender=sender, receiver=tracked_address, sort=True, advanced=False, datadir=datadir, wholetx=True, exclude_coinbase=True, debug=debug)
        db_structs = { txstruct["txid"] : txstruct for txstruct in db_txes }
        if debug:
            print("{} matching transactions found.".format(len(db_structs)))
    elif tracked_address == burn_address(): # and not include_change_addresses: # include_change_addresses needs all wallet txes
        if debug:
            print("Retrieving burn transactions ...")
        burn_txes = get_burn_transactions(create_txes=True, debug=debug)
        if debug:
            print("{} burn transactions found.".format(len(burn_txes)))
        raw_txes = burn_txes
    else:
        if debug:
            print("Retrieving wallet transactions ...")
        raw_txes = eu.get_wallet_transactions(exclude=excluded_accounts, debug=debug)

    if debug and not use_db:
        print(len(raw_txes), "transactions found.")

    # missing_txids = []

    excluded = ["generate", "orphan"]
    if wallet or sender: # wallet mode only needs txes where a wallet address was the sender.
        excluded.append(["receive"])
    if use_db:
        txids = (k for (k, v) in db_structs.items())
    else:
        txids = et.extract_txids_from_utxodict(raw_txes, exclude_cats=excluded, required_address=tracked_address, debug=debug)

    if not quiet: # only needed for message below about number of total transactions
        alltxes = 0

    for txid in txids:
        try:
            if deck is not None:
                full_tx = check_donation_tx_validity(txid, tracked_address, startblock=deck.startblock, endblock=deck.endblock, expected_sender=sender, debug=debug)
            else:
                full_tx = provider.getrawtransaction(txid, 1)
            assert full_tx is not None and full_tx.get("txid") == txid # second condition prevents error message JSONs to be counted.

            if unclaimed:
                assert txid not in claimed_txes

            if use_db and txid in db_structs:
                txstruct = db_structs[txid]
            else:
                txstruct = bu.get_tx_structure(tx=full_tx, human_readable=False, add_txid=True)

        except AssertionError:
            if debug:
                print("Transaction did not pass checks:", txid)
            #if include_change_addresses:
            #    missing_txids.append(tx["txid"])
            continue

        #if not sender:
        #    if not no_labels:
        #        addresses = ec.get_labels_and_addresses(keyring=keyring, empty=True)
        #if wallet and include_change_addresses:
        #    if debug:
        #        print("Retrieving missing transactions for change addresses ...")
        #    missing_txes = [provider.getrawtransaction(txid, 1) for txid in set(missing_txids)]
        #    all_txes = valid_txes + missing_txes
        #    change_addresses = ec.search_change_addresses(known_addresses=addresses, wallet_txes=all_txes, debug=debug)
        #    allowed_addresses.update(set([a["address"] for a in change_addresses]))

        # for txstruct in valid_txes:

        # txstruct = bu.get_tx_structure(tx=tx, human_readable=False) if not use_db else tx

        if txstruct is None:
            continue
        elif debug:
            print("Burn/Gateway TX found:", txstruct)

        if not quiet:
            alltxes += 1

        # sender is always the first sender, as specified in AT protocol.
        tx_sender = txstruct["inputs"][0]["sender"][0]
        if wallet:
            if tx_sender not in allowed_addresses:
                if debug:
                    print("Transaction {} excluded: no wallet transaction proper (e.g. P2TH). Sender: {}".format(txid, tx_sender))
                continue

        if advanced is True:
            tx_dict = full_tx
        else:
            tx_dict = et.return_tx_format("gatewaytx", txstruct=txstruct, tracked_address=tracked_address, debug=debug)
            if tx_dict is None:
                continue

            if not sender:
                if not no_labels:
                    for item in addresses:
                        if item["address"] == tx_sender:
                            if ("label" in item) and (item["label"] not in (None, "")):
                                tx_dict.update({"sender_label" : item["label"]})
                            break

                tx_dict.update({"sender_address" : tx_sender})
        txes_to_address.append(tx_dict)

    if not quiet:
        print("{} {} total transactions to address {} tracked by this wallet.".format(alltxes, tx_type_msg, tracked_address)) # len(valid_txes) became len(txids)
        if sender is not None:
            print("Showing only transactions sent from the following address:", sender)
        elif wallet is True:
            print("Showing only transaction sent from this wallet (excluding P2TH addresses).")

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
