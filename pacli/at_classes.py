import hashlib
import pypeerassets as pa
import pypeerassets.at.constants as c
from prettyprinter import cpprint as pprint
from pypeerassets.at.mutable_transactions import TransactionDraft
from pypeerassets.pautils import exponent_to_amount
from decimal import Decimal
from pacli.provider import provider
from pacli.config import Settings
from pacli.tui import print_deck_list
import pacli.extended_utils as eu
import pacli.extended_interface as ei
import pacli.at_utils as au
import pacli.extended_commands as ec
import pacli.config_extended as ce
import pacli.keystore_extended as ke
from pypeerassets.at.dt_misc_utils import list_decks_by_at_type

class ATTokenBase():

    def _create_tx(self, address_or_deck: str, amount: str, tx_fee: Decimal=None, change: str=Settings.change, sign: bool=True, send: bool=True, wait_for_confirmation: bool=False, verify: bool=False, quiet: bool=False, force: bool=False, debug: bool=False, optimize: bool=False) -> str:

        ke.check_main_address_lock()
        amount = Decimal(str(amount))
        if (amount == 0) or (amount < 0):
            raise ei.PacliInputDataError("Invalid amount, amount must be above zero.")

        if not eu.is_possible_address(address_or_deck):
            deckid = eu.search_for_stored_tx_label("deck", address_or_deck, quiet=quiet)
            deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
            try:
                address = deck.at_address
            except AttributeError:
                raise ei.PacliInputDataError("Wrong type of deck.")
            if not quiet:
                print("Sending transaction of {} coins to burn or AT gateway address: {}".format(str(amount), address))

            currentblock = provider.getblockcount()
            if deck.endblock is not None and currentblock >= deck.endblock:
                raise ei.PacliInputDataError("Token distribution has ended. Final deadline for burn or gateway transactions of this token was block {}.".format(deck.endblock))
            elif deck.startblock is not None and currentblock < (deck.startblock - 1):
                raise ei.PacliInputDataError("Token distribution has not started yet. Start deadline for burn or gateway transactions of this token is block {}.".format(deck.startblock))

            min_token_amount = Decimal(str(10 ** -deck.number_of_decimals))

            if deck.number_of_decimals >= 30:
                if not quiet:
                    print("Optimization not possible, token has too many decimal places.")

            elif (amount % min_token_amount) > 0:
                optimized_amount = (amount // min_token_amount) * min_token_amount
                if not quiet:
                    print("NOTE: The original amount will not lead to an optimal reward.")

                if optimize:
                    if not quiet:
                        print("Optimized amount as chosen with the '--optimize' flag, reducing the amount slightly from {} to {}".format(amount, optimized_amount))
                    amount = optimized_amount

                elif force:
                    if not quiet:
                        print("Continuing transaction as originally planned, as chosen with the '--force' flag, with {} coins.".format(amount))
                else:
                    if not quiet:
                        print("Aborting as no flag was selected for this situation.")
                        print("If you want to optimize the amount, select the '--optimize' flag, if you prefer the original amount use '--force'.")
                    return

        else:
            if (not force) and (not quiet) and (address_or_deck != au.burn_address()):
                print("WARNING: If you send the coins directly to a gateway address, then possible incompatibilities (e.g. deadlines) will not be checked.")
                print("Consider using the token ID or label/name as first argument instead.")
                raise ei.PacliInputDataError("Rejected transaction creation. If you want to create the transaction anyway, use the --force option.")

            address = ec.process_address(address_or_deck)


        change_address = ec.process_address(change)
        dec_amount = Decimal(str(amount))

        rawtx = au.create_simple_transaction(amount=dec_amount, dest_address=address, tx_fee=tx_fee, change_address=change_address, debug=debug)

        return eu.finalize_tx(rawtx, verify, sign, send, confirm=wait_for_confirmation, quiet=quiet, ignore_checkpoint=force, debug=debug)


    def claim(self, idstr: str, txid: str, receivers: list=None, amounts: list=None,
              payto: str=None, payamount: str=None, change: str=Settings.change,
              wait_for_confirmation: bool=False, quiet: bool=False, force: bool=False,
              verify: bool=False, sign: bool=True, send: bool=True, debug: bool=False) -> str:
        '''Claims the token reward for a burn transaction (PoB tokens) or a transaction to a tracked address (AT tokens) referenced by a transaction ID.

        Usage options:

        pacli [pobtoken|attoken] claim DECK TXID

        Claim the tokens and store them on the current main address, which has to be the sender of the rewarded transaction.
        TXID is the transaction ID to reference the rewarded transaction (e.g. burn transaction, donation or ICO payment).

        pacli [pobtoken|attoken] claim DECK TXID --payto=ADDRESS [--payamount=AMOUNT]

        Claim the tokens and make a payment with the issued tokens in the same transaction to one specific address.
        If --payamount is not provided, the whole amount will be sent to the address specified after --payto.

        pacli [pobtoken|attoken] claim DECK TXID -r "[ADDR1, ADDR2, ...]" -a "[AM1, AM2, ...]"

        Claim the tokens and make a payment with the issued tokens to multiple receivers.
        The lists must be put between brackets and quotes.
        The amount list lenght must be exactly as long as the address list.

        Args:

          tx_fee: Specify a transaction fee.
          change: Specify a change address.
          sign: Sign the transaction (True by default).
          send: Send the transaction (True by default).
          wait_for_confirmation: Wait and display a message until the transaction is confirmed.
          verify: Verify transaction with Cointoolkit (Peercoin only).
          payto: Pay to a single address (see above).
          payamount: Pay a single amount (see above).
          amounts: List of amounts (see above) to be paid to multiple receivers.
          receivers: List of receivers (see above).
          quiet: Suppress output and print it out in a script-friendly way.
          debug: Show additional debug information.
          force: Create the transaction even if the reward does not match the transaction or the reorg check fails (be careful!).'''

        kwargs = locals()
        del kwargs["self"]
        ei.run_command(self.__claim, **kwargs)


    def __claim(self, idstr: str, txid: str, receivers: list=None, amounts: list=None,
              payto: str=None, payamount: str=None, change: str=Settings.change,
              wait_for_confirmation: bool=False, quiet: bool=False, force: bool=False,
              verify: bool=False, sign: bool=True, send: bool=True, debug: bool=False) -> str:

        ke.check_main_address_lock()
        if payto is not None:
            payto = ec.process_address(payto)
            dec_payamount = Decimal(str(payamount)) if payamount is not None else None
        elif payamount is not None:
            raise ei.PacliInputDataError("Use --payamount together with --payto to designate a receiver of the payment.\nNo transaction was created.")
        else:
            dec_payamount = None

        if receivers:
            receiver_list = []
            for receiver in receivers:
                try:
                    receiver_list.append(ec.process_address(receiver))
                except:
                    raise ei.PacliInputDataError("Receiver invalid: {}".format(receiver))
        else:
            receiver_list = None


        deckid = eu.search_for_stored_tx_label("deck", idstr)
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

        change_address = ec.process_address(change)

        asset_specific_data, amount, receiver = au.create_at_issuance_data(deck, txid, Settings.key.address, amounts=amounts, receivers=receiver_list, payto=payto, payamount=dec_payamount, debug=debug, force=force)

        return eu.advanced_card_transfer(deck,
                                 amount=amount,
                                 receiver=receiver,
                                 change_address=change_address,
                                 asset_specific_data=asset_specific_data,
                                 sign=sign,
                                 send=send,
                                 force=force,
                                 verify=verify,
                                 confirm=wait_for_confirmation,
                                 debug=debug
                                 )

    @classmethod
    def spawn(self, token_name: str, address: str, multiplier: int=1, number_of_decimals: int=2, from_block: int=None,
              end_block: int=None, xtradata: str=None, change: str=Settings.change, verify: bool=False, ignore_warnings: bool=False,
              wait_for_confirmation: bool=False, sha256: bool=False, sign: bool=True, send: bool=True, debug: bool=False) -> None:
        """Spawns a new AT deck.

        Usage:

        pacli attoken spawn TOKEN_NAME TRACKED_ADDRESS

        Args:

          multiplier: Specify an integer multiplier for the reward (token metadata, defaults to 1).
          number_of_decimals: Specify the number of decimals of the token (token metadata, defaults to 2).
          from_block: Specify a start block to track transactions from (token metadata, optional).
          end_block: Specify an end block to track transactions (token metadata, optional).
          xtradata: Specify additional data (like a contract hash) (token metadata, optional).
          tx_fee: Specify a transaction fee.
          change: Specify a change address.
          sha256: Hash the xtradata data with sha256 (only in combination with -x).
          ignore_warnings: Ignore all warnings (reorg check etc.) and create transaction anyway (be careful!).
          sign: Sign the transaction (True by default).
          send: Send the transaction (True by default).
          wait_for_confirmation: Wait and display a message until the transaction is confirmed.
          verify: Verify transaction with Cointoolkit (Peercoin only)."""


        ke.check_main_address_lock()
        tracked_address = ei.run_command(ec.process_address, address, debug=debug)
        change_address = ei.run_command(ec.process_address, change, debug=debug)
        if sha256:
            s256hash = hashlib.sha256()
            s256hash.update(xtradata.encode())
            xd_bytes = s256hash.digest()
            if debug:
                print("Hashing data:", xtradata)
                print("SHA256 hash:", xd_bytes, "Hex:", s256hash.hexdigest())
        else:
            xd_bytes = xtradata.encode()

        asset_specific_data = ei.run_command(eu.create_deckspawn_data, c.ID_AT, at_address=tracked_address, multiplier=multiplier, startblock=from_block, endblock=end_block, extradata=xd_bytes, debug=debug)

        return ei.run_command(eu.advanced_deck_spawn, name=token_name, number_of_decimals=number_of_decimals,
               issue_mode=0x01, change_address=change_address, asset_specific_data=asset_specific_data,
               confirm=wait_for_confirmation, force=ignore_warnings, verify=verify, sign=sign, send=send, debug=debug)

    def check_claim(self, idstr: str, txid: str, quiet: bool=False, debug: bool=False):
        """Shows an AT or PoB claim transaction's contents.

        Usage:

            pacli attoken|pobtoken check_claim TOKEN TXID

        Args:

            quiet: Only check transaction with minimal output, suppress printouts.
            debug: Show additional debug information."""

        deck = ei.run_command(eu.search_for_stored_tx_label, "deck", idstr, return_deck=True, debug=debug)
        return ei.run_command(eu.get_claim_tx, txid, deck, quiet=quiet, debug=debug)

class ATToken(ATTokenBase):

    """Commands to deal with AT (address-tracking) tokens, which can be used for crowdfunding, trustless ICOs and similar purposes."""

    def send_coins(self, address_or_deck: str, amount: str, tx_fee: Decimal=None, change: str=Settings.change, sign: bool=True, send: bool=True, wait_for_confirmation: bool=False, verify: bool=False, quiet: bool=False, debug: bool=False, force: bool=False, optimize: bool=False) -> str:
        '''Creates a simple transaction from an address (default: current main address) to another one.
        The purpose of this command is to be able to use the address labels from Pacli,
        above all to make fast transactions to a tracked address of an AT token.

        Usage modes:

           pacli attoken create_tx TOKEN AMOUNT

        Send coins to the gateway (e.g. donation, investment) address of token (deck) TOKEN.

           pacli attoken create_tx ADDRESS AMOUNT

        Send coins to the gateway address ADDRESS.
        This should be considered an advanced mode. It will not check compatibility of deadlines.

        Args:

          tx_fee: Specify a transaction fee.
          change: Specify a change address.
          sign: Sign the transaction (True by default).
          send: Send the transaction (True by default).
          wait_for_confirmation: Wait and display a message until the transaction is confirmed.
          verify: Verify transaction with Cointoolkit (Peercoin only).
          quiet: Suppress output and print it out in a script-friendly way.
          debug: Show additional debug information.
          address_or_deck: To be used as a positional argument (flag name not necessary).
          amount: To be used as a positional argument (flag name not necessary).
          optimize: If used with a TOKEN, optimize amount sent to the gateway address if this leads to a better reward/investment ratio.
          force: Create the transaction in all cases with the chosen parameters, even if the amount is not optimal or no compatibility check (e.g. deadlines) can be performed.'''

        return ei.run_command(super()._create_tx, address_or_deck=address_or_deck, amount=amount, tx_fee=tx_fee, change=change, sign=sign, send=send, wait_for_confirmation=wait_for_confirmation, verify=verify, quiet=quiet, debug=debug, force=force, optimize=optimize)


class PoBToken(ATTokenBase):

    """Commands to deal with PoB (proof-of-burn) tokens, which reward burn transactions."""

    def spawn(self, token_name, multiplier: int=1, number_of_decimals: int=2, from_block: int=None,
              end_block: int=None, change: str=Settings.change, verify: bool=False, sign: bool=True,
              wait_for_confirmation: bool=False, send: bool=True, debug: bool=False):

        """Spawn a new PoB token, uses automatically the burn address of the network.

        Usage:

        pacli pobtoken spawn NAME

        Args:

          multiplier: Specify an integer multiplier for the reward..
          number_of_decimals: Specify the number of decimals of the token.
          from_block: Specify a start block to track transactions from.
          end_block: Specify an end block to track transactions.
          tx_fee: Specify a transaction fee.
          change: Specify a change address.
          sign: Sign the transaction (True by default).
          send: Send the transaction (True by default).
          wait_for_confirmation: Wait and display a message until the transaction is confirmed.
          verify: Verify transaction with Cointoolkit (Peercoin only)."""

        tracked_address = au.burn_address()
        print("Using burn address:", tracked_address)

        return super().spawn(token_name, tracked_address, multiplier, number_of_decimals, change=change, from_block=from_block, end_block=end_block, wait_for_confirmation=wait_for_confirmation, verify=verify, sign=sign, send=send, debug=debug)


    def burn_coins(self, amount: str, idstr: str=None, tx_fee: Decimal=None, change: str=Settings.change, wait_for_confirmation: bool=False, optimize: bool=False, force: bool=False, sign: bool=True, send: bool=True, verify: bool=False, quiet: bool=False, debug: bool=False) -> str:
        """Burn coins with a controlled transaction from the current main address.

        Usage modes:

            pacli pobtoken burn_coins AMOUNT

        Burns coins. Does not check deadlines or compatibility of any tokens.

            pacli pobtoken burn_coins AMOUNT -i TOKEN

        Burns coins checking for compatibility (e.g. deadlines) with token (deck) TOKEN.

        Args:

          idstr: ID of the token (deck) you want to check compatibility with.
          tx_fee: Specify a transaction fee.
          change: Specify a change address.
          sign: Sign the transaction (True by default).
          send: Send the transaction (True by default).
          wait_for_confirmation: Wait and display a message until the transaction is confirmed.
          verify: Verify transaction with Cointoolkit (Peercoin only).
          optimize: If used with a TOKEN, reduce amount set to the burn address if this leads to a better reward/investment ratio.
          force: Create the transaction in all cases with the chosen parameters, even if the amount is not optimal or no compatibility check (e.g. deadlines) can be performed.
          quiet: Suppress output and print it out in a script-friendly way.
          debug: Show additional debug information."""


        if idstr is None:
            return ei.run_command(super()._create_tx, address_or_deck=au.burn_address(), amount=amount, tx_fee=tx_fee, change=change, sign=sign, send=send, wait_for_confirmation=wait_for_confirmation, verify=verify, force=force, quiet=quiet, debug=debug)
        else:
            return ei.run_command(super()._create_tx, address_or_deck=idstr, amount=amount, tx_fee=tx_fee, change=change, sign=sign, send=send, wait_for_confirmation=wait_for_confirmation, verify=verify, force=force, optimize=optimize, quiet=quiet, debug=debug)
