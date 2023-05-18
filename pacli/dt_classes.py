# this file bundles all dt-specific classes.
from prettyprinter import cpprint as pprint
from pacli.config import Settings
from pacli.provider import provider
from pacli.tui import print_deck_list
import pypeerassets as pa
import pypeerassets.at.dt_misc_utils as dmu
import pypeerassets.at.constants as c
import json
from decimal import Decimal
from pypeerassets.at.dt_entities import SignallingTransaction, LockingTransaction, DonationTransaction, VotingTransaction, TrackedTransaction, ProposalTransaction
import pacli.dt_utils as du
import pacli.extended_utils as eu
import pacli.dt_interface as di
import pacli.dt_commands as dc
import pacli.keystore_extended as ke
import pacli.extended_interface as ei
import pacli.dt_txtools as dtx


class PoDToken:

    @classmethod
    def deck_spawn(self, name: str, dp_length: int, dp_reward: int, min_vote: int=0, sdp_periods: int=None, sdp_deck: str=None, verify: bool=False, sign: bool=False, send: bool=False, locktime: int=0, number_of_decimals=2) -> None: ### ADDRESSTRACK ###
        '''Wrapper to facilitate addresstrack DT spawns without having to deal with asset_specific_data.'''

        asset_specific_data = ei.run_command(eu.create_deckspawn_data, c.ID_DT, dp_length, dp_reward, min_vote, sdp_periods, sdp_deck)

        return ei.run_command(eu.advanced_deck_spawn, name=name, number_of_decimals=number_of_decimals, issue_mode=0x01,
                  locktime=locktime, asset_specific_data=asset_specific_data, verify=verify, sign=sign, send=send)

    def claim(self, proposal_id: str, donor_address:str=None, payment: list=None, receiver: list=None, locktime: int=0, donation_vout: int=2, donation_txid: str=None, donation_state: str=None, proposer: bool=False, verify: bool=False, sign: bool=False, send: bool=False, force: bool=False, debug: bool=False) -> str:
        '''Issue Proof-of-donation tokens after a successful donation.'''

        if donor_address is None:
            donor_address = Settings.key.address
        else:
            print("You provided a custom address. You will only be able to do a dry run to check if a certain address can claim tokens, but you can't actually claim tokens.\n--sign and --send are disabled, and if you sign the transaction manually it will be invalid.")
            sign, send = False, False

        # try:
        asset_specific_data, receiver, payment, deckid = ei.run_command(dc.claim_pod_tokens, proposal_id, donor_address=donor_address, payment=payment, receiver=receiver, donation_vout=donation_vout, donation_txid=donation_txid, donation_state=donation_state, proposer=proposer, force=force, debug=debug)
        #except TypeError as e: # should be catched.
        #    print("Error:", e)
        #    return None

        return ei.run_command(eu.advanced_transfer, deckid=deckid, receiver=receiver, amount=payment, asset_specific_data=asset_specific_data, verify=verify, locktime=locktime, sign=sign, send=send)

    def init_deck(self, deckid: str):
        '''Initializes DT deck and imports all P2TH addresses into node.'''

        ei.run_command(dc.init_dt_deck, Settings.network, deckid)

    def deck_info(self, deckid: str, p2th: bool=False, param: str=None):
        '''Prints DT-specific deck info.'''

        deckinfo = ei.run_command(dc.get_deckinfo, deckid, p2th)
        if param:
            print(deckinfo.get(param))
        else:
            pprint(deckinfo)

    def deck_list(self):
        '''List all DT decks.'''

        dt_decklist = ei.run_command(dmu.list_decks_by_at_type, provider, c.ID_DT)
        ei.run_command(print_deck_list, dt_decklist)

    def deck_state(self, deckid: str, debug: bool=False):
        '''Prints the DT deck state.'''
        ei.run_command(dc.dt_state, deckid, debug)

    def my_votes(self, deckid: str, address: str=Settings.key.address):
        '''shows votes cast from this address, for all proposals of a deck.'''
        return ei.run_command(dc.show_votes_by_address, deckid, address)

    def my_donations(self, deckid: str, address: str=Settings.key.address):
        '''shows donation states involving this address, for all proposals of a deck.'''
        return ei.run_command(dc.show_donations_by_address, deckid, address)

class Proposal:

    def get_votes(self, proposal_id: str, debug: bool=False):
        '''Displays the result of both voting rounds.'''
        # TODO: ideally there may be a variable indicating the second round has not started yet.

        all_votes = dmu.get_votestate(provider, proposal_id, debug)

        for phase in (0, 1):
            try:
                votes = all_votes[phase]
            except IndexError:
                pprint("Votes of round {} not available.".format(str(phase + 1)))
                continue

            pprint("Voting round {}:".format(str(phase + 1)))
            pprint("Positive votes (weighted): {}".format(str(votes["positive"])))
            pprint("Negative votes (weighted): {}".format(str(votes["negative"])))
            approval_state = "approved" if votes["positive"] > votes["negative"] else "not approved"
            pprint("In this round, the proposal was {}.".format(approval_state))

    def current_period(self, proposal_id: str, blockheight: int=None, show_blockheights: bool=True, debug: bool=False) -> None:
        '''Shows the current period of the proposal lifecycle.'''

        if blockheight is None:
            blockheight = provider.getblockcount() + 1
            pprint("Next block: {}".format(blockheight))
        deck = ei.run_command(du.deck_from_ttx_txid, proposal_id, "proposal", provider, debug=debug)
        # proposal_tx = dmu.find_proposal(proposal_id, provider)
        period, blockheights = ei.run_command(du.get_period,proposal_id, deck, blockheight)
        pprint(di.printout_period(period, blockheights, show_blockheights))

    def all_periods(self, proposal_id: str, debug: bool=False) -> None:
        '''Shows all periods of the proposal lifecycle.'''

        deck = ei.run_command(du.deck_from_ttx_txid, proposal_id, "proposal", provider, debug=debug)
        # proposal_tx = dmu.find_proposal(proposal_id, provider)
        periods = ei.run_command(du.get_all_periods, proposal_id, deck)
        for period, blockheights in periods.items():
            print(di.printout_period(period, blockheights, blockheights_first=True))

    def get_period(self, proposal_id: str, period: str, mode: str="start"):
        """Shows the start or end block of a period. Use letter-number combination for the 'period' parameter ,e.g. 'b2'."""
        try:
            pletter = period[0].upper()
            pnumber = int(period[1:])
        except:
            ei.print_red("Error: Period entered in wrong format. You have to enter a letter-number combination, e.g. b10 or d50.")
        proposal_tx = dmu.find_proposal(proposal_id, provider)
        periods = ei.run_command(du.get_all_periods, proposal_id, proposal_tx.deck)
        period_heights = periods[(pletter, pnumber)]
        if mode == "start":
            return period_heights[0]
        elif mode == "end":
            return period_heights[1]
        else:
            return period_heights

    def list(self, deckid: str, block: int=None, only_active: bool=False, all: bool=False, simple: bool=False, debug: bool=False) -> None:
        '''Shows all proposals for a deck and the period they are currently in, optionally at a specific blockheight.'''
        # TODO re-check: it seems that if we use Decimal for values like req_amount scientific notation is used.
        # Using float instead seems to work well when it's only divided by the "Coin" value (1000000 in PPC)
        # TODO ensure that the simple mode also takes into account Proposal Modifications

        statelist, advanced = ["active"], True
        if not only_active:
            statelist.append("completed")
        if all:
            statelist.append("abandoned")
        if simple:
            advanced = False

        if block is None:
            block = provider.getblockcount() + 1 # modified, next block is the reference, not last block
            pprint("Next block to be added to blockchain: " + str(block))
        #try:
        pstate_periods = ei.run_command(du.get_proposal_state_periods, deckid, block, advanced=advanced, debug=debug)
        #except KeyError:
        #    ei.print_red("Error: unconfirmed proposals in mempool or deck not initialized correctly.")
        #    ei.print_red("Check if you have initialized the deck with dt_init. Or wait until all proposals are confirmed.")
            # TODO: we can't rely on this, if there are many proposals maybe always there are some unconfirmed.
        # return
        #except ValueError as ve: # TODO: this should now be catched by run_command
        #    if len(ve.args) > 0:
        #        pprint(ve.args[0])
        #    ei.print_red("Error: Deck in wrong format, proposals could not be retrieved.")
        #    return

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

            pmsg = "" if all else "active and/or completed "
            print("No {}proposal states found for deck {}.".format(pmsg, deckid))

    def info(self, proposal_id: str) -> None:
        '''Get basic info of a proposal.'''
        info = du.get_proposal_info(proposal_id)
        pprint(info)

    def find(self, searchstring: str, advanced: bool=False, shortid: bool=False) -> None:
        '''finds a proposal based on its description string or short id'''
        pstates = ei.run_command(du.find_proposal_state_by_string, searchstring, advanced=advanced, shortid=shortid)
        for pstate in pstates:
            # this should go into dt_interface
            pprint(pstate.idstring)
            pprint("Donation Address: {}".format(pstate.donation_address))
            pprint("ID: {}".format(pstate.id))
            if advanced:
                pprint("State: {}".format(pstate.state))

    def state(self, proposal_string: str, param: str=None, debug: bool=False, simple: bool=False, complete: bool=False, raw: bool=False, search: bool=False) -> None:
        '''Shows a single proposal state.'''
        if search:
            pstate = ei.run_command(du.find_proposal_state_by_string, proposal_string, advanced=True)[0]
        elif len(proposal_string) == 16:
            pstate = ei.run_command(du.find_proposal_state_by_string, proposal_string, shortid=True, advanced=True)[0]
        elif len(proposal_string) == 64:
            proposal_id = proposal_string
            pstate = dmu.get_proposal_state(provider, proposal_id, debug=debug)
        else:
            print("NOTE: Non-standard search, trying to find by ID start.\nBe aware that you may not get the state of the proposal you intended.\nBe sure to check the Proposal ID.")
            pstate = ei.run_command(du.find_proposal_state_by_string, proposal_string, shortid=True, advanced=True)[0]
        pdict = pstate.__dict__
        if param is not None:
            result = pdict.get(param)
            if raw:
                di.prepare_complete_collection(result)
                print(result)
            else:
                di.prepare_dict({"result" : result})
                pprint("Value of parameter {} for proposal {}:".format(param, proposal_id))
                pprint(result)
        elif raw:
            di.prepare_complete_collection(pdict)
            print(pdict)
        elif simple:
            pprint(pdict)
        elif complete:
            di.prepare_complete_collection(pdict)
            pprint(pdict)
        else:
            pprint("Proposal State - " + pstate.idstring)
            # in the standard mode, some objects are shown in a simplified way.
            di.prepare_dict(pdict)
            pprint(pdict)

    def available_slot_amount(self, proposal_id: str, dist_round: int=None, all: bool=False, debug: bool=False):
        '''Shows the available slot amount in a slot distribution round, or show all of them. Default is the current round, if the current blockheight is inside one.'''
        pstate = dmu.get_proposal_state(provider, proposal_id, debug=debug)
        if all:
            for rd, round_slot in enumerate(pstate.available_slot_amount):
                pprint("Round {}: {}".format(rd, str(dmu.sats_to_coins(Decimal(round_slot), Settings.network))))
            return

        elif dist_round is None:
            dist_round = ei.run_command(du.get_dist_round, proposal_id, pstate.deck)
            if dist_round is None:
                print("ERROR: Current block height isn't inside a distribution round. Please provide one, or use --all.")
                return

        pprint("Available slot amount for round {}:".format(dist_round))
        pprint(str(dmu.sats_to_coins(Decimal(pstate.available_slot_amount[dist_round]), Settings.network)))


    def my_donation_states(self, proposal_id: str, address: str=Settings.key.address, all_addresses: bool=False, all_matches: bool=False, all: bool=False, unclaimed: bool=False, only_incomplete: bool=False, extconf: bool=False, debug: bool=False):
        '''Shows the donation states involving a certain address (default: current active address).'''
        # TODO: --all_addresses is linux-only until show_stored_address is converted to new config scheme.

        if all_addresses:

            all_dstates = ei.run_command(dmu.get_donation_states, provider, proposal_id, debug=debug)
            labels = ei.run_command(ke.get_all_labels, Settings.network, extconf=extconf)
            my_addresses = [ke.show_stored_address(label, network_name=Settings.network, noprefix=True) for label in labels]
            # print(my_addresses)
            my_dstates = [d for d in all_dstates if d.donor_address in my_addresses]
            # print(my_dstates)

        elif all_matches:
            # Includes states where the current address is used as origin or intermediate address.
            my_dstates = dmu.get_donation_states(provider, proposal_id, address=address, debug=debug)
        else:
            # Default behavior: only shows the state where the address is used as donor address.
            my_dstates = dmu.get_donation_states(provider, proposal_id, donor_address=address, debug=debug)

        allowed_states = di.get_allowed_states(all, unclaimed, only_incomplete)

        for pos, dstate in enumerate(my_dstates):
            if dstate.state not in allowed_states:
                continue
            pprint("Address: {}".format(dstate.donor_address))
            try:
                # this will only work if the key corresponding to the address is in the user's keystore.
                # We catch the exception to allow using it for others' addresses (no security issues involved).
                pprint("Label: {}".format(ke.show_label(dstate.donor_address)["label"]))
            except:
                pass
            pprint("Donation state ID: {}".format(dstate.id))

            #pprint(dstate.__dict__)
            ds_dict = dstate.__dict__
            for item in ds_dict:
                try:
                    value = ds_dict[item].txid
                except AttributeError:
                    value = ds_dict[item]
                print(item + ":", value)

    def all_donation_states(self, proposal_id: str, all: bool=False, only_incomplete: bool=False, unclaimed: bool=False, short: bool=False, debug: bool=False):
        '''Shows currently active (default) or all (--all flag) donation states of this proposal.'''
        dstates = dmu.get_donation_states(provider, proposal_id, debug=debug)

        allowed_states = di.get_allowed_states(all, unclaimed, only_incomplete)

        for dstate in dstates:

            if dstate.state not in allowed_states:
                continue

            pprint("ID: {}".format(dstate.id))
            ds_dict = dstate.__dict__

            if short:
                pprint("Donor address: {}".format(dstate.donor_address))
                pprint("-" * 16)
            else:
                for item in ds_dict:
                    if issubclass(type(ds_dict[item]), TrackedTransaction):
                        value = ds_dict[item].txid
                    else:
                        value = ds_dict[item]

                    print("{}: {}".format(item, value))

    def create(self, deckid: str, req_amount: str, periods: int, description: str="", change_address: str=None, change_label: str=None, tx_fee: str="0.01", confirm: bool=True, sign: bool=False, send: bool=False, verify: bool=False, debug: bool=False, txhex: bool=False):
        '''Creates a new proposal.'''

        kwargs = locals()
        del kwargs["self"]
        return ei.run_command(dtx.create_trackedtransaction, "proposal", **kwargs)

        """addresses, labels = (None, None, change_address), (None, None, change_label)
        basic_tx_data = ei.run_command(du.get_basic_tx_data, "proposal", deckid=deckid, input_address=Settings.key.address, addresses=addresses, labels=labels, silent=txhex)

        params = { "id" : c.ID_PROPOSAL , "deckid" : deckid, "epoch_number" : int(periods), "req_amount" : Decimal(str(req_amount)), "description" : description }

        rawtx = ei.run_command(du.create_unsigned_trackedtx, params, basic_tx_data, change_address=change_address, raw_tx_fee=tx_fee, network_name=Settings.network, debug=debug)

        return ei.output_tx(eu.finalize_tx(rawtx, verify, sign, send, debug=debug, silent=txhex, confirm=confirm), txhex=txhex)"""

    def modify(self, proposal_id: str, req_amount: str, periods: int, round_length: int=0, change_address: str=None, change_label: str=None, tx_fee: str="0.01", confirm: bool=True, sign: bool=False, send: bool=False, verify: bool=False, debug: bool=False, txhex: bool=False):
        '''Modify a proposal without providing the deck id.'''

        kwargs = locals()
        del kwargs["self"]
        return ei.run_command(dtx.create_trackedtransaction, "proposal", **kwargs)

        """old_proposal_tx = dmu.find_proposal(proposal_id, provider)
        addresses, labels = (None, None, change_address), (None, None, change_label)

        basic_tx_data = ei.run_command(du.get_basic_tx_data, "proposal", deckid=old_proposal_tx.deck.id, input_address=Settings.key.address, addresses=addresses, labels=labels, silent=txhex)

        params = { "id" : c.ID_PROPOSAL , "deckid" : deckid, "epoch_number" : int(periods), "round_length" : int(round_length), "req_amount" : Decimal(str(req_amount)), "first_ptx_txid" : proposal_id }

        rawtx = ei.run_command(du.create_unsigned_trackedtx, params, basic_tx_data, change_address=change_address, raw_tx_fee=tx_fee, network_name=Settings.network, debug=debug)

        return ei.output_tx(eu.finalize_tx(rawtx, verify, sign, send, debug=debug, silent=txhex, confirm=confirm), txhex=txhex)"""


    def vote(self, proposal_id: str, vote: str, tx_fee: str="0.01", change_address: str=None, change_label: str=None, input_address: str=Settings.key.address, verify: bool=False, sign: bool=False, send: bool=False, wait: bool=False, confirm: bool=True, txhex: bool=False, security: int=1, debug: bool=False):
        '''Vote (with "yes" or "no") for a proposal'''

        kwargs = locals()
        del kwargs["self"]
        return ei.run_command(dtx.create_trackedtransaction, "voting", **kwargs)

        """
        # MODIF: check_phase was eliminated. The extremely long timeframes between phases don't make worth it (nobody would start a transaction with --wait >2 months earlier).

        addresses, labels = (None, None, change_address), (None, None, change_label)

        basic_tx_data = ei.run_command(du.get_basic_tx_data, "voting", proposal_id=proposal_id, addresses=addresses, labels=labels, input_address=input_address, wait=wait, security_level=security, silent=txhex)

        if vote in ("+", "positive", "p", "1", "yes", "y", "true"):
            votechar, vote_bool = "+", True # TODO: do we need "votechar"? Or is bool better? (leave it open for now)
        elif vote in ("-", "negative", "n", "0", "no", "n", "false"):
            votechar, vote_bool = "-", False
        else:
            print("ERROR: Incorrect vote. Vote with 'positive'/'yes' or 'negative'/'no'.")

        # vote_readable = "Positive" if votechar == "+" else "Negative"
        # print("Vote:", vote_readable ,"\nProposal ID:", proposal_id)

        params = { "id" : c.ID_VOTING , "proposal_id" : proposal_id, "vote" : vote_bool }


        rawtx = ei.run_command(du.create_unsigned_trackedtx, params, basic_tx_data, change_address=change_address, raw_tx_fee=tx_fee, network_name=Settings.network)

        return ei.output_tx(eu.finalize_tx(rawtx, verify, sign, send, debug=debug, silent=txhex, confirm=confirm), txhex=txhex)"""


    def voters(self, proposal_id: str, debug: bool=False, blockheight: int=None, outputformat=None):
        '''Shows enabled voters and their balance at the start of the current epoch or at a defined blockheight.'''

        proposal_tx = dmu.find_proposal(proposal_id, provider)

        parser_state = dmu.get_parser_state(provider, deck=proposal_tx.deck, debug_voting=debug, force_continue=True, lastblock=blockheight)

        if blockheight is None:
            epoch = parser_state.epoch
            blockheight = parser_state.deck.epoch_length * epoch
        else:
            epoch = blockheight // parser_state.deck.epoch_length

        parser_state = dmu.get_parser_state(provider, deck=proposal_tx.deck, debug_voting=debug, force_continue=True)
        if outputformat not in ("simpledict", "voterlist"):
            pprint("Enabled voters and weights for proposal {}".format(proposal_id))

            pprint(parser_state.enabled_voters)
            # pprint(parser_state.__dict__)

            if blockheight is None:
                pprint("Note: The weight corresponds to the adjusted PoD and voting token balances at the start of the current epoch {} which started at block {}.".format(epoch, blockheight))
            else:
                pprint("Note: The weight corresponds to the adjusted PoD and voting token balances at the start of the epoch {} containing the selected blockheight {}.".format(epoch, blockheight))

            pprint("Weights are shown in minimum token units.")
            pprint("The tokens' numbers of decimals don't matter for this view.")

        elif outputformat == "voterlist":
            print(", ".join(parser_state.enabled_voters.keys()))

        elif outputformat == "simpledict":
            print(parser_state.enabled_voters)


class Donation:


    def signal(self, proposal_id: str, amount: str, dest_label: str=None, dest_address: str=None, change_address: str=None, tx_fee: str="0.01", change_label: str=None, confirm: bool=True, sign: bool=False, send: bool=False, verify: bool=False, check_round: int=None, wait: bool=True, debug: bool=False, txhex: bool=False, security: int=1, force: bool=False) -> None:
        '''Creates a compliant signalling transaction for a proposal.'''

        kwargs = locals()
        del kwargs["self"]
        return ei.run_command(dtx.create_trackedtransaction, "signalling", **kwargs)
        # return ei.run_command(dtx.create_trackedtransaction, "signalling", proposal_id=proposal_id, amount=amount, dest_label=dest_label, dest_address=dest_address, change_address=change_address, change_label=change_label, tx_fee=tx_fee, confirm=confirm, sign=sign, send=send, verify=verify, check_round=check_round, wait=wait, debug=debug, txhex=txhex, security=security, force=force)

        """addresses, labels = [dest_address, None, change_address], [dest_label, None, change_label]

        params = { "id" : c.ID_SIGNALLING, "proposal_id" : proposal_id }
        basic_tx_data = ei.run_command(du.get_basic_tx_data, "signalling", proposal_id=proposal_id, input_address=Settings.key.address, addresses=addresses, labels=labels, check_round=check_round, wait=wait, security_level=security, silent=txhex)

        donor_address_used = du.donor_address_used(basic_tx_data["dest_address"], proposal_id)
        if not txhex:
            ei.run_command(di.signalling_info, amount, check_round, basic_tx_data, dest_label=dest_label, donor_address_used=donor_address_used, force=force)

        rawtx = ei.run_command(du.create_unsigned_trackedtx, params, basic_tx_data, raw_tx_fee=tx_fee, raw_amount=amount, debug=debug, network_name=Settings.network, silent=txhex)

        return ei.output_tx(eu.finalize_tx(rawtx, verify, sign, send, debug=debug, silent=txhex, confirm=confirm), txhex=txhex)"""


    def lock(self, proposal_id: str, amount: str=None, change_address: str=None, dest_address: str=Settings.key.address, tx_fee: str="0.01", confirm: bool=True, sign: bool=False, send: bool=False, verify: bool=False, check_round: int=None, wait: bool=False, new_inputs: bool=False, timelock: int=None, reserve: str=None, reserve_address: str=None, dest_label: str=None, reserve_label: str=None, change_label: str=None, force: bool=False, debug: bool=False, txhex: bool=False, security: int=1) -> None:

        kwargs = locals()
        del kwargs["self"]
        return ei.run_command(dtx.create_trackedtransaction, "locking", **kwargs)

        '''Creates a Locking Transaction to lock funds for a donation, by default to the origin address.'''

        """# TODO: dest_address could be trashed completely as the convention is now to use always the donor address.
        # but: maybe in the future address reusage may have to be completely discouraged
        # [dest_address, reserve_address, change_address] = ke.show_addresses([dest_address, reserve_address, change_address], [dest_label, reserve_label, change_label], Settings.network)
        addresses, labels = [dest_address, reserve_address, change_address], [dest_label, reserve_label, change_label]

        #dist_round = du.get_dist_round(proposal_id) # not needed for LockingTX, but re-check

        cltv_timelock = int(manual_timelock) if manual_timelock else du.calculate_timelock(proposal_id)
        if force: # modified: before, False was also assigned if amount is given.
            use_slot = False
        else:
            use_slot = True

        lockhash_type = 2 # TODO: P2PKH is hardcoded now, but should be done by a check on the submitted addr.
        params = { "id" : c.ID_LOCKING, "proposal_id" : proposal_id, "timelock" : cltv_timelock, "address" : dest_address, "lockhash_type" : lockhash_type }
        basic_tx_data = ei.run_command(du.get_basic_tx_data, "locking", proposal_id=proposal_id, input_address=Settings.key.address, new_inputs=new_inputs, use_slot=use_slot, addresses=addresses, labels=labels, check_round=check_round, wait=wait, security_level=security, silent=txhex)

        if not txhex:
            print("Locking funds until block", cltv_timelock)

            if amount is not None:
                print("Not using slot, instead locking custom amount:", amount)

        rawtx = ei.run_command(du.create_unsigned_trackedtx(params, basic_tx_data, raw_tx_fee=tx_fee, raw_amount=amount, cltv_timelock=cltv_timelock, force=force, new_inputs=new_inputs, debug=debug, reserve=reserve, network_name=Settings.network, silent=txhex))

        return ei.output_tx(eu.finalize_tx(rawtx, verify, sign, send, debug=debug, silent=txhex, confirm=confirm), txhex=txhex)"""


    def release(self, proposal_id: str, amount: str=None, change_address: str=None, change_label: str=None, reserve_address: str=None, reserve_label: str=None, tx_fee: str="0.01", check_round: int=None, wait: bool=False, new_inputs: bool=False, force: bool=False, confirm: bool=True, sign: bool=False, send: bool=False, verify: bool=False, debug: bool=False, txhex: bool=False, security: int=1) -> None: ### ADDRESSTRACK ###
        '''Releases a donation.'''

        kwargs = locals()
        del kwargs["self"]
        return ei.run_command(dtx.create_trackedtransaction, "donation", **kwargs)

        """use_slot = False if (amount is not None) else True

        params = { "id" : c.ID_DONATION , "proposal_id" : proposal_id }
        addresses, labels = (None, reserve_address, change_address), (None, reserve_label, change_label)

        basic_tx_data = ei.run_command(du.get_basic_tx_data, "donation", proposal_id=proposal_id, input_address=Settings.key.address, new_inputs=new_inputs, use_slot=use_slot, addresses=addresses, labels=labels, check_round=check_round, wait=wait, security_level=security, debug=debug, silent=txhex)

        rawtx = ei.run_command(du.create_unsigned_trackedtx, params, basic_tx_data, raw_amount=amount, raw_tx_fee=tx_fee, new_inputs=new_inputs, force=force, network_name=Settings.network, debug=debug, silent=txhex)

        # TODO: in this configuration we can't use origin_label for P2SH. Look if it can be reorganized.
        if new_inputs:
            p2sh, prv, key, rscript = None, None, None, None
        else:
            p2sh = True
            key = Settings.key
            rscript = basic_tx_data.get("redeem_script")

        return ei.output_tx(eu.finalize_tx(rawtx, verify, sign, send, key=key, label=origin_label, redeem_script=rscript, debug=debug, silent=txhex, confirm=confirm), txhex=txhex)"""

    def resume(self, donation_state: str, send=False):
        """This method allows to select the next step of the donation state with all standard values,
        i.e. selecting always the full slot and using the previous transactions' outputs.
        The command works in the correct period and the one directly before.
        """
        if send:
            print("You selected to send your next transaction once the round has arrived.")
        else:
            print("This is a dry run, your transaction will not be sent. Use --send to send it.")

        dstate = du.find_donation_state_by_string(donation_state)
        if dstate.state == "complete":
            print("Donation state is already complete.")
            return
        elif dstate.state == "abandoned":
            print("Donation state is abandoned. You missed a step in the process.")
            return
        # TODO we need a way to insert the deck here.
        period = du.get_period(dstate.proposal_id, deck)
        dist_round = du.get_dist_round(dstate.proposal_id, period=period)
        if dstate.dist_round == dist_round:
            if dist_round <= 3 and dstate.signalling_tx:
                # here the next step should be a LockingTransaction
                self.lock(dstate.proposal_id, wait=True, sign=True, send=send)
            elif dist_round >= 4 and dstate.signalling_tx:
                # next step is release.
                self.release(dstate.proposal_id, wait=True, sign=True, send=send)
        elif period in (("D", 1), ("D", 2)): # release period and period immediately before
            # (we don't need to check the locking tx because we checked the state already.)
            self.release(dstate.proposal_id, wait=True, sign=True, send=send)

    def check_tx(self, txid=None, txhex=None):
        '''Creates a TrackedTransaction object and shows its properties. Primarily for debugging.'''
        tx = ei.run_command(du.create_trackedtx, txid=txid, txhex=txhex)
        pprint("Type: " + str(type(tx)))
        pprint(tx.__dict__)

    def check_all_tx(self, proposal_id: str, include_badtx: bool=False, light: bool=False):
        '''Lists all TrackedTransactions for a proposal, even invalid ones.
           include_badtx also detects wrongly formatted transactions, but only displays the txid.'''
        ei.run_command(du.get_all_trackedtxes, proposal_id, include_badtx=include_badtx, light=light)

    def show_slot(self, proposal_id: str, dist_round: int=None, satoshi: bool=False):
        '''Simplified variant of my_donation_states, only shows slot.
           If an address participated in several rounds, the round can be given.'''

        sat_slot = ei.run_command(du.get_slot, proposal_id, Settings.key.address, dist_round=dist_round)

        if dist_round is None:
            print("Showing first slot where this address participated.")

        if not satoshi:
            slot = du.sats_to_coins(sat_slot, Settings.network)
        else:
            slot = sat_slot

        print("Slot:", slot)

    def qualified(self, proposal_id: str, dist_round: int, address: str=Settings.key.address, label: str=None, debug: bool=False):
        '''Shows if the address is entitled to participate in a slot distribution round.'''
        # Note: the donor address must be used as the origin address for the new signalling transaction.
        if label is not None:
            address = ke.show_stored_key(label, Settings.network)
            address_label = "{} with label {}".format(address, label)
        else:
            # we don't use show_label here so it's also possible to use under Windows.
            address_label = address

        print("Qualification status for address {} for distribution round {} in proposal {}:".format(address_label, dist_round, proposal_id))

        slot_fill_threshold = 0.95
        if dist_round in (0, 3, 6, 7):
            return True

        dstates = dmu.get_donation_states(provider, proposal_id, debug=debug, donor_address=address)
        for ds in dstates:
            min_qualifying_amount = ds.slot * slot_fill_threshold
            if debug: print("Donation state id:", ds.id)
            if debug: print("Slot:", ds.slot)
            if debug: print("Effective locking slot:", ds.effective_locking_slot)
            if debug: print("Effective slot:", ds.effective_slot)
            if debug: print("Minimal qualifying amount (based on slot):", min_qualifying_amount)
            try:
                if dist_round == ds.dist_round + 1:
                    if dist_round in (1, 2) and (ds.state == "incomplete"):
                        if ds.effective_locking_slot >= min_qualifying_amount:
                            return True
                    # rd 4 is also rd 3 + 1
                    elif dist_round in (4, 5) and (ds.state == "complete"):
                        if ds.effective_slot >= min_qualifying_amount:
                            return True
                elif (dist_round == 4) and (ds.state == "complete"):
                    if ds.effective_slot >= min_qualifying_amount:
                        return True
            except TypeError:
                return False
        return False

    def check_donor_address(proposal_id: str, donor_address: str=Settings.key.address, silent: bool=False):
        '''Shows if the donor address was already used for a Proposal.'''
        # note: a "False" here means that the check was not passed, i.e. the donor address should not be used.

        if donor_address_used(donor_address, proposal_id):
            result = "Already used in this proposal, use another address." if not silent else False
        else:
            result = "Not used in this proposal, you can freely use it." if not silent else True
        return result


    def create_trackedtransaction(self, *args, **kwargs):
        '''Generic tracked transaction creation.'''

        return ei.run_command(dtx.create_trackedtransaction, *args, **kwargs)


