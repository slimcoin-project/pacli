# this file bundles all dt-specific classes.
from prettyprinter import cpprint as pprint
from pacli.config import Settings
from pacli.provider import provider
import pypeerassets as pa
import pypeerassets.at.dt_misc_utils as dmu
import json
from pypeerassets.at.dt_entities import SignallingTransaction, LockingTransaction, DonationTransaction, VotingTransaction, TrackedTransaction, ProposalTransaction
import pacli.dt_utils as du
import pacli.dt_interface as di
import pacli.keystore_extended as ke

class Proposal: ### DT ###

    def get_votes(self, proposal_txid: str, debug: bool=False):
        '''Displays the result of both voting rounds.'''
        # TODO: ideally there may be a variable indicating the second round has not started yet.

        all_votes = dmu.get_votestate(provider, proposal_txid, debug)

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

    def current_period(self, proposal_txid: str, blockheight: int=None, show_blockheights: bool=True):
        '''Shows the current period of the proposal lifecycle.'''

        if blockheight is None:
            blockheight = provider.getblockcount() + 1
            pprint("Next block: {}".format(blockheight))
        period, blockheights = du.get_period(proposal_txid, blockheight)
        pprint(di.printout_period(period, blockheights, show_blockheights))

    def all_periods(self, proposal_txid: str):
        '''Shows all periods of the proposal lifecycle.'''

        periods = du.get_all_periods(proposal_txid)
        for period, blockheights in periods.items():
            print(di.printout_period(period, blockheights, blockheights_first=True))

    def list(self, deckid: str, block: int=None, only_active: bool=False, all: bool=False, debug: bool=False) -> None:
        '''Shows all proposals for a deck and the period they are currently in, optionally at a specific blockheight.'''
        # TODO re-check: it seems that if we use Decimal for values like req_amount scientific notation is used.
        # Using float instead seems to work well when it's only divided by the "Coin" value (1000000 in PPC)

        statelist, advanced = ["active"], True
        if not only_active:
            statelist.append("completed")
        if all:
            statelist.append("abandoned")
            advanced = False

        if block is None:
            block = provider.getblockcount() + 1 # modified, next block is the reference, not last block
            pprint("Next block to be added to blockchain: " + str(block))
        try:
            pstate_periods = du.get_proposal_state_periods(deckid, block, advanced=advanced, debug=debug)
        except KeyError:
            pprint("Error, unconfirmed proposals in mempool. Wait until they are confirmed.")
            return
        except ValueError as ve:
            if len(ve.args) > 0:
                pprint(ve.args[0])
            pprint("Deck in wrong format, proposals could not be retrieved.")
            return

        coin = dmu.coin_value(Settings.network)


        if len([p for l in pstate_periods.values() for p in l]) == 0:
            print("No proposals found for deck: " + deckid)
        else:
            print("Proposals in the following periods are available for this deck:")

        for period in pstate_periods:
            pstates = pstate_periods[period]
            first = True
            for pstate_data in pstates:

                pstate = pstate_data["state"]
                startblock = pstate_data["startblock"]
                endblock = pstate_data["endblock"]

                if pstate.state in statelist:
                    if first:
                        print("\n")
                        pprint(di.printout_period(period, [startblock, endblock], show_blockheights=False))
                        first = False
                    requested_amount = pstate.req_amount / coin
                    result = ["ID: " + pstate.id,
                              "Startblock of this period: {} Endblock: {}".format(startblock, endblock),
                              "Requested amount: {}".format(requested_amount),
                              "Donation address: {}".format(pstate.donation_address)]
                    if advanced:
                        donated_amount = str(sum(pstate.donated_amounts) / coin)
                        result.append("State: {}".format(pstate.state))
                        result.append("Donated amount: {}".format(donated_amount))
                        result.append("Donation transactions: {}".format(len([d for rd in pstate.donation_txes for d in rd])))
                    print("\n*", "\n    ".join(result))

    def info(self, proposal_txid):
        '''Get basic info of a proposal.'''
        info = du.get_proposal_info(proposal_txid)
        pprint(info)

    def state(self, proposal_txid, debug=False, simple=False, complete=False):
        '''Shows a single proposal state.'''
        pstate = dmu.get_proposal_state(provider, proposal_txid, debug=debug)
        pdict = pstate.__dict__
        if simple:
            pprint(pdict)
        elif complete:
            di.prepare_complete_dict(pdict)
            pprint(pdict)
        else:
            pprint("Proposal State " + proposal_txid + ":")
            # in the standard mode, some objects are shown in a simplified way.
            di.prepare_dict(pdict)
            pprint(pdict)

    def my_donation_states(self, proposal_id: str, address: str=Settings.key.address, all_addresses: bool=False, also_origin: bool=False, debug: bool=False):
        '''Shows the donation states involving a certain address (default: current active address).'''
        # TODO: --all_addresses is linux-only until show_stored_address is converted to new config scheme.
        if all_addresses:

            all_dstates = dmu.get_donation_states(provider, proposal_id, debug=debug)
            labels = ke.get_all_labels(Settings.network)
            my_addresses = [ke.show_stored_address(label, network_name=Settings.network, noprefix=True) for label in labels]
            # print(my_addresses)
            my_dstates = [d for d in all_dstates if d.donor_address in my_addresses]
            # print(my_dstates)

        elif also_origin:
            # Default behavior MODIFIED. Origin addresses are also taken into account by get_donation_states.
            my_dstates = dmu.get_donation_states(provider, proposal_id, address=address, debug=debug)
        else:
            dstates = dmu.get_donation_states(provider, proposal_id, debug=debug)
            my_dstates = [ d for d in dstates if d.donor_address == address ]
            my_addresses = [address]

        for pos, dstate in enumerate(my_dstates):
            pprint("Address: {}".format(dstate.donor_address))
            pprint("Label: {}".format(ke.show_label(dstate.donor_address)["label"]))
            pprint("Donation state ID: {}".format(dstate.id))

            #pprint(dstate.__dict__)
            ds_dict = dstate.__dict__
            for item in ds_dict:
                try:
                    value = ds_dict[item].txid
                except AttributeError:
                    value = ds_dict[item]
                print(item + ":", value)

    def all_donation_states(self, proposal_id: str, all: bool=False, only_incomplete: bool=False, short: bool=False, debug: bool=False):
        '''Shows currently active (default) or all (--all flag) donation states of this proposal.'''
        dstates = dmu.get_donation_states(provider, proposal_id, debug=debug)

        if only_incomplete:
           allowed_states = ["incomplete"]
        else:
           allowed_states = ["incomplete", "complete"]
           if all:
               allowed_states += ["abandoned"]


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

    def create(self, deckid: str, req_amount: str, periods: int, slot_allocation_duration: int, change_address: str=None, tx_fee: str="0.01", p2th_fee: str="0.01", input_txid: str=None, input_vout: int=None, input_address: str=Settings.key.address, first_ptx: str=None, sign: bool=False, send: bool=False, verify: bool=False):
        '''Creates a new proposal.'''

        params = { "id" : "DP" , "dck" : deckid, "eps" : int(periods), "sla" : int(slot_allocation_duration), "amt" : int(req_amount), "ptx" : first_ptx}

        basic_tx_data = du.get_basic_tx_data("proposal", deckid=deckid, input_address=Settings.key.address)

        rawtx = du.create_unsigned_trackedtx(params, basic_tx_data, change_address=change_address, raw_tx_fee=tx_fee, raw_p2th_fee=p2th_fee, network_name=Settings.network)

        return du.finalize_tx(rawtx, verify, sign, send, debug=debug)

    def vote(self, proposal_id: str, vote: str, p2th_fee: str="0.01", tx_fee: str="0.01", change_address: str=None, input_address: str=Settings.key.address, verify: bool=False, sign: bool=False, send: bool=False, check_phase: int=None, wait: bool=False, confirm: bool=True):
        '''Vote (with "yes" or "no") for a proposal'''

        if (check_phase is not None) or (wait == True):
            print("Checking blockheights ...")
            if not du.check_current_period(proposal_id, "voting", phase=check_phase, wait=wait):
                return

        if vote in ("+", "positive", "p", "1", "yes", "y", "true"):
            votechar = "+"
        elif vote in ("-", "negative", "n", "0", "no", "n", "false"):
            votechar = "-"
        else:
            print("ERROR: Incorrect vote. Vote with 'positive'/'yes' or 'negative'/'no'.")

        vote_readable = "Positive" if votechar == "+" else "Negative"
        # print("Vote:", vote_readable ,"\nProposal ID:", proposal_id)

        params = { "id" : "DV" , "prp" : proposal_id, "vot" : votechar }

        basic_tx_data = du.get_basic_tx_data("voting", proposal_id=proposal_id, input_address=input_address)
        rawtx = du.create_unsigned_trackedtx(params, basic_tx_data, change_address=change_address, raw_tx_fee=tx_fee, raw_p2th_fee=p2th_fee, network_name=Settings.network)

        console_output = du.finalize_tx(rawtx, verify, sign, send, debug=debug)

        if confirm and sign and send:
            print("Waiting for confirmation (this can take several minutes) ...", end='')
            confirmations = 0
            while confirmations == 0:
                tx = provider.getrawtransaction(rawtx.txid, 1)
                try:
                    confirmations = tx["confirmations"]
                    break
                except KeyError:
                    di.spinner(10)

            print("\nVote confirmed.")

        return console_output


    def voters(self, proposal_id: str, debug: bool=False, blockheight: int=None):
        '''Shows enabled voters and their balance at the start of the current epoch or at a defined blockheight.'''

        proposal_tx = dmu.proposal_from_tx(proposal_id, provider)

        parser_state = dmu.get_parser_state(provider, deck=proposal_tx.deck, debug_voting=debug, force_continue=True, lastblock=blockheight)

        if blockheight is None:
            epoch = parser_state.epoch
            blockheight = parser_state.deck.epoch_length * epoch
        else:
            epoch = blockheight // parser_state.deck.epoch_length

        parser_state = dmu.get_parser_state(provider, deck=proposal_tx.deck, debug_voting=debug, force_continue=True)
        pprint("Enabled voters and weights for proposal {}".format(proposal_id))

        pprint(parser_state.enabled_voters)
        # pprint(parser_state.__dict__)

        if blockheight is None:
            pprint("Note: The weight corresponds to the adjusted PoD and voting token balances at the start of the current epoch {} which started at block {}.".format(epoch, blockheight))
        else:
            pprint("Note: The weight corresponds to the adjusted PoD and voting token balances at the start of the epoch {} containing the selected blockheight {}.".format(epoch, blockheight))

        pprint("Weights are shown in minimum token units.")
        pprint("The tokens' numbers of decimals don't matter for this view.")


class Donation:

    def signal(self, proposal_txid: str, amount: str, dest_label: str=None, dest_address: str=None, change_address: str=None, tx_fee: str="0.01", p2th_fee: str="0.01", change_label: str=None, sign: bool=False, send: bool=False, verify: bool=False, check_round: int=None, wait: bool=False, input_address: str=Settings.key.address, debug: bool=False) -> None:
        '''Creates a compliant signalling transaction for a proposal.'''

        [dest_address, change_address] = du.show_addresses([dest_address, change_address], [dest_label, change_label], Settings.network)

        if (check_round is not None) or (wait == True):
            if not du.check_current_period(proposal_txid, "signalling", dist_round=check_round, wait=wait):
                return

            print("You are signalling {} coins.".format(amount))
            print("Your donation address: {}".format(dest_address))
            if dest_label is not None:
                print("Label: {}".format(dest_label))
            # WORKAROUND. This should be done with the "legacy" parameter and net_query.
            if Settings.network in ("slm", "tslm"):
                total_tx_fee = 0.03
            elif Settings.network in ("tppc"):
                total_tx_fee = 0.02
            elif Settings.network in ("ppc"):
                total_tx_fee = 0.002

            print("Take into account that releasing the donation requires {} coins for fees.".format(total_tx_fee))
            if (check_round is not None) and (check_round < 4):
                print("Additionally, locking the transaction requires {} coins, so total fees sum up to {}.".format(total_tx_fee, total_tx_fee * 2))

        params = { "id" : "DS" , "prp" : proposal_txid }
        basic_tx_data = du.get_basic_tx_data("signalling", proposal_id=proposal_txid, input_address=Settings.key.address)

        rawtx = du.create_unsigned_trackedtx(params, basic_tx_data, change_address=change_address, dest_address=dest_address, raw_tx_fee=tx_fee, raw_p2th_fee=p2th_fee, raw_amount=amount, debug=debug, network_name=Settings.network)

        return du.finalize_tx(rawtx, verify, sign, send, debug=debug)

    def lock(self, proposal_txid: str, amount: str=None, change_address: str=None, dest_address: str=Settings.key.address, tx_fee: str="0.01", p2th_fee: str="0.01", sign: bool=False, send: bool=False, verify: bool=False, check_round: int=None, wait: bool=False, new_inputs: bool=False, dist_round: int=None, manual_timelock: int=None, reserve: str=None, reserve_address: str=None, dest_label: str=None, reserve_label: str=None, change_label: str=None, force: bool=False, debug: bool=False) -> None:

        '''Creates a Locking Transaction to lock funds for a donation, by default to the origin address.'''
        # TODO: dest_address could be trashed completely as the convention is now to use always the donor address.
        [dest_address, reserve_address, change_address] = du.show_addresses([dest_address, reserve_address, change_address], [dest_label, reserve_label, change_label], Settings.network)

        dist_round = du.get_dist_round(proposal_txid)
        if (check_round is not None) or (wait == True):
            if not du.check_current_period(proposal_txid, "locking", dist_round=check_round, wait=wait):
                return

        cltv_timelock = int(manual_timelock) if manual_timelock else du.calculate_timelock(proposal_txid)
        print("Locking funds until block", cltv_timelock)

        if amount is not None:
            print("Not using slot, instead locking custom amount:", amount)
        if force: # modified: before, False was also assigned if amount is given.
            use_slot = False
        else:
            use_slot = True

        # timelock and dest_address are saved in the transaction, to be able to reconstruct redeem script
        params = { "id" : "DL", "prp" : proposal_txid, "lck" : cltv_timelock, "adr" : dest_address }
        basic_tx_data = du.get_basic_tx_data("locking", proposal_id=proposal_txid, input_address=Settings.key.address, new_inputs=new_inputs, use_slot=use_slot, dist_round=dist_round)

        rawtx = du.create_unsigned_trackedtx(params, basic_tx_data, dest_address=dest_address, change_address=change_address, raw_tx_fee=tx_fee, raw_p2th_fee=p2th_fee, raw_amount=amount, cltv_timelock=cltv_timelock, force=force, new_inputs=new_inputs, debug=debug, reserve=reserve, reserve_address=reserve_address, network_name=Settings.network)

        return du.finalize_tx(rawtx, verify, sign, send, debug=debug)


    def release(self, proposal_txid: str, amount: str=None, change_address: str=None, tx_fee: str="0.01", p2th_fee: str="0.01", input_address: str=Settings.key.address, check_round: int=None, check_release: bool=False, wait: bool=False, new_inputs: bool=False, origin_label: str=None, origin_key: str=None, force: bool=False, sign: bool=False, send: bool=False, verify: bool=False, debug: bool=False) -> None: ### ADDRESSTRACK ###
        '''Releases a donation.'''

        if (check_round is not None) or (wait == True):
            if not du.check_current_period(proposal_txid, "donation", dist_round=check_round, wait=wait, release=True):
                return

        # dist_round only gives a value if we're inside the block limits of a round.
        # in the donation release phase, this gives None.
        dist_round = du.get_dist_round(proposal_txid)

        use_slot = False if (amount is not None) else True

        params = { "id" : "DD" , "prp" : proposal_txid }

        basic_tx_data = du.get_basic_tx_data("donation", proposal_id=proposal_txid, input_address=Settings.key.address, new_inputs=new_inputs, use_slot=use_slot, use_locking_slot=True, dist_round=dist_round, debug=debug)

        rawtx = du.create_unsigned_trackedtx(params, basic_tx_data, change_address=change_address, raw_amount=amount, raw_tx_fee=tx_fee, raw_p2th_fee=p2th_fee, new_inputs=new_inputs, force=force, use_locking_slot=True, network_name=Settings.network, debug=debug)

        # TODO: in this configuration we can't use origin_label for P2SH. Look if it can be reorganized.
        if new_inputs:
            p2sh, prv, key, rscript = None, None, None, None
        else:
            p2sh = True
            key = Settings.key
            rscript = basic_tx_data.get("redeem_script")

        return du.finalize_tx(rawtx, verify, sign, send, key=key, label=origin_label, redeem_script=rscript, debug=debug)

    def check_tx(self, txid=None, txhex=None):
        '''Creates a TrackedTransaction object and shows its properties. Primarily for debugging.'''
        tx = du.create_trackedtx(txid=txid, txhex=txhex)
        pprint("Type: " + str(type(tx)))
        pprint(tx.__dict__)

    def check_all_tx(self, proposal_id: str, include_badtx: bool=False, light: bool=False):
        '''Lists all TrackedTransactions for a proposal, even invalid ones.
           include_badtx also detects wrongly formatted transactions, but only displays the txid.'''
        du.get_all_trackedtxes(proposal_id, include_badtx=include_badtx, light=light)

    def show_slot(self, proposal_id: str, dist_round: int=None, satoshi: bool=False):
        '''Simplified variant of my_donation_states, only shows slot.
           If an address participated in several rounds, the round can be given.'''

        sat_slot = du.get_slot(proposal_id, Settings.key.address, dist_round=dist_round)

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
            address = du.show_stored_key(label, Settings.network)
            address_label = "{} with label {}".format(address, label)
        else:
            # we don't use show_label here so it's also possible to use under Windows.
            address_label = address

        print("Qualification status for address {} for distribution round {} in proposal {}:".format(address_label, dist_round, proposal_id))

        slot_fill_threshold = 0.95
        if dist_round in (0, 3, 6, 7):
            return True

        dstates = dmu.get_donation_states(provider, proposal_id, debug=debug, address=address)
        for ds in dstates:

            if (dist_round == ds.dist_round + 1) and (ds.state == "incomplete"):
                if dist_round in (1, 2):
                    if ds.locking_tx.amount >= (ds.slot * slot_fill_threshold):
                        return True
                elif dist_round == 5:
                    if ds.donated_amount >= (ds.slot * slot_fill_threshold):
                        return True
            elif (dist_round == 4) and (ds.state == "incomplete"):
                if ds.donated_amount >= (ds.slot * slot_fill_threshold):
                    return True
        return False


