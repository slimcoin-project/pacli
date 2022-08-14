# Commands specific for DT tokens in standard pacli classes

import pacli.dt_utils as du
import pacli.dt_interface as di
import pypeerassets as pa
import pypeerassets.at.dt_misc_utils as dmu
from prettyprinter import cpprint as pprint
from pypeerassets.at.dt_parser_utils import deck_from_tx
from pypeerassets.at.transaction_formats import setfmt
from pypeerassets.legacy import is_legacy_blockchain, legacy_import

from pacli.provider import provider
from pacli.config import Settings

# Address

def show_votes_by_address(deckid, address):
    # TODO: cleanup print statements!
    # shows all valid voting transactions from a specific address, for all proposals.

    pprint("Votes cast from address: " + address)
    vote_readable = { b'+' : 'Positive', b'-' : 'Negative' }
    deck = deck_from_tx(deckid, provider)

    try:
        pst = dmu.get_parser_state(provider, deck, force_continue=True, force_dstates=True)
        # pst = ParserState(deck, [], provider)
    except AttributeError:
        print("This seems not to be a proof-of-donation deck. No vote count possible.")
        return

    pstates = pst.proposal_states

    if not pstates:
        print("No proposals recorded for this deck.")
        return

    for proposal in pstates:
        phase, phaselist = 0, []
        for phase, phaselist in enumerate(pstates[proposal].voting_txes):
            for vtx in phaselist:
                if vtx.sender == address:
                    pprint("-----------------------------------------")
                    pprint("Vote: " + vote_readable[vtx.vote])
                    pprint("Proposal: " + proposal)
                    pprint("Phase: " + str(phase))
                    pprint("Vote txid: " + vtx.txid)
                    pprint("Weight: " + str(vtx.weight))


def show_donations_by_address(deckid, address):
    # shows all valid donation transactions from a specific address, for all proposals.

    pprint("Donations realized from address: " + address)
    deck = deck_from_tx(deckid, provider)

    try:
        pst = dmu.get_parser_state(provider, deck, force_continue=True, force_dstates=True)

    except AttributeError:
        print("This seems not to be a proof-of-donation deck. No donation count possible.")
        return

    pstates = pst.proposal_states

    if not pstates:
        print("No proposals recorded for this deck.")
        return

    for proposal in pstates:
        for rd, rdlist in enumerate(pstates[proposal].donation_states):
            for dstate in rdlist.values():
                # print(dstate.__dict__)
                if (dstate.donor_address == address) and (dstate.donation_tx is not None):
                    pprint("-----------------------------------------")
                    pprint("Proposal: " + proposal)
                    pprint("Round: " + str(rd))
                    pprint("Amount: " + str(dstate.donated_amount))
                    pprint("Donation txid: " + dstate.donation_tx.txid)



# Deck


def init_deck(network, deckid, rescan=True):
    deck = deck_from_tx(deckid, provider)
    if deckid not in provider.listaccounts():
        provider.importprivkey(deck.p2th_wif, deck.id, rescan)
        print("Importing P2TH address from deck.")
    else:
        print("P2TH address was already imported.")
    check_addr = provider.validateaddress(deck.p2th_address)
    print("Output of validation tool:\n", check_addr)
        # load_deck_p2th_into_local_node(provider, deck) # we don't use this here because it doesn't provide the rescan option



def init_dt_deck(network_name, deckid, rescan=True):
    # MODIFIED: added support for legacy blockchains
    deck = deck_from_tx(deckid, provider)
    legacy = is_legacy_blockchain(network_name)

    if "sdp_deckid" not in deck.__dict__.keys():
        print("No SDP (voting) token found for this deck. This is probably not a proof-of-donation deck!")
        return

    if deck.id not in provider.listaccounts():
        print("Importing main key from deck.")
        load_deck_p2th_into_local_node(provider, deck)

    for tx_type in ("proposal", "signalling", "locking", "donation", "voting"):
        p2th_addr = deck.derived_p2th_address(tx_type)
        print("Importing {} P2TH address: {}".format(tx_type, p2th_addr))
        if legacy:
            p2th_wif = deck.derived_p2th_wif(tx_type)
            legacy_import(provider, p2th_addr, p2th_wif, rescan)
        else:
            dmu.import_p2th_address(provider, p2th_addr)

    # SDP
    # Note: there can be a None value for sdp_deckid even if this is a PoD token (e.g. in the case of a swap).
    if deck.sdp_deckid is not None:
        p2th_sdp_addr = pa.Kutil(network=network_name,
                             privkey=bytearray.fromhex(deck.sdp_deckid)).address

        print("Importing SDP P2TH address: {}".format(p2th_sdp_addr))

        if legacy:
            p2th_sdp_wif = pa.Kutil(network=network_name,
                             privkey=bytearray.fromhex(deck.sdp_deckid)).wif
            legacy_import(provider, p2th_sdp_addr, p2th_sdp_wif, rescan)
        else:
            dmu.import_p2th_address(provider, p2th_sdp_addr)
    if rescan:
        if not legacy:
            print("Rescanning ...")
            provider.rescanblockchain()
    print("Done.")

def get_deckinfo(deckid, p2th: bool=False):
    d = deck_from_tx(deckid, provider)
    d_dict = d.__dict__
    if p2th:
        print("Showing P2TH addresses.")
        # the following code generates the addresses, so it's not necessary to add them to the dict.
        p2th_dict = {"p2th_main": d.p2th_address,
                      "p2th_proposal" : d.derived_p2th_address("proposal"),
                      "p2th_signalling" : d.derived_p2th_address("signalling"),
                      "p2th_locking" : d.derived_p2th_address("locking"),
                      "p2th_donation" : d.derived_p2th_address("donation"),
                      "p2th_voting" : d.derived_p2th_address("voting")}
        # d_dict.update(p2th_dict)
    return d_dict


def list_dt_decks():
    # TODO: This does not catch some errors with invalid decks which are displayed:
    # InvalidDeckSpawn ("InvalidDeck P2TH.") -> not catched in deck_parser in pautils.py
    # 'error': 'OP_RETURN not found.' -> InvalidNulldataOutput , in pautils.py
    # 'error': 'Deck () metainfo incomplete, deck must have a name.' -> also in pautils.py, defined in exceptions.py.

    decks = pa.find_all_valid_decks(provider,
                                    Settings.deck_version,
                                    Settings.production)
    dt_decklist = []
    for d in decks:
        try:
            if d.at_type == "DT":
                dt_decklist.append(d)
        except AttributeError:
            continue

    return dt_decklist

def dt_state(deckid, debug: bool=False, debug_voting: bool=False, debug_donations: bool=False):
    # prints the ParserState (DTDeckState).
    deck = deck_from_tx(deckid, provider)
    pst_dict = dmu.get_parser_state(provider, deck, force_continue=True, force_dstates=True, debug=debug, debug_voting=debug_voting, debug_donations=debug_donations).__dict__
    di.prepare_dict(pst_dict, only_txids=["initial_cards", "sdp_cards", "donation_txes"], only_id=["sdp_deck", "deck"], only_ids = ["proposal_states", "approved_proposals", "valid_proposals"])
    # di.prepare_complete_dict(pst.__dict__)

    pprint(pst_dict)

def show_p2th(self, proposal_id: str):
    # prints all P2TH addresses
    pass

# Card

def claim_pod_tokens(proposal_id: str, donor_address: str, payment: list=None, receiver: list=None, deckid: str=None, donation_vout: int=2, donation_txid: str=None, proposer: bool=False, force: bool=False, debug: bool=False):


    if not receiver: # if there is no receiver, the coins are directly allocated to the donor.
        receiver = [Settings.key.address]

    if not force:
        print("Calculating reward ...")
        try:
            reward_data = du.get_pod_reward_data(proposal_id, donor_address, proposer=proposer, debug=debug)
        except Exception as e:
            print(e)
            return None
        deckid = reward_data.get("deckid")
        max_payment = reward_data.get("reward")
        donation_txid = reward_data.get("donation_txid")
    elif not deckid:
        print("ERROR: No deckid provided, if you use --force you need to provide it.")
        return None
    elif payment is not None:
        max_payment = sum(payment)
        print("WARNING: Overriding reward calculation. If you calculated your payment incorrectly, the transaction will be invalid.")
    else:
        print("ERROR: No payment data provided.")
        return None

    if payment is None:
        payment = [max_payment]
    else:
        if sum(payment) > max_payment:
            raise Exception("Amount of cards does not correspond to the spent coins. Use --force to override.")
        rest_amount = max_payment - sum(payment)
        if rest_amount > 0:
            receiver.append(donor_address)
            payment.append(rest_amount)


    params = { "id" : "DT", "dtx" : donation_txid, "out" : donation_vout}
    asset_specific_data = setfmt(params, tx_type="cardissue_dt")
    return asset_specific_data, receiver, payment, deckid
