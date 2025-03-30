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
import pacli.extended_commands as ec
import pacli.config_extended as ce
import pacli.extended_interface as ei
import pacli.dt_txtools as dtx
from pacli.extended_constants import DEFAULT_POD_DECK


class PoDToken():

    """General commands to manage dPoD (decentralized proof-of-donation) tokens."""

    @classmethod
    def spawn(self,
                   name: str,
                   epoch_length: int,
                   reward: int,
                   min_vote: int=0,
                   periods_sdp: int=None,
                   token_sdp: str=None,
                   number_of_decimals=2,
                   change: str=Settings.change,
                   wait_for_confirmation: bool=False,
                   ignore_warnings: bool=False,
                   verify: bool=False,
                   sign: bool=True,
                   send: bool=True,
                   locktime: int=0,
                   debug: bool=False) -> None:
        """Spawns a new DT deck.

        Usage:

            pacli podtoken spawn NAME EPOCHLENGTH REWARD

        Args:

          min_vote: Voting threshold (percentage) to approve a proposal (default: 0).
          periods_sdp: Number of Special Distribution Periods.
          token_sdp: Deck for the Special Distribution Periods (can be ID or label)
          number_of_decimals: Number of decimals of the token (default: 2).
          tx_fee: Specify a transaction fee.
          change: Specify a change address.
          ignore_warnings: Ignore all warnings and create transaction anyway (be careful!).
          sign: Sign the transaction (False by default).
          send: Send the transaction (False by default).
          locktime: Lock the transaction until a block or a time (not recommended, buggy in SLM).
          wait_for_confirmation: Wait and display a message until the transaction is confirmed.
          verify: Verify transaction with Cointoolkit (Peercoin only).
          debug: Show additional debug information."""

        asset_specific_data = ei.run_command(eu.create_deckspawn_data, c.ID_DT, epoch_length, reward, min_vote, periods_sdp, token_sdp, debug=debug)
        change_address = ec.process_address(change, debug=debug)

        return ei.run_command(eu.advanced_deck_spawn, name=name, number_of_decimals=number_of_decimals, issue_mode=0x01,
                             change_address=change_address, locktime=locktime, asset_specific_data=asset_specific_data, force=ignore_warnings,
                             confirm=wait_for_confirmation, verify=verify, sign=sign, send=send, debug=debug)


    def state(self, idstr: str=None, debug: str=None) -> None:
        """Prints the DT deck state (the current state of the deck variables).

        Usage:

            pacli podtoken state [DECK]

        If no DECK is given, the default dPoD token is used.

        Args:

          debug: Shows debug information.

        """
        deckid = du.default_deck() if idstr is None else ei.run_command(eu.search_for_stored_tx_label, "deck", idstr, debug=debug)
        if debug is not None:
            debug_standard = True if debug == True else False
            debug_donations = True if "donations" in debug else False
            debug_voting = True if "voting" in debug else False
        else:
            debug_standard, debug_donations, debug_voting = None, None, None

        ei.run_command(dc.dt_state, deckid, debug=debug_standard, debug_donations=debug_donations, debug_voting=debug_voting)


    def claim(self,
              proposal: str,
              receivers: list=None,
              amounts: list=None,
              change: str=Settings.change,
              locktime: int=0,
              state: str=None,
              examine_address:str=None,
              proposer: bool=False,
              verify: bool=False,
              sign: bool=True,
              send: bool=True,
              force: bool=False,
              quiet: bool=False,
              txhex: bool=False,
              wait_for_confirmation: bool=False,
              debug: bool=False) -> str:
        """Issue Proof-of-donation tokens as a reward after a successful donation.

        Usage modes:

            pacli podtoken claim PROPOSAL

        Claim the tokens and store them on the current main address, which has to be the donor.
        PROPOSAL is the proposal that was donated to.
        Note: as there can be only one donation per proposal and donor address, there is no possible ambiguity.

            pacli podtoken claim DECK TXID -r [ADDR1, ADDR2, ...] -a [AM1, AM2, ...]

        Claim the tokens and make a payment with the issued tokens to multiple receivers (put the lists into brackets)

        Args:

          proposer: Claim the proposer reward.
          state: Allows to specify a donation state (TXID of signalling transaction) if there are any ambiguities, for example if an incomplete donation was made from the same address.
          examine_address: Allows to specify a different donor address to check if a claim from there is possible (--sign and --send are disabled).
          locktime: Lock the transaction until a block or a time (not recommended, buggy in SLM).
          change: Specify a change address.
          receivers: List of receivers of the transaction (see above).
          amounts: List of amounts sent to the receivers (see above).
          sign: Sign the transaction (True by default).
          send: Send the transaction (True by default).
          wait_for_confirmation: Wait and display a message until the transaction is confirmed.
          verify: Verify transaction with Cointoolkit (Peercoin only).
          quiet: Suppress output.
          txhex: Print out the transaction as a HEX string.
          debug: Show additional debug information.
          force: Create the transaction even if the reward does not match the transaction or other warnings like the reorg check are displayed (be careful!).
        """
        # TODO add payto/payamount like in attoken/pobtoken claim

        change_address = ei.run_command(ec.process_address, change)
        proposal_id = eu.search_for_stored_tx_label("proposal", proposal)

        if examine_address is None:
            donor_address = Settings.key.address
        else:
            donor_address = examine_address
            print("You provided a custom address. You will only be able to do a dry run to examine if this address can claim tokens, but you can't actually claim tokens.\n--sign and --send are disabled, and if you sign the transaction manually it will be invalid.")
            sign, send = False, False

        if txhex is True:
            quiet = True

        asset_specific_data, receiver, payment, deckid = ei.run_command(dc.claim_pod_tokens, proposal_id, donor_address=donor_address, payment=amounts, receiver=receivers, donation_state=state, proposer=proposer, force=force, debug=debug, quiet=quiet)

        tx = ei.run_command(eu.advanced_card_transfer, deckid=deckid, receiver=receivers, amount=amounts, asset_specific_data=asset_specific_data, change_address=change_address, verify=verify, locktime=locktime, force=force, confirm=wait_for_confirmation, quiet=quiet, sign=sign, send=send)
        return ei.output_tx(tx, txhex=txhex)


    def votes(self,
              idstr: str=None,
              address: str=None,
              debug: bool=False):

        """Shows votes cast by an address for a token (deck).
        If no token is specified, the default dPoD token is used.

        Usage modes:

            pacli podtoken votes [TOKEN]

        Shows all votes cast from the current address for the specified token TOKEN.

            pacli podtoken votes -a ADDRESS
            pacli podtoken votes TOKEN [-a] ADDRESS

        Shows all votes cast from the address ADDRESS for the specified token TOKEN.
        The flag name -a has to be given if no token is provided.

        Args:

          address: Show votes from the specified address. Can be used as a positional argument if a token is given.
          my: Show votes of the current main address.
          debug: Prints debug information.
          token: Token (deck) ID or global or local label/name. To be used as a positional argument (flag name not necessary).

        """

        deckid = du.default_deck() if idstr is None else ei.run_command(eu.search_for_stored_tx_label, "deck", idstr, debug=debug)
        if address is None:
            address = Settings.key.address
        else:
            address = ec.process_address(address)
        return ei.run_command(dc.show_votes_by_address, deckid, address, debug=debug)


    def electorate(self,
               idstr: str=None,
               state_at_block: int=None,
               phase: str=None,
               epoch: int=None,
               miniid: bool=False,
               listvoters: bool=False,
               next_state: int=None,
               quiet: bool=False,
               debug: bool=False) -> None:
        """Shows the potential 'electorate' of enabled voters (the list of addresses with a positive balance of voting-enabling tokens) to vote for a dPoD token, and their voting weight at the start of the current epoch, for a proposal's voting round, or the epoch corresponding to a defined blockheight.

        Usage modes:

            pacli podtoken electorate [TOKEN]

        Shows the electorate at the start of the current epoch.
        If TOKEN is not given, the default proof-of-donation token is used.
        TOKEN can be a token (deck) ID, a local label or the global name.

            pacli podtoken electorate [TOKEN] -s BLOCKHEIGHT

        Takes a block height BLOCKHEIGHT and calculates the state at the start of the epoch the block belongs to.
        This shows how the electorate would look if a proposal was voted at this block.

            pacli podtoken electorate [TOKEN] -e EPOCH

        Shows the voting weight at the start of the epoch EPOCH.

            pacli podtoken electorate [TOKEN] -n [BLOCKHEIGHT]

        Show potential balance of the next epoch after the current or selected block, taking into account token transfers.
        If BlOCKHEIGHT is given, then the state is calculated for the epoch start following the given block height.
        If no block height is given, the potential state taking into account the transactions of voting and dPoD tokens at the current block is calculated. This state however can change until the end of the epoch.

            pacli podtoken electorate PROPOSAL -p [PHASE]

        Shows list of enabled addresses to vote for proposal PROPOSAL in a voting phase (1 or 2).
        If PHASE is not given, the first phase is used.
        PROPOSAL can be an ID, a local label, a part of the description or the mini ID (with -m option).

        Args:

          quiet: Suppress additional output and print out a script-friendly dictionary.
          listvoters: Print out only a list of voters.
          state_at_block: See Usage modes (not in combination with -p, -n and -e).
          epoch: Calculate the state at the start of a specific epoch (not in combination with -p, -s or -n).
          phase: Show voters for a voting phase of a proposal. See Usage modes.
          miniid: Use the mini id (short id) to identify the proposal.
          next_state: See Usage modes (not in combination with -p, -s or -e).
          debug: Show additional debug information."""

        return ei.run_command(self.__electorate, idstr=idstr, phase=phase, blockheight=state_at_block, next=next_state, miniid=miniid, epoch=epoch, listvoters=listvoters, quiet=quiet, debug=debug)

    def __electorate(self,
               idstr: str=None,
               phase: str=None,
               blockheight: int=None,
               epoch: int=None,
               miniid: bool=False,
               listvoters: bool=False,
               next: bool=False,
               quiet: bool=False,
               debug: bool=False) -> None:

        if type(next) == int:
            blockheight = next
        if type(blockheight) == bool or type(epoch) == bool:
           raise ei.PacliInputDataError("If using -e or -s options you have to provide an epoch (for -e) or block height (for -s).")

        current_block = provider.getblockcount()

        if phase is None:
            deckid = eu.search_for_stored_tx_label("deck", idstr, debug=debug) if idstr is not None else DEFAULT_POD_DECK[Settings.network]
            deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

            if "epoch_length" not in deck.__dict__:
                raise ei.PacliInputDataError("Not a Proof of Donation token (deck).")
            if epoch is None:
                if blockheight is None:
                    blockheight = current_block
                epoch = blockheight // deck.epoch_length
            if next:
                epoch += 1

        else:
            phase = 1 if phase == True else phase
            pp_data = Proposal()._get(idstr, require_states=True, miniid=miniid, label_priority=True, debug=debug)
            proposal_id = pp_data["id"]
            proposal = pp_data["states"][0]
            deck = proposal.deck
            epoch = proposal.end_epoch if phase == 2 else proposal.start_epoch

        epoch_start = deck.epoch_length * epoch # first block of the epoch
        if blockheight is None:
            blockheight = epoch_start

        if blockheight > current_block:
            if phase is not None:
                msg_futureblock = "Impossible to show the electorate for this voting round as the epoch begins in the future."
            else:
                msg_futureblock = "You can't select a future epoch or block height."
            raise ei.PacliInputDataError(msg_futureblock)

        # last_epoch_start is the start of the last epoch which will be completely processed.
        last_epoch_start = max(0, (epoch - 1) * deck.epoch_length)

        parser_state = dmu.get_parser_state(provider, deck=deck, debug_voting=debug, force_continue=True, lastblock=last_epoch_start)

        if listvoters is True:
            print(", ".join(parser_state.enabled_voters.keys()))
        elif quiet is True:
            print(parser_state.enabled_voters)
        else:
            if phase is not None:
               pprint("Enabled voters and weights for proposal {}, for voting phase {}".format(proposal_id, phase))
            else:
               pprint("Enabled voters and weights for token (deck) {}".format(deckid))
            print("\n")

            voters = parser_state.enabled_voters

            if not voters:
                print("No potential voters found in this epoch.")

            for voter, vbalance in voters.items():
                print("{}: {}".format(voter, float(vbalance)))

            if next is not None:
                print("\nNote: The weight depends on the adjusted dPoD and voting token balances at the start of the epoch {} which starts at block {}.".format(epoch, epoch_start))
                if blockheight == current_block:
                    print("Note that there may be token transfers after the current block which will change the outcome.")
            elif blockheight in (current_block, epoch_start):
                print("\nNote: The weight depends on the adjusted dPoD and voting token balances at the start of the epoch {} which started at block {}.".format(epoch, epoch_start))
            else:
                print("\nNote: The weight depends on the adjusted dPoD and voting token balances at the start of the epoch {} containing the selected blockheight {}.".format(epoch, blockheight))

            print("Weights are shown in minimum token units.")


    def check_tx(self, proposal: str=None, txid: str=None, fulltx: str=None, include_badtx: bool=False, light: bool=False) -> None:
        """Shows properties of TrackedTransactions. Primarily for debugging.

        Usage modes:

            pacli donation check_tx PROPOSAL

        Lists all TrackedTransactions for a proposal, even invalid ones.

            pacli donation check_tx [-t TXID|-f TXHEX]

        Displays all attributes of a TrackedTransaction, given a TXID or the transaction in hex format (TXHEX).

        Args:

          include_badtx: also detects wrongly formatted transactions, but only displays the txid (not in combination with -t or -f).
          light: Faster mode, not displaying properties depending from deck state.
          fulltx: Transaction in hex code. See Usage modes.
          txid: Transaction ID. See Usage modes.
          proposal: Proposal ID or label. See Usage modes. To be used as a positional argument (flag name not mandatory).
        """
        # TODO: catch error when OP_RETURN is not found (pypeerassets.exceptions.InvalidNulldataOutput)

        if proposal is not None:

            # ex check_all_tx

            proposal_id = eu.search_for_stored_tx_label("proposal", proposal)
            return ei.run_command(du.get_all_trackedtxes, proposal_id, include_badtx=include_badtx, light=light)

        tx = ei.run_command(du.get_trackedtx, txid=txid, txhex=fulltx)
        pprint("Type: " + str(type(tx)))
        pprint(tx.__dict__)


class Proposal:

    """Commands to manage, show and vote for proposals in dPoD tokens."""


    def _get(self, searchstring: str, miniid: bool=False, advanced: bool=False, require_states: bool=False, label_priority: bool=False, debug: bool=False) -> dict:

        proposal_id = None
        if (miniid is False and label_priority is True) or (require_states is False):
            try:
                proposal_id = eu.search_for_stored_tx_label("proposal", str(searchstring))
                proposal_states = None
            except ei.PacliInputDataError:
                require_states = True

        if require_states is True or miniid is True:
            if proposal_id is not None:
                proposal_state = dmu.get_proposal_state(provider, proposal_id, debug=debug)
                proposal_states = [proposal_state]
            else:
                proposal_states = du.find_proposal_state_by_string(str(searchstring), advanced=advanced, shortid=miniid)
            if len(proposal_states) > 1 and debug:
                print("Note: There are more than one proposal states matching the string. Displaying the first one.")
            try:
                proposal_id = proposal_states[0].id
            except IndexError:
                raise ei.PacliInputDataError("Proposal not found.")

        return {"id" : proposal_id, "states" : proposal_states}



    def set(self,
            label: str,
            proposal_id: str,
            modify: bool=False,
            quiet: bool=False) -> None:
        """Stores a proposal with label and proposal id (TXID). Use --modify to change the label.

        Usage modes:

            pacli proposal set LABEL PROPOSAL_ID

        Stores a new proposal.

            pacli proposal set NEW_LABEL OLD_LABEL -m

        Modifies the label of an already stored proposal.

        Args:

          modify: Replace the label by another one (see Usage modes).
          quiet: Suppress output (script-friendly).
        """
        return ce.setcfg("proposal", label, value=proposal_id, quiet=quiet, modify=modify)

    def show(self,
             label_or_id: str,
             param: str=None,
             state: bool=False,
             info: bool=False,
             find: bool=False,
             advanced: bool=False,
             basic: bool=False,
             quiet: bool=False,
             miniid: bool=False,
             debug: bool=False) -> str:
        """Shows information about a proposal.

        Usage modes:

            pacli proposal show LABEL

        Shows a proposal ID stored with a label LABEL.

            pacli proposal show LABEL_OR_ID -i

        Shows basic information about a proposal.
        Proposal can be given as an ID, a local label, the description or a part of it, or the mini ID (with -m option).
        If -a is given, show advanced information (all parameters of the proposal transaction).

            pacli proposal show LABEL_OR_ID -s [-p PARAM]

        Shows a dictionary with the current state of a proposal.
        In the standard mode, some of the elements are simplified.
        If -a is given, show the complete elements of the proposal state (long output).
        If -p is given, display only a specific parameter of the dictionary.
        Proposal can be given as an ID, a local label, the description or a part of it, or the mini ID (with -m option).
        If -f is given in addition to -s, local labels will be ignored and instead the string will be searched if possible.

            pacli proposal show STRING -f

        Find all proposals containing STRING in their ID or description.
        Proposal can be given as an ID, a local label, the description or a part of it, or the mini ID (with -m option).
        If -a is given, show information about activity state (slower).

        Args:

            advanced: Show advanced information about a proposal or its state. Exact additions depend on the flag combination (only with -f, -s and -i).
            basic: Show a simplified version of the proposal state (only in combination with -s).
            find: Search for a proposal containing a string (see Usage modes).
            info: Show basic info about a proposal.
            miniid: Use the mini id (short id) to identify the proposal.
            param: Only in combination with -s: show a value of the proposal state dictionary (the output of proposal show -s).
            quiet: Suppress addiitonal output, print information in raw format (script-friendly).
            state: Show the state of the proposal with all variables (see Usage modes).
            debug: Provide additional debug information.

        """

        pp_data = ei.run_command(self._get, label_or_id, require_states=(state or find), miniid=miniid, label_priority=(not find), advanced=advanced, debug=debug)

        if info is True:
            return self.__info(pp_data["id"], advanced=advanced)
        elif state is True:
            return self.__state(pp_data["states"][0], param=param, complete=advanced, simple=basic, quiet=quiet, search=find, debug=debug)
        elif find is True:
            return self.__find(pp_data["states"], advanced=advanced, shortid=miniid)

        return ce.show("proposal", label_or_id, quiet=quiet)

    def __info(self, proposal_id: str, advanced: bool=False) -> None:
        """Get basic info of a proposal."""

        proposal_tx = du.find_proposal(proposal_id, provider)
        if advanced:
            pprint(proposal_tx.__dict__)
        else:
            pprint({"Proposal ID" : proposal_id,
                    "Description" : proposal_tx.description,
                    "Donation address" : proposal_tx.donation_address,
                    "Block height" : proposal_tx.blockheight,
                    "Token/Deck ID" : proposal_tx.deck.id})


    def __find(self, pstates: str, advanced: bool=False, shortid: bool=False) -> None:
        """finds a proposal based on its description string or short id"""

        for pstate in pstates:
            # this should go into dt_interface
            pprint(pstate.idstring)
            pprint("Donation Address: {}".format(pstate.donation_address))
            pprint("ID: {}".format(pstate.id))
            pprint("Token/Deck ID: {}".format(pstate.deck.id))
            if advanced:
                pprint("State: {}".format(pstate.state))

    def __state(self, pstate: str, param: str=None, simple: bool=False, complete: bool=False, quiet: bool=False, search: bool=False, debug: bool=False, ) -> None:
        """Shows a single proposal state. You can search also for a short id (length 16 characters) or parts of the description."""

        pdict = pstate.__dict__
        if param is not None:
            result = pdict.get(param)
            if quiet:
                di.prepare_complete_collection(result)
                print(result)
            else:
                di.prepare_dict({"result" : result})
                pprint("Value of parameter {} for proposal {}:".format(param, pstate.id))
                pprint(result)
        elif quiet is True:
            di.prepare_complete_collection(pdict)
            print(pdict)
        elif simple is True:
            pprint(pdict)
        elif complete is True:
            di.prepare_complete_collection(pdict)
            pprint(pdict)
        else:
            pprint("Proposal State - " + pstate.idstring)
            # in the standard mode, some objects are shown in a simplified way.
            di.prepare_dict(pdict)
            pprint(pdict)

    def list(self,
             id_or_label: str=None,
             blockheight: int=False,
             find: str=None,
             only_active: bool=False,
             all_proposals: bool=False,
             simple: bool=False,
             quiet: bool=False,
             named: bool=False,
             debug: bool=False) -> None:
        """Shows a list of proposals.

        In all modes without -n, if DECK is not given the standard dPoD token is used.

        Usage modes:

           pacli proposal list [DECK] [-o|-a]

        Shows proposals of DECK. By default, shows active and completed proposals.
        DECK can be a deck ID or a label.

           pacli proposal list [DECK] -f STRING

        Shows proposals of DECK matching a string STRING in its ID string / description.

           pacli proposal list -n

        Shows proposals a label was assigned to.

        Args:

          only_active: shows only currently active proposals (not in combination with -n).
          all_proposals: in addition to active and completed, shows also abandoned proposals.
          find: Search by string in the list (not in combination with -n).
          simple: Like --all, but doesn't show proposals' state (much faster).
          named: Only shows proposals with labels/names assigned to them.
          blockheight: Block height to consider for the proposals' state (debugging option)
          quiet: If used with --named, suppress additional output and printout list in a script-friendly way.
          debug: Show debugging information.
          id_or_label: To be used as a positional argument (flag name not mandatory). See Usage modes.
        """

        if named:
            return ce.list("proposal", quiet=quiet)
        else:
            return ei.run_command(dc.list_current_proposals, deck=id_or_label, block=blockheight, searchstring=find, only_active=only_active, all_states=all_proposals, simple=simple, debug=debug)


    def approval(self, proposal: str, voters: bool=False, quiet: bool=False, debug: bool=False) -> None:
        """Show the approval state of a proposal (all votes cast by all enabled voters).

        Usage:
             pacli proposal approval PROPOSAL

        Shows all votes from all users on the proposal PROPOSAL.

        Args:

            debug: Show additional debug information.
            voters: Show voters and their transactions and weights.
            quiet: Suppress additional information (script-friendly)"""

        proposal_id = ei.run_command(eu.search_for_stored_tx_label, "proposal", proposal, quiet=quiet, debug=debug)

        if voters is True:
            return ei.run_command(self.__all_votes, proposal_id, quiet=quiet, debug=debug)
        else:
            return ei.run_command(self.__votestate, proposal_id, quiet=quiet, debug=debug)


    def __votestate(self, proposal_id: str, quiet: bool=False, debug: bool=False) -> None:
        """Displays the result of both voting rounds."""
        # TODO: ideally there may be a variable indicating the second round has not started yet.


        all_votes = dmu.get_votestate(provider, proposal_id, debug)
        votestate = []
        for phase in (0, 1):
            try:
                votes = all_votes[phase]
            except IndexError:
                if not quiet:
                    pprint("Votes of round {} not available.".format(str(phase + 1)))
                continue

            # approval_state = "approved" if votes["positive"] > votes["negative"] else "not approved"
            if votes["positive"] > votes["negative"]:
                approval_state = "approved"
            else:
                approval_state = "not approved"

            if quiet is True:
                votestate.append({"round" : phase, "state" : approval_state, "votes" : votes})
            else:
                pprint("Voting round {}:".format(str(phase + 1)))
                pprint("Positive votes (weighted): {}".format(str(votes["positive"])))
                pprint("Negative votes (weighted): {}".format(str(votes["negative"])))
                pprint("In this round, the proposal was {}.".format(approval_state))

        if quiet:
            print(votestate)


    def __all_votes(self, proposal_id: str, quiet: bool=False, debug: bool=False):

        proposal_state = dmu.get_proposal_state(provider, proposal_id, debug=debug)
        vtxes = proposal_state.voting_txes
        votestate = []

        for phase in (0, 1):
            for vtx in vtxes[phase]:
                if quiet:
                    vote = vtx.vote
                    weight = vtx.vote_weight
                else:
                    vote = "positive" if vtx.vote is True else "negative"
                    weight = str(vtx.vote_weight)
                vdict = {"txid" : vtx.txid,
                        "sender" : vtx.sender,
                        "vote" : vote,
                        "weight" : weight,
                        "blockheight" : vtx.blockheight}
                votestate.append(vdict)
        if quiet:
            print(votestate)
        else:
            pprint("Initial voting round transactions:")
            pprint(votestate[0])
            pprint("Final voting round transactions:")
            pprint(votestate[1])

    def period(self,
              label_or_id: str,
              period: str=None,
              all_periods: bool=False,
              blockheight: int=None,
              miniid: bool=False,
              start: bool=False,
              end: bool=False,
              debug: bool=False):
        """Shows information about the periods of a proposal.
        Proposal can be given as an ID, local label, mini ID (-m option) or as part of the ID string or description.

        NOTE: -e option can give nothing as a result, if the last period (E) is chosen.

        Usage options:

            pacli proposal period PROPOSAL

        Shows the current period of the proposal.

            pacli proposal period PROPOSAL -a

        Shows info about all periods of the proposal.

            pacli proposal period PROPOSAL PERIOD

        Shows info about a certain period of the proposal.
        PERIOD has to be entered as a string, combining a letter and a number (e.g. b20, e1)
        By default, the start and end block of the period are shown.

            pacli proposal period PROPOSAL -b BLOCK

        Shows info about the period of a proposal active at block BLOCK.

        Args:

           start: Shows only the start block of the period (script-friendly), current period is used if no PERIOD was given.
           end: Shows only the end block of the period (script-friendly), current period is used if no PERIOD was given.
           debug: Show debug information.
           miniid: Use the short ID of the proposal.
           period: Period (see Usage modes). To be used as a positional argument (flag name not mandatory).
           all_periods: Show all periods (see Usage modes).
           blockheight: Show period at a block height (see Usage modes).
        """

        pp_data = ei.run_command(self._get, label_or_id, require_states=False, miniid=miniid, label_priority=True, debug=debug)
        proposal_id = pp_data["id"]

        if start is True:
            mode = "start"
        elif end is True:
            mode = "end"
        else:
            mode = None

        if all_periods is True:
            return ei.run_command(self.__all_periods, proposal_id, debug=debug)
        elif period is not None:
            return ei.run_command(self.__get_period, proposal_id, period, mode=mode, debug=debug)
        else:
            return ei.run_command(self.__current_period, proposal_id, blockheight=blockheight, show_blockheights=True, mode=mode, debug=debug)

    # TODO: the period methods could be simplified, much code redundance.
    def __current_period(self, proposal: str, blockheight: int=None, show_blockheights: bool=True, mode: str=None, quiet: bool=False, debug: bool=False) -> None:
        """Shows the current period of the proposal lifecycle."""

        if mode in ("start", "end"):
            quiet = True
        proposal_id = eu.search_for_stored_tx_label("proposal", proposal, quiet=quiet)
        if blockheight is None:
            blockheight = provider.getblockcount() + 1
            if not quiet:
                pprint("Next block in the chain: {}".format(blockheight))
        deck = du.deck_from_ttx_txid(proposal_id, "proposal", provider, debug=debug)
        period, blockheights = du.get_period(proposal_id, deck, blockheight)

        if mode == "start":
            return blockheights[0]
        elif mode == "end":
            return blockheights[1]
        else:
            pprint(di.printout_period(period, blockheights, show_blockheights))


    def __all_periods(self, proposal: str, debug: bool=False) -> None:
        """Shows all periods of the proposal lifecycle."""

        proposal_id = eu.search_for_stored_tx_label("proposal", proposal)
        deck = ei.run_command(du.deck_from_ttx_txid, proposal_id, "proposal", provider, debug=debug)
        periods = ei.run_command(du.get_all_periods, proposal_id, deck)
        for period, blockheights in periods.items():
            print(di.printout_period(period, blockheights, blockheights_first=True))


    def __get_period(self, proposal: str, period: str, mode: str=None, debug: bool=False) -> object:
        """Shows the start or end block of a period. Use letter-number combination for the 'period' parameter ,e.g. 'b2'."""
        try:
            pletter = period[0].upper()
            pnumber = int(period[1:])
        except ValueError:
            if period in ("C", "E"):
                pnumber = 0
            else:
                raise ei.PacliInputDataError("Period entered in wrong format. You have to enter a letter-number combination, e.g. b10 or d50. Only periods C and E are accepted without number.")

        proposal_id = eu.search_for_stored_tx_label("proposal", proposal)
        proposal_tx = dmu.find_proposal(proposal_id, provider)
        periods = ei.run_command(du.get_all_periods, proposal_id, proposal_tx.deck)
        period_heights = periods[(pletter, pnumber)]

        if mode == "start":
            return period_heights[0]
        elif mode == "end":
            return period_heights[1]
        else:
            return period_heights


    # Tracked Transactions in Proposal class

    def create(self, identifier: str, req_amount: str=None, periods: int=None, intro: str="", change: str=Settings.change, tx_fee: str="0.01", modify: bool=False, force: bool=False, wait_for_confirmation: bool=False, sign: bool=False, send: bool=False, verify: bool=False, debug: bool=False, quiet: bool=False) -> None:
        """Creates a new proposal.

        Usage modes:

            pacli proposal create TOKEN REQ_AMOUNT PERIODS [INTRO]

        Creates a new proposal on token (deck) TOKEN with parameters:

        - requested amount REQ_AMOUNT
        - length of the working period in distribution periods: PERIODS
        - short introduction/description: INTRO (optional, but recommended)

        DECK can be a label or a deck ID.

            pacli proposal create PROPOSAL [[-r] REQ_AMOUNT] [[-p] PERIODS] [[-i] INTRO]

        Modifies the existing proposal PROPOSAL.
        The parameters can be entered as positional or keyword arguments.
        If only few parameters are to be changed, using keywords is recommended,
        to be able to skip the other parameters.

        Args:

          sign: Sign the transaction.
          send: Send the transaction.
          change: Set change address.
          modify: Modify the proposal (see Usage modes).
          tx_fee: Set custom transaction fee.
          wait_for_confirmation: Wait for a confirmation and show a message until then.
          verify: Verify transaction with Cointoolkit (Peercoin only).
          force: Create transaction even if the reorg check fails.
          quiet: Only output the transaction hexstring (script-friendly).
          debug: Display debugging information.
          req_amount: Requested amount. To be used as positional argument (flag name not necessary). See Usage modes.
          periods: Required periods. To be used as positional argument (flag name not necessary). See Usage modes.
          intro: Short introduction or description. To be used as positional argument (flag name not necessary). See Usage modes.
        """
        # NOTE: as deck is not mandatory when modifying an existing proposal, we can only use keyword arguments if we want to perserve the order.
        # req_amount and periods in modifications is not strictly necessary, re-check this! TODO

        kwargs = locals()

        if modify is True:
            kwargs.update({"proposal" : identifier})
        else:
            kwargs.update({"deck" : identifier})
        kwargs.update({"description" : intro, "txhex" : quiet})
        del kwargs["self"], kwargs["identifier"], kwargs["intro"], kwargs["quiet"], kwargs["modify"]
        return ei.run_command(dtx.create_trackedtransaction, "proposal", **kwargs)


    def vote(self, proposal: str, vote: str, tx_fee: str="0.01", change: str=Settings.change, verify: bool=False, sign: bool=False, send: bool=False, force: bool=False, wait_for_confirmation: bool=False, match_round: bool=False, quiet: bool=False, level_security: int=1, debug: bool=False) -> None:
        """Vote (with "yes" or "no") for a proposal.

        Usage:

            pacli proposal vote PROPOSAL [yes|no]

        Args:

          sign: Sign the transaction.
          send: Send the transaction.
          change: Set change address
          tx_fee: Set custom transaction fee.
          level_security: Security level.
          wait_for_confirmation: Wait for a confirmation and show a message until then.
          match_round: Wait for the next suitable voting round to broadcast the transaction.
          force: Create transaction even if the reorg check fails.
          verify: Verify transaction with Cointoolkit (Peercoin only).
          quiet: Only display the transaction hexstring (script-friendly).
          debug: Display debugging information."""

        kwargs = locals()
        kwargs.update({"txhex" : quiet, "security" : level_security, "wait" : match_round})
        del kwargs["self"], kwargs["match_round"], kwargs["level_security"], kwargs["quiet"]
        return ei.run_command(dtx.create_trackedtransaction, "voting", **kwargs)

class Donation:

    """Commands to manage donations in dPoD tokens."""

    # Tracked Transactions in Donation class
    # TODO: It would be best to find another word for "reserve", as we have already "round_number" with -r. Perhaps something like "next_round_reserve? (but -n is --new_inputs)

    def signal(self, proposal: str, amount: str, destination: str, change: str=Settings.change, tx_fee: str="0.01", wait_for_confirmation: bool=False, sign: bool=False, send: bool=False, verify: bool=False, round_number: int=None, match_round: bool=True, debug: bool=False, quiet: bool=False, level_security: int=1, force: bool=False) -> None:
        """Creates a compliant signalling transaction for a proposal. The destination address becomes the donor address of the Donation State. It can be added as an address or as a label.

        Usage:

        pacli donation signal PROPOSAL AMOUNT DESTINATION_ADDRESS [--sign --send]

        Args:

          sign: Sign the transaction.
          send: Send the transaction.
          match_round: Wait for the next signalling round to begin.
          round_number: In combination with -m, specify a round for the transaction to be sent (0 to 7).
          level_security: Specify a security level (default: 1)
          change: Set change address
          tx_fee: Set custom transaction fee.
          wait_for_confirmation: Wait for a confirmation and show a message until then.
          verify: Verify transaction with Cointoolkit (Peercoin only).
          quiet: Only display the transaction hexstring (script-friendly).
          debug: Display debugging information.
          force: Send the transaction even if the reorg check fails or some parameters do not make sense."""

        kwargs = locals()
        kwargs.update({"txhex" : quiet, "security" : level_security, "wait" : match_round, "check_round" : round_number})
        del kwargs["self"], kwargs["round_number"], kwargs["match_round"], kwargs["level_security"], kwargs["quiet"]
        return ei.run_command(dtx.create_trackedtransaction, "signalling", **kwargs)


    def lock(self, proposal: str, amount: str=None, destination: str=Settings.key.address, change: str=Settings.change, reserve: str=None, tx_fee: str="0.01", wait_for_confirmation: bool=False, sign: bool=False, send: bool=False, verify: bool=False, round_number: int=None, match_round: bool=False, new_inputs: bool=False, timelock: int=None, reserveamount: str=None, force: bool=False, debug: bool=False, quiet: bool=False, level_security: int=1) -> None:
        """Creates a Locking Transaction to lock funds for a donation, by default to the origin address.

        Usage:

            pacli transaction lock PROPOSAL [AMOUNT] [--sign --send]

        Lock an amount to be used as a donation for PROPOSAL.
        If the amount is not given, use the calculated slot.

        Args:

          amount: Specify a custom amount to lock.
          reserveamount: Reserve an amount to signal for the next suitable distribution round.
          reserve: Specify an address to send the reserve amount to.
          timelock: Specify a custom timelock (NOT recommended!)
          new_inputs: Do not use the output of the signalling transaction, but instead new ones.
          sign: Sign the transaction.
          send: Send the transaction.
          match_round: Wait for the next locking round to begin.
          round_number: In combination with --wait, specify a round for the transaction to be sent.
          level_security: Specify a security level (default: 1)
          change: Set change address
          tx_fee: Set custom transaction fee.
          wait_for_confirmation: Wait for a confirmation and show a message until then.
          verify: Verify transaction with Cointoolkit (Peercoin only).
          quiet: Only display the transaction hexstring (script-friendly).
          debug: Display debugging information.
          force: Send the transaction even if the reorg check fails or some parameters do not make sense.
          destination: Address the funds will be locked at.
        """

        kwargs = locals()
        kwargs.update({"txhex" : quiet, "security" : level_security, "wait" : match_round, "check_round" : round_number})
        del kwargs["self"], kwargs["round_number"], kwargs["match_round"], kwargs["level_security"], kwargs["quiet"]
        return ei.run_command(dtx.create_trackedtransaction, "locking", **kwargs)


    def release(self, proposal: str, amount: str=None, change: str=Settings.change, reserve: str=None, reserveamount: str=None, tx_fee: str="0.01", round_number: int=None, match_round: bool=False, new_inputs: bool=False, force: bool=False, wait_for_confirmation: bool=False, sign: bool=False, send: bool=False, verify: bool=False, debug: bool=False, quiet: bool=False, level_security: int=1) -> None:
        """Releases a donation and transfers the coins to the Proposer. This command can be used both in the release phase and in the donation rounds of the second distribution phase.

        Usage:

        pacli donation release PROPOSAL [options] [--sign --send]

        Args:

          amount: Specify a custom amount to release.
          reserveamount: Reserve an amount to signal for the next suitable distribution round.
          reserve: Specify an address to send the reserve amount to.
          new_inputs: Do not use the output of the locking or signalling transaction, but instead new ones.
          sign: Sign the transaction.
          send: Send the transaction.
          match_round: Wait for the next donation round to begin.
          round_number: In combination with --wait, specify a round for the transaction to be sent.
          level_security: Specify a security level (default: 1)
          change: Set change address
          tx_fee: Set custom transaction fee.
          wait_for_confirmation: Wait for a confirmation and show a message until then.
          verify: Verify transaction with Cointoolkit (Peercoin only).
          quiet: Only display the transaction hexstring (script-friendly).
          debug: Display debugging information.
          force: Send the transaction even if the reorg check fails or some parameters do not make sense.
        """

        kwargs = locals()
        kwargs.update({"txhex" : quiet, "security" : level_security, "wait" : match_round, "check_round" : round_number})
        del kwargs["self"], kwargs["round_number"], kwargs["match_round"], kwargs["level_security"], kwargs["quiet"]

        return ei.run_command(dtx.create_trackedtransaction, "donation", **kwargs)

    def proceed(self, proposal: str=None, donation: str=None, amount: str=None, label: str=None, send: bool=False):
        """EXPERIMENTAL method allowing to select the next step of a donation state with all standard values,
        i.e. selecting always the full slot and using the previous transactions' outputs.
        The command works if the block height corresponds to the correct period or the one directly before.

        Usage modes:

            pacli donation proceed PROPOSAL

        Proceed with a donation to PROPOSAL.

            pacli donation proceed -d DONATION_STATE

        Proceed with the specified donation state.

        Args:

          proposal: Proposal. To be used as a positional argument (flag name not mandatory). See Usage modes.
          donation: Donation state.
          amount: Select a custom amount.
          label: Label of the donor address.
          send: Send the transaction (signing is already sent to True)."""

        # you can use a label for your donation
        # TODO: may need adaptation for main address lock
        donor_label = label

        if donation is not None:
            dstate_id = eu.search_for_stored_tx_label("donation", donation)
            dstate = du.find_donation_state_by_string(dstate_id)
            deck = deck_from_ttx_txid(dstate_id)
            proposal_id = dstate.proposal_id
        elif proposal is not None:
            proposal_id = eu.search_for_stored_tx_label("proposal", proposal)
            deck = deck_from_ttx_txid(proposal_id)
            proposal_state = dmu.get_proposal_state(provider, proposal_id=proposal_id)
            dstate = get_dstates_from_donor_address(Settings.key.address, proposal_state)[0]
        else:
            print("You must provide either a proposal state or a donation state.")
            return

        if send is True:
            print("You selected to send your next transaction once the round has arrived.")
        else:
            print("This is a dry run, your transaction will not be sent. Use --send to send it.")

        if dstate.state == "complete":
            print("Donation state is already complete.")
            return
        elif dstate.state == "abandoned":
            print("Donation state is abandoned. You missed a step in the process.")
            return

        period = du.get_period(proposal_id, deck)
        dist_round = du.get_dist_round(proposal_id, period=period)

        if (not dstate) and (int(amount) > 0) and (donor_label is not None):
            self.signal(proposal_id, amount, dest_label=donor_label)
        # if block heights correspond to a slot distribution round, decide if we do a locking or donation transaction
        elif dstate.dist_round == dist_round:
            if dist_round <= 3 and dstate.signalling_tx:
                # here the next step should be a LockingTransaction
                self.lock(proposal_id, match_round=True, sign=True, send=send)
            elif dist_round >= 4 and dstate.signalling_tx:
                # next step is release.
                self.release(proposal_id, match_round=True, sign=True, send=send)
        elif period in (("D", 0), ("D", 1), ("D", 2)): # release period and 2 periods immediately before
            # (we don't need to check the locking tx because we checked the state already.)
            self.release(proposal_id, match_round=True, sign=True, send=send)
        elif period in (("D", 50), ("E", 0)):
            PoDToken().claim_reward(proposal_id)
        else:
            print("""This command only works in a period corresponding to a step in the donation process,
                     or the periods inmediately before. Wait until the period for your step has been reached.""")


    def create_tx(self, tx_type, **kwargs) -> None:
        """Generic tracked transaction creation.

        Usage:

            pacli donation create_tx TX_TYPE [options]

        Create a transaction of type TX_TYPE.
        Allowed values: proposal, vote, signalling, locking, donation.

        Options and flags:

        Please refer to the help docstring of the transaction type you want to create.
        """

        return ei.run_command(dtx.create_trackedtransaction, tx_type, **kwargs)

    # Other commands

    def __all_donation_states(self, proposal: str, all_states: bool=False, incomplete: bool=False, unclaimed: bool=False, mode: str=None, debug: bool=False) -> None:
        """Shows currently active (default) or all (--all flag) donation states of this proposal."""

        proposal_id = eu.search_for_stored_tx_label("proposal", proposal)
        dstates = dmu.get_donation_states(provider, proposal_id, debug=debug)
        allowed_states = di.get_allowed_states(all_states, unclaimed, incomplete)

        for dstate in dstates:

            if dstate.state not in allowed_states:
                continue

            di.display_donation_state(dstate, mode)

    def __my_donation_states(self, proposal: str, address: str=Settings.key.address, wallet: bool=False, all_matches: bool=False, all_states: bool=False, unclaimed: bool=False, incomplete: bool=False, keyring: bool=False, mode: str=None, debug: bool=False) -> None:
        """Shows the donation states involving a certain address (default: current active address)."""

        # TODO: not working properly; probably related to the label prefixes.

        proposal_id = eu.search_for_stored_tx_label("proposal", proposal)

        if wallet is True:

            all_dstates = ei.run_command(dmu.get_donation_states, provider, proposal_id, debug=debug)
            labels = ei.run_command(ec.get_all_labels, Settings.network, keyring=keyring)
            my_addresses = [ec.show_stored_address(label, network_name=Settings.network, noprefix=True, keyring=keyring) for label in labels]
            my_dstates = [d for d in all_dstates if d.donor_address in my_addresses]

        elif all_matches is True:
            # Includes states where the current address is used as origin or intermediate address.
            my_dstates = dmu.get_donation_states(provider, proposal_id, address=address, debug=debug)
        else:
            # Default behavior: only shows the state where the address is used as donor address.
            my_dstates = dmu.get_donation_states(provider, proposal_id, donor_address=address, debug=debug)

        allowed_states = di.get_allowed_states(all_states, unclaimed, incomplete)

        for pos, dstate in enumerate(my_dstates):
            if dstate.state not in allowed_states:
                continue
            pprint("Address: {}".format(dstate.donor_address))
            try:
                # this will only work if the label corresponding to the address was stored..
                # We catch the exception to allow using it for others' addresses.
                pprint("Label: {}".format(ec.show_label(dstate.donor_address)["label"], keyring=keyring))
            except:
                pass

            di.display_donation_state(dstate, mode)


    def list(self,
             token: str=None,
             examine_address: str=None,
             my: bool=False,
             wallet: bool=False,
             origin_matches: bool=False,
             all_states: bool=False,
             incomplete: bool=False,
             unclaimed: bool=False,
             short: bool=False,
             basic: bool=False,
             proposal: str=None,
             keyring: bool=False,
             debug: bool=False):
        """Shows a list of donation states.

        Usage modes:

            pacli donation list -p PROPOSAL

        Show all donation states made to a proposal and match the requirements lined out in the options.

            pacli donation list -m -p PROPOSAL [-w]

        Shows donation states made from this address or wallet (with -w) to a proposal.
        By default, incompleted and completed donations are shown.

            pacli donation list DECK

        Show all donation states for a deck.
        Can be limited to the own wallet (-m -w) or an address (-m or -e):

        Args:

          wallet: In combination with -m, show all donations made from the wallet.
          examine_address: In combination with -m, specify another donor address (labels allowed).
          all_states: Printout all donation states, including abandoned ones (cannot be combined with -i or -u).
          incomplete: Only show incomplete states (cannot be combined with -a or -u).
          unclaimed: Only show states with realized donation transactions which were still not claimed by the donor (cannot be combined with -a or -i).
          origin_matches: In combination with -m, show also states where the specified address is not the donor address but the origin address.
          keyring: In combination with -m, use the keyring of the OS for the address/key storage.
          short: Printout in short mode.
          basic: Printout in basic/simplified mode.
          debug: Show debug information.
          proposal: Proposal, if -m mode is used.
          my: Show donations made from an address or the user's wallet. See Usage modes.
          token: Deck or proposal. See Usage modes. To be used as a positional argument (flag name not mandatory).
        """

        if basic:
            mode = "simplified"
        elif short:
            mode = "short"
        else:
            mode = None

        if my is True:
            examine_address = Settings.key.address

        if proposal is not None:
             if my:
                 return ei.run_command(self.__my_donation_states, proposal, address=examine_address, wallet=wallet, all_matches=origin_matches, incomplete=incomplete, unclaimed=unclaimed, all_states=all_states, keyring=keyring, mode=mode, debug=debug)
             else:
                 return ei.run_command(self.__all_donation_states, proposal, incomplete=incomplete, unclaimed=unclaimed, all_states=all_states, mode=mode, debug=debug)
        elif token is not None:
             deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", token)
             return ei.run_command(dc.show_donations_by_address, deckid, examine_address, wallet=wallet, incomplete=incomplete, unclaimed=unclaimed, all_states=all_states, mode=mode, debug=debug)
        else:
             ei.print_red("Invalid option, you have to provide a proposal or a token (deck).")


    def __available_slot_amount(self, proposal_id: str, dist_round: int=None, current: bool=False, quiet: bool=False, debug: bool=False):
        """Shows the available slot amount in a slot distribution round, or show all of them. Default is the current round, if the current blockheight is inside one."""

        # proposal_id = eu.search_for_stored_tx_label("proposal", proposal)
        pstate = dmu.get_proposal_state(provider, proposal_id, debug=debug)

        if current is True:
            dist_round = ei.run_command(du.get_dist_round, proposal_id, pstate.deck)
            if dist_round is None:
                raise ei.PacliInputDataError("Current block height isn't inside a distribution round. Please provide one, or don't use --current.")
                return

        if dist_round is None:
            slots = []
            for rd, round_slot in enumerate(pstate.available_slot_amount):
                if quiet is True:
                    slots.append(round_slot)
                else:
                    pprint("Round {}: {}".format(rd, str(dmu.sats_to_coins(Decimal(round_slot), Settings.network))))

            if quiet is True:
                return slots
        else:
            slot = pstate.available_slot_amount[dist_round]
            if quiet is True:
                return slot
            else:
                pprint("Available slot amount for round {}:".format(dist_round))
                pprint(str(dmu.sats_to_coins(Decimal(slot), Settings.network)))


    def slot(self,
             proposal: str,
             round_number: int=None,
             address: str=None,
             my: bool=False,
             current: bool=False,
             satoshi: bool=False,
             quiet: bool=False,
             debug: bool=False) -> None:
        """Shows the available slots of a proposal.

        Usage modes:

            pacli donation slot PROPOSAL [ROUND_NUMBER]

        Shows all slots of a proposal, either in a specified distribution round, or of all rounds.

            pacli donation slot PROPOSAL -m

        Shows slots of the current main address.

            pacli donation slot PROPOSAL -a ADDRESS_OR_LABEL

        Shows slots of another address (can be given as a label).

        Args:

          round_number: Specify a distribution round. To be used as a positional argument (flag name not mandatory).
          current: If used at a block height corresponding to a distribution round of the proposal, show the slot for this round.
          satoshi: Shows the slot in satoshis (only in combination with --my).
          quiet: Suppresses information and shows slots in script-friendly way. Slots are always displayed in satoshi.
          debug: Display additional debug information.
          address: Address to check. See Usage modes.
          """
        # TODO: here a --wallet option would make sense.

        proposal_id = ei.run_command(eu.search_for_stored_tx_label,"proposal", proposal, quiet=quiet)
        if (not my) and (not address):
            return ei.run_command(self.__available_slot_amount, proposal_id, dist_round=round_number, current=current, quiet=quiet, debug=debug)

        if not address:
            address = Settings.key.address
        else:
            address = ec.process_address(address)

        result = ei.run_command(du.get_slot, proposal_id, donor_address=address, dist_round=round_number, quiet=quiet)

        if (dist_round is None) and (not quiet):
            print("Showing first slot where this address participated.")

        if (satoshi is True) or (quiet is True):
            slot = result["slot"]
        else:
            slot = du.sats_to_coins(result["slot"], Settings.network)

        if quiet is True:
            return result
        else:
            print("Distribution round:", result["round"])
            print("Slot:", slot)


    def qualified(self, proposal: str, round_number: int, address: str=Settings.key.address, label: str=None, debug: bool=False) -> bool:
        """Shows if the address is entitled to participate in a slot distribution round.

        Usage:

        pacli donation qualified PROPOSAL ROUND_NUMBER [ADDRESS| -l ADDRESS_LABEL]

        Shows if address ADDRESS (default: current main address) is qualified in the round ROUND_NUMBER.
        If a label is used, --label=ADDRESS_LABEL has to be used.

        Args:

          debug: Show additional debug information.
          address: Address to check.
          label: Label of the address to check.
        """
        # Note: the donor address must be used as the origin address for the new signalling transaction.
        # TODO: could probably be reworked with the ProposalState methods.
        # TODO: show_stored_key can be replaced with ce.process_address. We would then however have to detect if a label was used or not (for the "..with label.." part)

        proposal_id = ei.run_command(eu.search_for_stored_tx_label, "proposal", proposal)
        if label is not None:
            address = ke.show_stored_key(label, Settings.network)
            address_label = "{} with label {}".format(address, label)
        else:
            # we don't use show_label here so it's also possible to use under Windows.
            address_label = address

        print("Qualification status for address {} for distribution round {} in proposal {}:".format(address_label, round_number, proposal_id))

        slot_fill_threshold = 0.95
        if round_number in (0, 3, 6, 7):
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
                if round_number == ds.dist_round + 1:
                    if round_number in (1, 2) and (ds.state == "incomplete"):
                        if ds.effective_locking_slot >= min_qualifying_amount:
                            return True
                    # rd 4 is also rd 3 + 1
                    elif round_number in (4, 5) and (ds.state == "complete"):
                        if ds.effective_slot >= min_qualifying_amount:
                            return True
                elif (round_number == 4) and (ds.state == "complete"):
                    if ds.effective_slot >= min_qualifying_amount:
                        return True
            except TypeError:
                return False
        return False

    def check_address(self, proposal: str, address: str=Settings.key.address, quiet: bool=False):
        """Shows if the donor address was already used for a Proposal.

        Usage:

        pacli donation check_address PROPOSAL [ADDRESS]

        If ADDRESS is omitted, the current main address is used.
        Note: a "False" means that the check was not passed, i.e. the donor address should not be used.

        Args:

          address: Donor address. To be used as a positional argument (flag name not mandatory). See Usage.
          quiet: Suppress output."""

        proposal_id = ei.run_command(eu.search_for_stored_tx_label, "proposal", proposal, quiet=quiet)
        if du.donor_address_used(address, proposal_id):
            result = "Already used in this proposal, use another address." if not quiet else False
        else:
            result = "Not used in this proposal, you can freely use it." if not quiet else True
        return result
