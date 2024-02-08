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
from pacli.token_classes import Token


class PoDToken(Token):

    @classmethod
    def deck_spawn(self,
                   name: str,
                   epoch_length: int,
                   reward: int,
                   min_vote: int=0,
                   periods_sdp: int=None,
                   deck_sdp: str=None,
                   number_of_decimals=2,
                   change: str=Settings.change,
                   confirm: bool=False,
                   verify: bool=False,
                   sign: bool=False,
                   send: bool=False,
                   locktime: int=0) -> None:
        """Spawns a new DT deck.

        Usage:

        pacli podtoken deck_spawn NAME EPOCHLENGTH REWARD [options]

        Options and flags:
        -m, --min_vote PERCENTAGE: Voting threshold to approve a proposal (default: 0).
        -p, --periods_sdp PERIODS: Number of Special Distribution Periods.
        -d, --deck_sdp DECK: Deck for the Special Distribution Periods (can be ID or label)
        -n, --number_of_decimals NUMBER: Number of decimals of the token (default: 2).
        -t, --tx_fee: Specify a transaction fee.
        --change: Specify a change address.
        --sign: Sign the transaction (False by default).
        --send: Send the transaction (False by default).
        --confirm: Wait and display a message until the transaction is confirmed.
        --verify: Verify transaction with Cointoolkit."""

        asset_specific_data = ei.run_command(eu.create_deckspawn_data, c.ID_DT, epoch_length, reward, min_vote, periods_sdp, deck_sdp)
        change_address = ec.process_address(change)

        return ei.run_command(eu.advanced_deck_spawn, name=name, number_of_decimals=number_of_decimals, issue_mode=0x01,
                             change_address=change_address, locktime=locktime, asset_specific_data=asset_specific_data,
                             confirm=confirm, verify=verify, sign=sign, send=send)

    '''def init_deck(self, deck: str, store_label: str=None) -> None:
        """Initializes DT deck and imports all P2TH addresses into node.

        Usage options:

        pacli podtoken init_deck DECK

        Only initialize the deck (DECK can be a deck ID or a label if it was already stored).

        pacli podtoken init_deck DECK LABEL

        Initialize deck DECK and store a label LABEL for it.
        """

        deckid = eu.search_for_stored_tx_label("deck", deck)
        ei.run_command(dc.init_dt_deck, Settings.network, deckid, store_label=store_label)'''


    def deck_state(self, deck: str, debug: bool=False) -> None:
        '''Prints the DT deck state (the current state of the deck variables).

        Usage:

        pacli podtoken deck_state DECK

        Options:
        --debug: Shows debug information.

        '''
        deckid = eu.search_for_stored_tx_label("deck", deck)
        ei.run_command(dc.dt_state, deckid, debug)


    def claim(self,
              proposal: str,
              receivers: list=None,
              amounts: list=None,
              change: str=Settings.change,
              locktime: int=0,
              donation_state: str=None,
              donor_address:str=None,
              proposer: bool=False,
              verify: bool=False,
              sign: bool=True,
              send: bool=True,
              force: bool=False,
              quiet: bool=False,
              txhex: bool=False,
              confirm: bool=False,
              debug: bool=False) -> str:
        '''Issue Proof-of-donation tokens as a reward after a successful donation.

        Usage options:

        pacli podtoken claim PROPOSAL

        Claim the tokens and store them on the current main address, which has to be the donor.
        PROPOSAL is the proposal that was donated to.
        Note: as there can be only one donation per proposal and donor address, there is no possible ambiguity.

        pacli podtoken claim DECK TXID --receivers=[ADDR1, ADDR2, ...] --amounts=[AM1, AM2, ...]

        Claim the tokens and make a payment with the issued tokens to multiple receivers (put the lists into brackets)

        Options and flags:
        --proposer: Claim the proposer reward.
        --donation_state: Allows to specify a donation state (TXID of signalling transaction) if there are any ambiguities, for example if an incomplete donation was made from the same address.
        --donor_address: Allows to specify a different donor address to check if a claim from there is possible (--sign and --send are disabled).
        --locktime: Lock the transaction until a block or a time.
        --change: Specify a change address.
        --sign: Sign the transaction (True by default).
        --send: Send the transaction (True by default).
        --confirm: Wait and display a message until the transaction is confirmed.
        --verify: Verify transaction with Cointoolkit.
        --quiet: Suppress output.
        --txhex: Print out the transaction as a HEX string.
        --debug: Show additional debug information.
        --force: Create the transaction even if the reward does not match the transaction (only for debugging!).
        '''

        change_address = ec.process_address(change)
        proposal_id = eu.search_for_stored_tx_label("proposal", proposal)

        if donor_address is None:
            donor_address = Settings.key.address
        else:
            print("You provided a custom address. You will only be able to do a dry run to check if a certain address can claim tokens, but you can't actually claim tokens.\n--sign and --send are disabled, and if you sign the transaction manually it will be invalid.")
            sign, send = False, False

        if txhex:
            quiet = True

        asset_specific_data, receiver, payment, deckid = ei.run_command(dc.claim_pod_tokens, proposal_id, donor_address=donor_address, payment=amounts, receiver=receivers, donation_state=donation_state, proposer=proposer, force=force, debug=debug, quiet=quiet)

        tx = ei.run_command(eu.advanced_card_transfer, deckid=deckid, receiver=receivers, amount=amounts, asset_specific_data=asset_specific_data, change_address=change_address, verify=verify, locktime=locktime, confirm=confirm, quiet=quiet, sign=sign, send=send)
        return ei.output_tx(tx, txhex=txhex)


    def __get_votes(self, proposal: str, debug: bool=False) -> None:
        '''Displays the result of both voting rounds.'''
        # TODO: ideally there may be a variable indicating the second round has not started yet.

        proposal_id = eu.search_for_stored_tx_label("proposal", proposal)
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

    def __my_votes(self, deck: str, address: str=Settings.key.address) -> None:
        '''shows votes cast from this address, for all proposals of a deck.'''

        deckid = eu.search_for_stored_tx_label("deck", deck)
        return ei.run_command(dc.show_votes_by_address, deckid, address)

    def votes(self,
              proposal_or_deck: str=None,
              address: str=Settings.key.address,
              my: bool=False,
              debug: bool=False):
        """Shows votes, either of the current address, or of a specific proposal.

        Usage options:

        pacli podtoken votes PROPOSAL

        Shows all votes from all users on the proposal PROPOSAL.

        pacli podtoken votes DECK [-m/--my|ADDRESS]

        Shows all votes cast from the current address (-m/--my) or another ADDRESS for the specified deck DECK.

        Other options and flags:
        -d, --debug: prints debug information

        """

        if my or (address is not None):
            return self.__my_votes(proposal_or_deck, address=address)
        else:
            return self.__get_votes(proposal_or_deck, debug=debug)


class Proposal:


    def __info(self, proposal: str) -> None:
        '''Get basic info of a proposal.'''

        proposal_id = eu.search_for_stored_tx_label("proposal", proposal)
        proposal_tx = du.find_proposal(proposal_id, provider)
        pprint(proposal_tx.__dict__)

    def __find(self, searchstring: str, advanced: bool=False, shortid: bool=False) -> None:
        '''finds a proposal based on its description string or short id'''

        pstates = ei.run_command(du.find_proposal_state_by_string, searchstring, advanced=advanced, shortid=shortid)
        for pstate in pstates:
            # this should go into dt_interface
            pprint(pstate.idstring)
            pprint("Donation Address: {}".format(pstate.donation_address))
            pprint("ID: {}".format(pstate.id))
            if advanced:
                pprint("State: {}".format(pstate.state))

    def __state(self, proposal_string: str, param: str=None, simple: bool=False, complete: bool=False, quiet: bool=False, search: bool=False, debug: bool=False, ) -> None:
        '''Shows a single proposal state. You can search also for a short id (length 16 characters) or parts of the description.'''

        if search:
            pstate = ei.run_command(du.find_proposal_state_by_string, proposal_string, advanced=True, require_state=True)[0]
        else:
            if len(proposal_string) == 16:
                # if the length is 16 like in the short id, we search this id.
                pstate = ei.run_command(du.find_proposal_state_by_string, proposal_string, advanced=True, require_state=True, shortid=True)[0]
            else:
                proposal_id = eu.search_for_stored_tx_label("proposal", proposal_string)
                try:
                    pstate = dmu.get_proposal_state(provider, proposal_id, debug=debug)
                except (IndexError, KeyError) as e:
                    ei.print_red("Error: {}".format(e))

        pdict = pstate.__dict__
        if param is not None:
            result = pdict.get(param)
            if quiet:
                di.prepare_complete_collection(result)
                print(result)
            else:
                di.prepare_dict({"result" : result})
                pprint("Value of parameter {} for proposal {}:".format(param, proposal_id))
                pprint(result)
        elif quiet:
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

    def set(self,
            label: str,
            proposal_id: str,
            modify: bool=False,
            quiet: bool=False) -> None:
        """Stores a proposal with label and proposal id (TXID). Use --modify to change the label.

        Usage options:

        pacli proposal set LABEL PROPOSAL_ID

        Stores a new proposal.

        pacli proposal set NEW_LABEL OLD_LABEL -m/--modify

        Modifies the label of an already stored proposal.

        Flags:
        -q, --quiet: Suppress output.
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

        Usage options:

        pacli proposal show LABEL

        Shows a proposal ID stored with a label LABEL.

        pacli proposal show LABEL_OR_ID -i/--info

        Shows basic information about a proposal.

        pacli proposal show LABEL_OR_ID -s/--state [-p/--param PARAM] [-a/--advanced]

        Shows a dictionary with the current state of a proposal.
        If -p/--param is given, display only a specific parameter of the dictionary.
        If -a/--advanced is given, show advanced information.

        pacli proposal show STRING -f/--find [-m/--miniid]

        Find a proposal containing STRING in its ID or description.
        If -m/--miniid is given, the STRING must match the mini ID (first 8 characters) of the proposal.

        Other options and flags:
        -q, --quiet: Suppress addiitonal output, print information in raw format (script-friendly).
        -d, --debug: Provide additional debug information.

        """

        if info:
            return self.__info(label_or_id)
        elif state:
            # note: --state and --find can be together.
            # proposal_string: str, param: str=None, simple: bool=False, complete: bool=False, raw: bool=False, search: bool=False, debug: bool=False, ) -> None:
            return self.__state(label_or_id, param=param, complete=advanced, simple=basic, quiet=quiet, search=find, debug=debug)
        elif find:
            return self.__find(label_or_id, advanced=advanced, shortid=miniid)
        return ce.show("proposal", label_or_id, quiet=quiet)

    def list(self,
             id_or_label: str=None,
             blockheight: int=False,
             only_active: bool=False,
             all: bool=False,
             simple: bool=False,
             quiet: bool=False,
             named: bool=False,
             debug: bool=False) -> None:
        """Shows a list of proposals.

        Usage options:

        pacli proposal list DECK [--only_active|--all]

        Shows proposals of DECK. By default, shows active and completed proposals.
        DECK can be a deck ID or a label.

        Flags of this mode:
        -o, --only_active: shows only currently active proposals.
        -a, --all: in addition to active and completed, shows also abandoned proposals.
        -s, --simple: Like --all, but doesn't show proposals' state (much faster).
        -b, --blockheight: Block height to consider for the proposals' state (debugging option)

        pacli proposal list -n/--named

        Shows proposals a label was assigned to.

        Other options and flags:

        -q, --quiet: If used with --named, suppress additional output and printout list in a script-friendly way.
        -d, --debug: Show debugging information.
        """

        if named:
            return ce.list("proposal", quiet=quiet)
        else:
            return ei.run_command(dc.list_current_proposals, id_or_label, block=blockheight, only_active=only_active, all=all, simple=simple, debug=debug)

    def voters(self,
               proposal: str,
               debug: bool=False,
               blockheight: int=None,
               outputformat=None) -> None:
        '''Shows enabled voters and their balance at the start of the current epoch of a proposal, or at a defined blockheight.

        Usage:
        pacli proposal voters PROPOSAL [options]

        Options and flags:
        -o, --outputformat FORMAT: Use a different output format.
            Allowed values:
                'simpledict' prints out a script-friendly dict,
                'voterlist' prints out only a list of voters.
        -b, --blockheight: Block height to consider for the voters' balances (mainly debugging command)
        -d, --debug: Show additional debug information.
        '''
        # TODO: if blockheight option is given, proposal isn't strictly necessary. But the code would have to be changed for that.
        # TODO: the voter weight is shown in scientific notation. Should be re-formatted.

        proposal_id = eu.search_for_stored_tx_label("proposal", proposal)
        proposal_tx = dmu.find_proposal(proposal_id, provider)
        deck = proposal_tx.deck

        # parser_state = dmu.get_parser_state(provider, deck=proposal_tx.deck, debug_voting=debug, force_continue=True, lastblock=blockheight)

        if blockheight is None:
            # epoch = parser_state.epoch
            epoch = provider.getblockcount() // deck.epoch_length
            blockheight = deck.epoch_length * epoch
            # blockheight = parser_state.deck.epoch_length * epoch
        else:
            # epoch = blockheight // parser_state.deck.epoch_length
            epoch = blockheight // deck.epoch_length

        parser_state = dmu.get_parser_state(provider, deck=deck, debug_voting=debug, force_continue=True, lastblock=blockheight)

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

    # TODO: the period methods could be simplified, much code redundance.
    def __current_period(self, proposal: str, blockheight: int=None, show_blockheights: bool=True, mode: str=None, quiet: bool=False, debug: bool=False) -> None:
        '''Shows the current period of the proposal lifecycle.'''

        if mode in ("start", "end"):
            quiet = True
        proposal_id = eu.search_for_stored_tx_label("proposal", proposal, quiet=quiet)
        if blockheight is None:
            blockheight = provider.getblockcount() + 1
            if not quiet:
                pprint("Next block: {}".format(blockheight))
        deck = ei.run_command(du.deck_from_ttx_txid, proposal_id, "proposal", provider, debug=debug)
        period, blockheights = ei.run_command(du.get_period, proposal_id, deck, blockheight)

        if mode == "start":
            return blockheights[0]
        elif mode == "end":
            return blockheights[1]
        else:
            pprint(di.printout_period(period, blockheights, show_blockheights))


    def __all_periods(self, proposal: str, debug: bool=False) -> None:
        '''Shows all periods of the proposal lifecycle.'''

        proposal_id = eu.search_for_stored_tx_label("proposal", proposal)
        deck = ei.run_command(du.deck_from_ttx_txid, proposal_id, "proposal", provider, debug=debug)
        periods = ei.run_command(du.get_all_periods, proposal_id, deck)
        for period, blockheights in periods.items():
            print(di.printout_period(period, blockheights, blockheights_first=True))


    def __get_period(self, proposal: str, period: str, mode: str=None) -> object:
        """Shows the start or end block of a period. Use letter-number combination for the 'period' parameter ,e.g. 'b2'."""
        try:
            pletter = period[0].upper()
            pnumber = int(period[1:])
        except:
            ei.print_red("Error: Period entered in wrong format. You have to enter a letter-number combination, e.g. b10 or d50.")

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

    def period(self,
              proposal: str,
              period: str=None,
              all: bool=False,
              blockheight: int=None,
              start: bool=False,
              end: bool=False,
              debug: bool=False):
        '''Shows information about the periods of a proposal.

        Usage options:

        pacli proposal period

        Shows the current period of the proposal.

        pacli proposal period -a/--all

        Shows info about all periods of the proposal.

        pacli proposal period PERIOD

        Shows info about a certain period of the proposal.
        PERIOD has to be entered as a string, combining a letter and a number (e.g. b20, e1)
        By default, the start and end block of the period are shown.

        pacli proposal period --blockheight=BLOCK

        Shows info about the period of a proposal active at block BLOCK.


        Other options and flags:

        -s, --start: If used with a PERIOD, shows only the start block of the period (script-friendly).
        -e, --end: If used with a PERIOD, shows only the end block of the period (script-friendly).
        -d, --debug: Show debug information.

        NOTE: --end can give nothing as a result, if the last period (E) is chosen.

        '''
        if start:
            mode = "start"
        elif end:
            mode = "end"
        else:
            mode = None

        if all:
            return self.__all_periods(proposal, debug=debug)
        elif period:
            return self.__get_period(proposal, period, mode=mode)
        else:
            return self.__current_period(proposal, blockheight=blockheight, show_blockheights=True, mode=mode, debug=debug)

    """def list(self, deck: str, block: int=None, only_active: bool=False, all: bool=False, simple: bool=False, debug: bool=False) -> None:
        '''Shows all proposals for a deck and the period they are currently in, optionally at a specific blockheight.'''
        # TODO re-check: it seems that if we use Decimal for values like req_amount scientific notation is used.
        # Using float instead seems to work well when it's only divided by the "Coin" value (1000000 in PPC)
        # TODO ensure that the simple mode also takes into account Proposal Modifications
        # TODO add deck label mode (solved?)

        deckid = eu.search_for_stored_tx_label("deck", deck)
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

        pstate_periods = ei.run_command(du.get_proposal_state_periods, deckid, block, advanced=advanced, debug=debug)

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
            print("No {}proposal states found for deck {}.".format(pmsg, deckid))"""

    # Tracked Transactions in Proposal class

    def create(self, deck: str=None, req_amount: str=None, periods: int=None, description: str="", change: str=Settings.change, tx_fee: str="0.01", modify: str=None, confirm: bool=False, sign: bool=False, send: bool=False, verify: bool=False, debug: bool=False, txhex: bool=False) -> None:
        '''Creates a new proposal.

        Usage options:

        pacli proposal create DECK REQ_AMOUNT PERIODS [DESCRIPTION] [--sign --send]

        Creates a new proposal on deck DECK with parameters:
        - requested amount REQ_AMOUNT
        - lengt of the working period in distribution periods: PERIODS
        - short description: DESCRIPTION

        pacli proposal create --modify=PROPOSAL [options] [--sign --send]

        Modifies the existing proposal PROPOSAL.

        Other options and flags:
        --sign: Sign the transaction.
        --send: Send the transaction.
        --change: Set change address
        --tx_fee: Set custom transaction fee.
        --confirm: Wait for a confirmation and show a message until then.
        --verify: Verify transaction with Cointoolkit.
        --txhex: Only display the transaction hexstring (script-friendly).
        --debug: Display debugging information.
        '''
        # NOTE: as deck is not mandatory when modifying an existing proposal, we can only use keyword arguments if we want to perserve the order.
        # req_amount and periods in modifications is not strictly necessary, re-check this! TODO

        kwargs = locals()
        if modify:
            kwargs.update({"proposal" :  modify})
            del kwargs["modify"]
        del kwargs["self"]
        return ei.run_command(dtx.create_trackedtransaction, "proposal", **kwargs)


    def vote(self, proposal: str, vote: str, tx_fee: str="0.01", change: str=Settings.change, verify: bool=False, sign: bool=False, send: bool=False, wait: bool=False, confirm: bool=False, txhex: bool=False, security: int=1, debug: bool=False) -> None:
        '''Vote (with "yes" or "no") for a proposal.

        Usage:

        pacli proposal vote PROPOSAL [yes|no]

        Options:
        --sign: Sign the transaction.
        --send: Send the transaction.
        --change: Set change address
        --tx_fee: Set custom transaction fee.
        --confirm: Wait for a confirmation and show a message until then.
        --verify: Verify transaction with Cointoolkit.
        --txhex: Only display the transaction hexstring (script-friendly).
        --debug: Display debugging information.'''

        kwargs = locals()
        del kwargs["self"]
        return ei.run_command(dtx.create_trackedtransaction, "voting", **kwargs)




class Donation:

    # Tracked Transactions in Donation class

    def signal(self, proposal: str, amount: str, destination: str, change: str=Settings.change, tx_fee: str="0.01", confirm: bool=False, sign: bool=False, send: bool=False, verify: bool=False, check_round: int=None, wait: bool=True, debug: bool=False, txhex: bool=False, security: int=1, force: bool=False) -> None:
        '''Creates a compliant signalling transaction for a proposal. The destination address becomes the donor address of the Donation State. It can be added as an address or as a label.

        Usage:

        pacli donation signal PROPOSAL AMOUNT DESTINATION_ADDRESS [--sign --send]

        Options and flags:

        --sign: Sign the transaction.
        --send: Send the transaction.
        --wait: Wait for the next signalling round to begin.
        --check_round: In combination with --wait, specify a round for the transaction to be sent.
        --security: Specify a security level (default: 1)
        --change: Set change address
        --tx_fee: Set custom transaction fee.
        --confirm: Wait for a confirmation and show a message until then.
        --verify: Verify transaction with Cointoolkit.
        --txhex: Only display the transaction hexstring (script-friendly).
        --debug: Display debugging information.
        --force: Send the transaction even if some parameters are wrong (debugging option).'''

        kwargs = locals()
        del kwargs["self"]
        return ei.run_command(dtx.create_trackedtransaction, "signalling", **kwargs)


    def lock(self, proposal: str, amount: str=None, change: str=Settings.change, destination: str=Settings.key.address, reserve: str=None, tx_fee: str="0.01", confirm: bool=False, sign: bool=False, send: bool=False, verify: bool=False, check_round: int=None, wait: bool=False, new_inputs: bool=False, timelock: int=None, reserveamount: str=None, force: bool=False, debug: bool=False, txhex: bool=False, security: int=1) -> None:
        '''Creates a Locking Transaction to lock funds for a donation, by default to the origin address.

        Usage:

        pacli transaction lock PROPOSAL [options] [--sign --send]

        Lock an amount to be used as a donation for PROPOSAL.
        If the amount is not given, use the calculated slot.

        Options and flags:

        --amount: Specify a custom amount to lock.
        --reserveamount: Reserve an amount to signal for the next suitable distribution round.
        --reserve: Specify an address to send the reserve amount to.
        --timelock: Specify a custom timelock (NOT recommended!)
        --new_inputs: Do not use the output of the signalling transaction, but instead new ones.
        --sign: Sign the transaction.
        --send: Send the transaction.
        --wait: Wait for the next locking round to begin.
        --check_round: In combination with --wait, specify a round for the transaction to be sent.
        --security: Specify a security level (default: 1)
        --change: Set change address
        --tx_fee: Set custom transaction fee.
        --confirm: Wait for a confirmation and show a message until then.
        --verify: Verify transaction with Cointoolkit.
        --txhex: Only display the transaction hexstring (script-friendly).
        --debug: Display debugging information.
        --force: Send the transaction even if some parameters are wrong (debugging option).
        '''

        kwargs = locals()
        del kwargs["self"]
        return ei.run_command(dtx.create_trackedtransaction, "locking", **kwargs)


    def release(self, proposal: str, amount: str=None, change: str=Settings.change, reserve: str=None, reserveamount: str=None, tx_fee: str="0.01", check_round: int=None, wait: bool=False, new_inputs: bool=False, force: bool=False, confirm: bool=False, sign: bool=False, send: bool=False, verify: bool=False, debug: bool=False, txhex: bool=False, security: int=1) -> None:
        '''Releases a donation and transfers the coins to the Proposer. This command can be used both in the release phase and in the donation rounds of the second distribution phase.

        Usage:

        pacli donation release PROPOSAL [options] [--sign --send]

        Options and flags:

        --amount: Specify a custom amount to release.
        --reserveamount: Reserve an amount to signal for the next suitable distribution round.
        --reserve: Specify an address to send the reserve amount to.
        --new_inputs: Do not use the output of the locking or signalling transaction, but instead new ones.
        --sign: Sign the transaction.
        --send: Send the transaction.
        --wait: Wait for the next donation round to begin.
        --check_round: In combination with --wait, specify a round for the transaction to be sent.
        --security: Specify a security level (default: 1)
        --change: Set change address
        --tx_fee: Set custom transaction fee.
        --confirm: Wait for a confirmation and show a message until then.
        --verify: Verify transaction with Cointoolkit.
        --txhex: Only display the transaction hexstring (script-friendly).
        --debug: Display debugging information.
        --force: Send the transaction even if some parameters are wrong (debugging option).
        '''

        kwargs = locals()
        del kwargs["self"]
        return ei.run_command(dtx.create_trackedtransaction, "donation", **kwargs)

    def proceed(self, proposal: str=None, donation: str=None, amount: str=None, donor_label: str=None, send: bool=False):
        '''EXPERIMENTAL method allowing to select the next step of a donation state with all standard values,
        i.e. selecting always the full slot and using the previous transactions' outputs.
        The command works if the block height corresponds to the correct period or the one directly before.

        Usage options:

        pacli donation proceed PROPOSAL

        Proceed with a donation to PROPOSAL.

        pacli donation proceed --donation=DONATION_STATE

        Proceed with the specified donation state.

        Options and flags:

        --amount: Select a custom amount.
        --donor_label: Select a donor label.
        --send: Send the transaction (signing is already sent to True).'''

        # you can use a label for your donation

        if donation:
            dstate_id = eu.search_for_stored_tx_label("donation", donation)
            dstate = du.find_donation_state_by_string(dstate_id)
            deck = deck_from_ttx_txid(dstate_id)
            proposal_id = dstate.proposal_id
        elif proposal:
            proposal_id = eu.search_for_stored_tx_label("proposal", proposal)
            deck = deck_from_ttx_txid(proposal_id)
            proposal_state = get_proposal_state(provider, proposal_id=proposal_id)
            dstate = get_dstates_from_donor_address(Settings.key.address, proposal_state)[0]
        else:
            print("You must provide either a proposal state or a donation state.")
            return

        if send:
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

        if (not dstate) and (int(amount) > 0) and donor_label:
            self.signal(proposal_id, amount, dest_label=donor_label)
        # if block heights correspond to a slot distribution round, decide if we do a locking or donation transaction
        elif dstate.dist_round == dist_round:
            if dist_round <= 3 and dstate.signalling_tx:
                # here the next step should be a LockingTransaction
                self.lock(proposal_id, wait=True, sign=True, send=send)
            elif dist_round >= 4 and dstate.signalling_tx:
                # next step is release.
                self.release(proposal_id, wait=True, sign=True, send=send)
        elif period in (("D", 0), ("D", 1), ("D", 2)): # release period and 2 periods immediately before
            # (we don't need to check the locking tx because we checked the state already.)
            self.release(proposal_id, wait=True, sign=True, send=send)
        elif period in (("D", 50), ("E", 0)):
            PoDToken().claim_reward(proposal_id)
        else:
            print("""This command only works in a period corresponding to a step in the donation process,
                     or the periods inmediately before. Wait until the period for your step has been reached.""")


    def create_tx(self, tx_type, **kwargs) -> None:
        '''Generic tracked transaction creation.

        Usage:

        pacli donation create_tx TX_TYPE [options]

        Create a transaction of type TX_TYPE.
        Allowed values: proposal, vote, signalling, locking, donation.

        Options and flags:

        Please refer to the help docstring of the transaction type you want to create.
        '''

        return ei.run_command(dtx.create_trackedtransaction, tx_type, **kwargs)

    # Other commands

    def __all_donation_states(self, proposal: str, all: bool=False, incomplete: bool=False, unclaimed: bool=False, mode: str=None, debug: bool=False) -> None:
        '''Shows currently active (default) or all (--all flag) donation states of this proposal.'''

        proposal_id = eu.search_for_stored_tx_label("proposal", proposal)
        dstates = dmu.get_donation_states(provider, proposal_id, debug=debug)
        allowed_states = di.get_allowed_states(all, unclaimed, incomplete)

        for dstate in dstates:

            if dstate.state not in allowed_states:
                continue

            di.display_donation_state(dstate, mode)

    def __my_donation_states(self, proposal: str, address: str=Settings.key.address, wallet: bool=False, all_matches: bool=False, all: bool=False, unclaimed: bool=False, incomplete: bool=False, keyring: bool=False, mode: str=None, debug: bool=False) -> None:
        '''Shows the donation states involving a certain address (default: current active address).'''
        # TODO: --all_addresses is linux-only until show_stored_address is converted to new config scheme.
        # TODO: not working properly; probably related to the label prefixes.

        proposal_id = eu.search_for_stored_tx_label("proposal", proposal)

        if wallet:

            all_dstates = ei.run_command(dmu.get_donation_states, provider, proposal_id, debug=debug)
            labels = ei.run_command(ec.get_all_labels, Settings.network, keyring=keyring)
            my_addresses = [ec.show_stored_address(label, network_name=Settings.network, noprefix=True, keyring=keyring) for label in labels]
            my_dstates = [d for d in all_dstates if d.donor_address in my_addresses]

        elif all_matches:
            # Includes states where the current address is used as origin or intermediate address.
            my_dstates = dmu.get_donation_states(provider, proposal_id, address=address, debug=debug)
        else:
            # Default behavior: only shows the state where the address is used as donor address.
            my_dstates = dmu.get_donation_states(provider, proposal_id, donor_address=address, debug=debug)

        allowed_states = di.get_allowed_states(all, unclaimed, incomplete)

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
             deck_or_proposal: str=None,
             address: str=Settings.key.address,
             my: bool=False,
             wallet: bool=False,
             all_matches: bool=False,
             all: bool=False,
             incomplete: bool=False,
             unclaimed: bool=False,
             short: bool=False,
             proposal: str=None,
             keyring: bool=False,
             mode: str=None,
             debug: bool=False):
        """Shows a list of donation states.

        Usage options:

        pacli donation list PROPOSAL

        Show all donation states made to a proposal and match the requirements lined out in the options.

        pacli donation list --my --proposal=PROPOSAL [--wallet]

        Shows donation states made from this address or wallet to a proposal.
        By default, incompleted and completed donations

        pacli donation list DECK --my

        Show all donation states made from that address.

        Other options and flags:
        --wallet: In combination with --my and --proposal, show all donations made from the wallet.
        --address: In combination with --my, specify another donor address.
        --all: In combination with --my, printout all donation states (also abandoned ones).
        --incomplete: In combination with --my, only show incomplete states.
        --unclaimed: In combination with --my, only show states still not claimed.
        --all_matches: In combination with --my, show also states where the specified address is not the donor address but the origin address.
        --keyring: In combination with --my, use the keyring of the OS for the address/key storage.
        --mode: Printout in a specific mode (allowed options: 'short', 'simplified').
        --debug: Show debug information.
        """
        # TODO: an option --wallet for the variant with DECK would be useful.

        if my:
             if proposal:
                 return ei.run_command(self.__my_donation_states, proposal, address=address, wallet=wallet, all_matches=all_matches, incomplete=incomplete, unclaimed=unclaimed, all=all, keyring=keyring, mode=mode, debug=debug)
             else:
                 deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck_or_proposal)
                 return ei.run_command(dc.show_donations_by_address, deckid, address, mode=mode)

        elif deck_or_proposal is not None:
             proposal = deck_or_proposal
             return ei.run_command(self.__all_donation_states, proposal, incomplete=incomplete, unclaimed=unclaimed, all=all, mode=mode, debug=debug)
        else:
             ei.print_red("Invalid option, you have to provide a proposal or a deck.")


    def check_tx(self, txid=None, txhex=None, proposal: str=None, include_badtx: bool=False, light: bool=False) -> None:
        '''Creates a TrackedTransaction object and shows its properties. Primarily for debugging.

        Usage options:

        pacli donation check_tx --proposal=PROPOSAL

        Lists all TrackedTransactions for a proposal, even invalid ones.

        pacli donation check_tx [--txid=TXID|--txhex=TXHEX]

        Displays all attributes of a TrackedTransaction, given a TXID or the transaction in hex format (TXHEX).

        Options and flags:
        --include_badtx: also detects wrongly formatted transactions, but only displays the txid.
        --light: Faster mode, not displaying properties depending from deck state.
        '''

        if proposal:

            # ex check_all_tx

            proposal_id = eu.search_for_stored_tx_label("proposal", proposal)
            return ei.run_command(du.get_all_trackedtxes, proposal_id, include_badtx=include_badtx, light=light)

        tx = ei.run_command(du.get_trackedtx, txid=txid, txhex=txhex)
        pprint("Type: " + str(type(tx)))
        pprint(tx.__dict__)


    """def check_all_tx(self, proposal: str, include_badtx: bool=False, light: bool=False) -> None:
        '''Lists all TrackedTransactions for a proposal, even invalid ones.
           include_badtx also detects wrongly formatted transactions, but only displays the txid.'''

        proposal_id = eu.search_for_stored_tx_label("proposal", proposal)
        ei.run_command(du.get_all_trackedtxes, proposal_id, include_badtx=include_badtx, light=light)""" # done, see check_tx


    def __available_slot_amount(self, proposal_id: str, dist_round: int=None, current: bool=False, quiet: bool=False, debug: bool=False):
        '''Shows the available slot amount in a slot distribution round, or show all of them. Default is the current round, if the current blockheight is inside one.'''

        # proposal_id = eu.search_for_stored_tx_label("proposal", proposal)
        pstate = dmu.get_proposal_state(provider, proposal_id, debug=debug)

        if current:
            dist_round = ei.run_command(du.get_dist_round, proposal_id, pstate.deck)
            if dist_round is None:
                raise ei.PacliInputDataError("Current block height isn't inside a distribution round. Please provide one, or don't use --current.")
                return

        if dist_round is None:
            slots = []
            for rd, round_slot in enumerate(pstate.available_slot_amount):
                if quiet:
                    slots.append(round_slot)
                else:
                    pprint("Round {}: {}".format(rd, str(dmu.sats_to_coins(Decimal(round_slot), Settings.network))))

            if quiet:
                return slots
        else:
            slot = pstate.available_slot_amount[dist_round]
            if quiet:
                return slot
            else:
                pprint("Available slot amount for round {}:".format(dist_round))
                pprint(str(dmu.sats_to_coins(Decimal(slot), Settings.network)))


    def slot(self,
             proposal: str,
             dist_round: int=None,
             address: str=None,
             my: bool=False,
             current: bool=False,
             satoshi: bool=False,
             quiet: bool=False,
             debug: bool=False) -> None:
        '''Shows the available slots of a proposal.

        Usage options:

        pacli donation slot PROPOSAL [DIST_ROUND]

        Shows all slots of a proposal, either in a specified distribution round, or of all rounds.

        pacli donation slot PROPOSAL --my

        Shows slots of the current main address.

        pacli donation slot PROPOSAL --address=ADDRESS_OR_LABEL

        Shows slots of another address (can be given as a label).

        Options and flags:

        --dist_round: Specify a distribution round.
        --current: If used at a block height corresponding to a distribution round of the proposal, show the slot for this round.
        --satoshi: Shows the slot in satoshis (only in combination with --my).
        --quiet: Suppresses information and shows slots in script-friendly way. Slots are always displayed in satoshi.
        --debug: Display additional debug information.'''
        # TODO: here a --wallet option would make sense.

        proposal_id = ei.run_command(eu.search_for_stored_tx_label,"proposal", proposal, quiet=quiet)
        if (not my) and (not address):
            return ei.run_command(self.__available_slot_amount, proposal_id, dist_round=dist_round, current=current, quiet=quiet, debug=debug)

        if not address:
            address = Settings.key.address
        else:
            address = ec.process_address(address)

        result = ei.run_command(du.get_slot, proposal_id, donor_address=address, dist_round=dist_round, quiet=quiet)

        if (dist_round is None) and (not quiet):
            print("Showing first slot where this address participated.")

        if satoshi or quiet:
            slot = result["slot"]
        else:
            slot = du.sats_to_coins(result["slot"], Settings.network)

        if quiet:
            return result
        else:
            print("Distribution round:", result["round"])
            print("Slot:", slot)


    def qualified(self, proposal: str, round_dist: int, address: str=Settings.key.address, label: str=None, debug: bool=False) -> bool:
        '''Shows if the address is entitled to participate in a slot distribution round.

        Usage:

        pacli donation qualified PROPOSAL DIST_ROUND [ADDRESS|--label=ADDRESS_LABEL]

        Shows if address ADDRESS (default: current main address) is qualified.
        If a label is used, --label=ADDRESS_LABEL has to be used.

        Options and flags:
        --debug: Show additional debug information.
        '''
        # Note: the donor address must be used as the origin address for the new signalling transaction.
        # TODO: could probably be reworked with the ProposalState methods.
        # TODO: show_stored_key can be replaced with ce.process_address. We would then however have to detect if a label was used or not (for the "..with label.." part)

        proposal_id = eu.search_for_stored_tx_label("proposal", proposal)
        if label is not None:
            address = ke.show_stored_key(label, Settings.network)
            address_label = "{} with label {}".format(address, label)
        else:
            # we don't use show_label here so it's also possible to use under Windows.
            address_label = address

        print("Qualification status for address {} for distribution round {} in proposal {}:".format(address_label, round_dist, proposal_id))

        slot_fill_threshold = 0.95
        if round_dist in (0, 3, 6, 7):
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
                if round_dist == ds.dist_round + 1:
                    if round_dist in (1, 2) and (ds.state == "incomplete"):
                        if ds.effective_locking_slot >= min_qualifying_amount:
                            return True
                    # rd 4 is also rd 3 + 1
                    elif round_dist in (4, 5) and (ds.state == "complete"):
                        if ds.effective_slot >= min_qualifying_amount:
                            return True
                elif (round_dist == 4) and (ds.state == "complete"):
                    if ds.effective_slot >= min_qualifying_amount:
                        return True
            except TypeError:
                return False
        return False

    def check_address(self, proposal: str, donor_address: str=Settings.key.address, quiet: bool=False):
        '''Shows if the donor address was already used for a Proposal.

        Usage:

        pacli donation check_address PROPOSAL [DONOR_ADDRESS]

        If DONOR_ADDRESS is omitted, the current main address is used.
        Note: a "False" means that the check was not passed, i.e. the donor address should not be used.

        Flag:
        -q, --quiet: Suppress output.'''

        proposal_id = ei.run_command(eu.search_for_stored_tx_label, "proposal", proposal, quiet=quiet)
        if du.donor_address_used(donor_address, proposal_id):
            result = "Already used in this proposal, use another address." if not quiet else False
        else:
            result = "Not used in this proposal, you can freely use it." if not quiet else True
        return result
