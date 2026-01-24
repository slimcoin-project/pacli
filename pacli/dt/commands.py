# Commands specific for DT tokens in standard pacli classes

import pypeerassets as pa
import pypeerassets.at.dt_misc_utils as dmu
import pypeerassets.at.constants as c


from prettyprinter import cpprint as pprint
from pypeerassets.at.protobuf_utils import serialize_card_extended_data
from pypeerassets.legacy import is_legacy_blockchain, legacy_import
from pypeerassets.networks import net_query
from pypeerassets.pautils import load_deck_p2th_into_local_node
from pypeerassets.exceptions import P2THImportFailed

import pacli.dt.utils as du
import pacli.dt.interface as di
import pacli.extended.utils as eu
import pacli.extended.queries as eq
import pacli.extended.handling as eh
from pacli.provider import provider
from pacli.config import Settings

# Address

def show_votes_by_address(deckid: str, address: str, debug: bool=False) -> None:
    # shows all valid voting transactions from a specific address, for all proposals.

    pprint("Votes cast from address: " + address)
    # vote_readable = { b'+' : 'Positive', b'-' : 'Negative' }
    vote_readable = { True : 'Positive', False : 'Negative' }
    deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

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


def show_donations_by_address(deckid: str, address: str=None, wallet: bool=False, mode: str=None, all_states: bool=False, incomplete: bool=False, unclaimed: bool=False, quiet: bool=False, debug: bool=False) -> None:
    # shows all valid donation transactions from a specific address, for all proposals.

    if wallet is True:
        addresses = eq.get_wallet_address_set(empty=True, include_named=True)
    elif address is not None:
        addresses = [address]
    else:
        addresses = None

    if not quiet:
        if wallet:
            pprint("Donations realized from all wallet addresses:")
        elif addresses is not None:
            pprint("Donations realized from address: " + address)
        else:
            pprint("Donations realized from all donors:")

    deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

    try:
        pst = dmu.get_parser_state(provider, deck, force_continue=True, force_dstates=True)

    except AttributeError:
        raise eh.PacliInputDataError("This seems not to be a proof-of-donation deck. No donation count possible.")
        return

    pstates = pst.proposal_states
    allowed_states = di.get_allowed_states(all_states, unclaimed, incomplete)

    if not pstates:
        print("No proposals recorded for this deck.")
        return

    for proposal in pstates:
        for rd, rdlist in enumerate(pstates[proposal].donation_states):
            for dstate in rdlist.values():
                if dstate.state not in allowed_states:
                    continue
                # print(dstate.__dict__)
                if ((addresses is None) or (dstate.donor_address in addresses)) and (dstate.donation_tx is not None):
                #if (dstate.donor_address == address) and (dstate.donation_tx is not None):
                    di.display_donation_state(dstate, mode=mode)

# Deck

def init_dt_deck(network_name: str, deckid: str, rescan: bool=True, quiet: bool=False, label: str=None, no_label: bool=False, debug: bool=False) -> None:
    # MODIFIED: added support for legacy blockchains
    deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
    legacy = is_legacy_blockchain(network_name)

    if not quiet:
        print("Importing dPoD deck:", deck.id)

    if "sdp_deckid" not in deck.__dict__.keys():
        if not quiet:
            print("No SDP (voting) token found for this deck. This is probably not a proof-of-donation deck!")
        return

    all_accounts = provider.listaccounts()
    if deck.id not in all_accounts:
        if not quiet:
            print("Importing main key from deck.")
        load_deck_p2th_into_local_node(provider, deck)
    else:
        if not quiet:
            print("Main key was already imported.")

    for tx_type in ("proposal", "signalling", "locking", "donation", "voting"):

        accountname=deck.id + tx_type.upper()
        if accountname in all_accounts:
            if not quiet:
                print("P2TH address for", tx_type, "was already imported.")
            continue

        p2th_addr = deck.derived_p2th_address(tx_type)
        if not quiet:
            print("Importing {} P2TH address: {}".format(tx_type, p2th_addr))
            print("Accountname for {}: {}".format(tx_type, accountname))
        if legacy:
            p2th_wif = deck.derived_p2th_wif(tx_type)
            try:
                legacy_import(provider, p2th_addr, p2th_wif, rescan, silent=quiet, accountname=accountname)
            except P2THImportFailed:
                raise eh.PacliInputDataError("P2TH import failed for address:", p2th_addr)
        else:
            dmu.import_p2th_address(provider, p2th_addr)

    # SDP
    # Note: there can be a None value for sdp_deckid even if this is a PoD token (e.g. in the case of a swap).
    if deck.sdp_deckid is not None:
        if deck.sdp_deckid not in all_accounts:

            p2th_sdp_addr = pa.Kutil(network=network_name,
                             privkey=bytearray.fromhex(deck.sdp_deckid)).address

            if not quiet:
                print("Importing SDP (voting) P2TH address: {}".format(p2th_sdp_addr))

            if legacy:
                p2th_sdp_wif = pa.Kutil(network=network_name,
                             privkey=bytearray.fromhex(deck.sdp_deckid)).wif
                legacy_import(provider, p2th_sdp_addr, p2th_sdp_wif, rescan, silent=quiet, accountname=deck.sdp_deckid)
            else:
                dmu.import_p2th_address(provider, p2th_sdp_addr)

        else:
            if not quiet:
                print("SDP (voting) P2TH address was already imported.")

    if rescan:
        if not legacy:
            provider.rescanblockchain()
            if not quiet:
                print("Rescanning ...")


    if not no_label:
        eu.store_deck_label(deck, label=label, alt=False, quiet=quiet, debug=debug)

    if not quiet:
        print("Done.")


def dt_state(deckid: str, debug: bool=False, debug_voting: bool=False, debug_donations: bool=False):
    # prints the ParserState (DTDeckState).

    deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
    pst_dict = dmu.get_parser_state(provider, deck, force_continue=True, force_dstates=True, debug=debug, debug_voting=debug_voting, debug_donations=debug_donations).__dict__
    di.prepare_dict(pst_dict, only_txids=["initial_cards", "sdp_cards", "donation_txes"], only_id=["sdp_deck", "deck"], only_ids = ["proposal_states", "approved_proposals", "valid_proposals"])
    pprint(pst_dict)

# Card
# Reward data seems to be missing in the "new" function ATM.

def claim_pod_tokens(proposal_id: str, donor_address: str=Settings.key.address, donation_state: str=None, payment: list=None, receiver: list=None, proposer: bool=False, force: bool=False, debug: bool=False, quiet: bool=False) -> tuple:

    # TODO: recheck the numbers of decimals problem (if donations have more decimals than token txes) here too!

    if not receiver: # if there is no receiver, the coins are directly allocated to the donor.
        receiver = [donor_address]

    # enable using labels for proposals
    proposal_id = eu.search_for_stored_tx_label("proposal", proposal_id, quiet=quiet)

    if not force:
        beneficiary = "proposer" if proposer else "donor {}".format(donor_address)
        if not quiet:
            print("Calculating reward for {} ...".format(beneficiary))

        reward_data = du.get_pod_reward_data(proposal_id, donor_address, donation_state=donation_state, proposer=proposer, debug=debug, quiet=quiet)
        deckid = reward_data.get("deckid")
        max_payment = reward_data.get("reward")
        donation_txid = reward_data.get("donation_txid")

    elif not deckid:
        raise eh.PacliInputDataError("No deckid provided, if you use --force you need to provide it.")

    elif payment is not None:
        max_payment = sum(payment)
        if not quiet:
            print("WARNING: Overriding reward calculation. If you calculated your payment incorrectly, the transaction will be invalid.")
    else:
        raise eh.PacliInputDataError("No payment data provided.")

    if payment is None:
        payment = [max_payment]
    else:
        if sum(payment) > max_payment:
            raise eh.PacliInputDataError("Amount of cards does not correspond to the spent coins. Use --force to override.")
        rest_amount = max_payment - sum(payment)
        if rest_amount > 0:
            receiver.append(donor_address)
            payment.append(rest_amount)

    asset_specific_data = serialize_card_extended_data(net_query(provider.network), id=c.ID_DT, txid=donation_txid)
    return asset_specific_data, receiver, payment, deckid


def list_current_proposals(deck: str, block: int=None, searchstring: str=None, only_active: bool=False, all_states: bool=False, simple: bool=False, debug: bool=False) -> None:
    # TODO re-check: it seems that if we use Decimal for values like req_amount scientific notation is used.
    # Using float instead seems to work well when it's only divided by the "Coin" value (1000000 in PPC)
    # TODO ensure that the simple mode also takes into account Proposal Modifications

    deckid = du.default_deck() if deck is None else eu.search_for_stored_tx_label("deck", deck)
    #else:
    #    try:
    #        deckid = eu.search_for_stored_tx_label("deck", deck)
    #    except (ValueError, TypeError):
    #        raise eh.PacliInputDataError("No deck provided.")

    statelist, advanced = ["active"], True
    if not only_active:
        statelist.append("completed")
    if all_states:
        statelist.append("abandoned")
    if simple:
        advanced = False

    if block is None:
        block = provider.getblockcount() + 1 # modified, next block is the reference, not last block
        pprint("Next block to be added to blockchain: " + str(block))

    pstate_periods = eh.run_command(du.get_proposal_state_periods, deckid, block, advanced=advanced, debug=debug)

    coin = dmu.coin_value(Settings.network)
    shown_pstates = False

    if len([p for l in pstate_periods.values() for p in l]) == 0:
        print("No proposals found for deck: " + deckid)
    else:
        print("Proposals in the following periods are available for this deck:")

    # for index, period in enumerate(pstate_periods):
    for period in pstate_periods:
        pstates = pstate_periods[period]
        first = True

        for pstate_data in pstates:

            pstate = pstate_data["state"]
            startblock = pstate_data["startblock"]
            endblock = pstate_data["endblock"]

            if searchstring is not None:
                if str(searchstring) not in pstate.idstring:
                    continue

            if pstate.state in statelist:
                if not shown_pstates:
                    shown_pstates = True
                if first: # MODIF, index is not needed.
                    print("\n")
                    pprint(di.printout_period(period, [startblock, endblock], show_blockheights=False))
                    first = False
                requested_amount = pstate.req_amount / coin
                # We can't add the state in simple mode, as it will always be "active" at the start.
                result = [
                          "Short ID & description: " + pstate.idstring,
                          "Requested amount: {}".format(requested_amount),
                          "Donation address: {}".format(pstate.donation_address),
                          "Complete ID: {}".format(pstate.id),
                          "Proposed delivery (block): {}".format(pstate.deck.epoch_length * pstate.end_epoch),
                          "Duration of the period: {} - {}".format(startblock, endblock)
                          ]

                if advanced:
                    donated_amount = str(sum(pstate.donated_amounts) / coin)
                    result.append("State: {}".format(pstate.state))
                    result.append("Donated amount: {}".format(donated_amount))
                    result.append("Donation transactions: {}".format(len([d for rd in pstate.donation_txes for d in rd])))
                print("\n*", "\n    ".join(result))


    if not shown_pstates:

        if all_states:
            pmsg = ""
        elif only_active:
            pmsg = "active "
        else:
            pmsg = "active and/or completed "
        print("No {}proposal states found for deck {}.".format(pmsg, deckid))

