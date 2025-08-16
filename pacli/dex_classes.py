import time
import pacli.dex_utils as dxu
import pacli.blockexp_utils as bxu
import pacli.extended_interface as ei
import pacli.extended_utils as eu
import pypeerassets as pa
import pacli.extended_commands as ec
import pacli.config_extended as ce
from decimal import Decimal
from prettyprinter import cpprint as pprint
from pacli.provider import provider
from pacli.config import Settings


class Swap:
    """Commands allowing the decentralized exchange of tokens for coins."""

    @classmethod
    def lock(self,
            idstr: str,
            amount: str,
            lock: int,
            lockaddr: str,
            receiver: str=None,
            blockheight: bool=False,
            addrtype: str="p2pkh",
            change: str=Settings.change,
            force: bool=False,
            wait_for_confirmation: bool=False,
            sign: bool=True,
            send: bool=True,
            quiet: bool=False,
            debug: bool=False):
        """Locks a number of tokens on the receiving address.
        Transfers are only permitted to the Lock Address. This is the condition to avoid scams in the swap DEX.
        Card default receiver is the sender (the current main address).
        If -r option is used, the cards instead will be sent to the address specified behind that flag. This address becomes the one where you have to initiate a swap from.

        Usage modes:

            pacli swap lock TOKEN TOKEN_AMOUNT LOCK_BLOCKS LOCK_ADDRESS [RECEIVER]

        By default, you specify the relative number of blocks (counted from the current block height) to lock the tokens.

            pacli swap lock TOKEN TOKEN_AMOUNT BLOCKHEIGHT LOCK_ADDRESS [RECEIVER] -b

        Using -b/--blockheight, the third positional argument indicates the absolute block height.

        Args:

          sign: Sign the transaction.
          send: Send the transaction.
          blockheight: Lock to an absolute block height (instead of a relative number of blocks).
          receiver: Specify a receiver for the tokens (can be only one).
          addrtype: Address type (default: p2pkh)
          change: Specify a custom change address.
          wait_for_confirmation: Wait for the first confirmation of the transaction and display a message.
          force: Create transaction even if the reorg check fails. Does not check balance (faster, but use with caution).
          quiet: Output only the transaction in hexstring format (script-friendly).
          debug: Show additional debug information.
         """

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", idstr, quiet=quiet, debug=debug)
        change_address = ec.process_address(change, debug=debug)
        lock_address = ec.process_address(lockaddr, debug=debug)
        if receiver is None:
            receiver_address = Settings.key.address
        else:
            receiver_address = ec.process_address(receiver)
        return ei.run_command(dxu.card_lock, deckid=deckid, amount=str(amount), lock=lock, lockaddr=lock_address, addrtype=addrtype, absolute=blockheight, change=change_address, receiver=receiver_address, sign=sign, send=send, force=force, confirm=wait_for_confirmation, txhex=quiet, debug=debug)

    @classmethod
    def create(self,
                 token: str,
                 partner_address: str,
                 partner_input: str,
                 amount_cards: str,
                 amount_coins: str,
                 buyer_change_address: str=None,
                 label: str=None,
                 quiet: bool=False,
                 sign: bool=True,
                 debug: bool=False):
        """Creates a new exchange transaction, signs it partially and outputs it in hex format to be submitted to the exchange partner.

        Usage:

            pacli swap create DECK PARTNER_ADDRESS PARTNER_INPUT TOKEN_AMOUNT COIN_AMOUNT

        PARTNER_ADDRESS and PARTNER_INPUT come from your exchange partner (see manual). PARTNER_ADDRESS can be an address or a label of a stored address.
        NOTE: To pay the transaction fees, you need coins on your address which don't come directly from mining (coinbase inputs can't be used due to an upstream bug). It will work if you transfer mined coins in a regular transaction to the address you will be using for the swap.

        Args:

          sign: Sign the transaction.
          buyer_change_address: Specify a change address of the token buyer (default: sender address). Can be the address itself or a label of a stored address.
          label: Specify a label to save the transaction hex string with.
          quiet: Suppress output.
          debug: Show additional debug information.
        """

        partner_address = ei.run_command(ec.process_address, partner_address, debug=debug)
        buyer_change_address = ei.run_command(ec.process_address, buyer_change_address, debug=debug) if buyer_change_address is not None else None
        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", token, quiet=quiet)
        return ei.run_command(dxu.build_coin2card_exchange, deckid, partner_address, partner_input, Decimal(str(amount_cards)), Decimal(str(amount_coins)), sign=sign, coinseller_change_address=buyer_change_address, save_identifier=label, debug=debug)

    # @classmethod
    def finalize(self,
                 ftxstr: str,
                 id_deck: str=None,
                 units: str=None,
                 send: bool=False,
                 force: bool=False,
                 wait_for_confirmation: bool=False,
                 txhex: bool=False,
                 quiet: bool=False,
                 debug: bool=False):
        """Signs and broadcasts an exchange transaction.

        Usage:

            pacli swap finalize TX_HEXSTRING TOKEN UNITS [--send]

        TX_HEXSTRING is the partially signed transaction in the format of an hex string.
        TOKEN can be a label or a token (deck) ID. Mandatory for a safe swap.
        UNITS is the expected amount of tokens.
        Check first if everything is correct with a dry run, then add --send to broadcast transaction.

        Args:

          send: Sends the transaction (by default set to False).
          id_deck: Token (deck) to conduct the swap.
          units: Token units expected in the swap.
          wait_for_confirmation: Waits for the transaction to confirm.
          force: Creates the transaction even if the checks fail. WARNING: Use with caution, do not use if the token seller insists on it as it can lead to coin/token loss!
          txhex: Shows only the hex string of the transaction.
          quiet: Suppresses some printouts (with the exception of the --force warning).
          debug: Show additional debug information.
        """

        kwargs = locals()
        del kwargs["self"]
        return ei.run_command(self.__finalize, **kwargs)

    def __finalize(self, ftxstr: str, id_deck: str=None, units: str=None, send: bool=False, force: bool=False, wait_for_confirmation: bool=False, txhex: bool=False, quiet: bool=False, debug: bool=False):

        txhexstr = ce.show("transaction", ftxstr, quiet=True)
        if txhexstr is None:
            txhexstr = ftxstr

        if force:
            print("WARNING: --force option used. Do only proceed if you REALLY know what your are doing.")
            print("NEVER use this option if your swap counterparty (the token seller) insists on using it.")
            print("You have 20 seconds to abort the exchange with a keyboard interruption (e.g. CTRL-C or CTRL-D depending on the operating system) or close the terminal window.")
            time.sleep(20)
        else:
            if id_deck is None:
                raise ei.PacliInputDataError("No deck provided. Deck check is mandatory.")
            if units is None:
                raise ei.PacliInputDataError("Number of expected token units not provided. Mandatory for a safe swap.")
            fail = ei.run_command(self.__check, txhexstr, return_state=True, deckstr=id_deck, token_amount=units, debug=debug)
            if fail is True:
                raise ei.PacliDataError("Swap check failed. It is advised to NOT proceed with the exchange. If you are REALLY sure everything is correct and you will receive the tokens (and eventually the change of the coins you paid) on an address you own, use --force. Do NOT use the --force option if you have the slightest doubt the token seller may trick you into a fraudulent swap.")
        return ei.run_command(dxu.finalize_coin2card_exchange, txhexstr, send=send, force=force, confirm=wait_for_confirmation, quiet=quiet, txhex=txhex, debug=debug)

    @classmethod
    def list_locks(self, idstr: str, blockheight: int=None, quiet: bool=False, debug: bool=False):
        """Shows all current locks of a deck.

        Usage:

            pacli swap list_locks DECK

        Args:

          blockheight: Specify a block height to show locks at (BUGGY). To be used as a positional argument (flag name not necessary).
          quiet: Don't prettyprint the lock dictionary and suppress additional output.
          debug: Show debug information.
        """
        # TODO: blockheight seems not to work.

        blockheight = provider.getblockcount() if blockheight is None else blockheight
        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", idstr, quiet=quiet)
        locks = dxu.get_locks(deckid, blockheight, debug=debug)
        #deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        #cards = pa.find_all_valid_cards(dxu.provider, deck)
        #state = pa.protocol.DeckState(cards, cleanup_height=blockheight, debug=debug)

        if quiet is True:
            return state.locks
        else:
            return dxu.prettyprint_locks(state.locks, blockheight, decimals=deck.number_of_decimals)

    @classmethod
    def select_coins(self, amount, address=Settings.key.address, wallet: bool=False, utxo_type="pubkeyhash", debug: bool=False):
        """Prints out all suitable utxos for an exchange transaction.

        Usage:

            pacli swap select_coins AMOUNT [ADDRESS|-w]

        If ADDRESS is not given, the current main address is used.
        Using the -w flag instead of an address searches UTXOs in the whole wallet.
        NOTE: due to an upstream bug, coinbase UTXOs can't be used for swaps. They will be ignored by this command.

        Args:

          address: Alternative address to show suitable UTXOs. To be used as a positional argument (flag name not necessary).
          utxo_type: Specify a different UTXO type (default: pubkeyhash)
          wallet: Search UTXOs in all addresses of the wallet.
          debug: Show additional debug information.
        """

        addr = None if wallet is True else ei.run_command(ec.process_address, address, debug=debug)
        return ei.run_command(dxu.select_utxos, minvalue=amount, address=addr, utxo_type=utxo_type, debug=debug)

    # @classmethod
    def check(self, _txstring: str, token: str=None, change_address: str=None, buyer_address: str=None, amount_coins: str=None, units_token: str=None, debug: bool=False):
        """Checks a swap transaction, allowing the token buyer to see if everything is correct.

        Usage:

            pacli swap check TRANSACTION

        TRANSACTION can be either the raw transactions' hex string (TXHEX) or the label of a stored transaction.
        If no more arguments are given, the transaction's inputs and outputs will be shown and basic checks will be performed.

        Args:

          buyer_address: The address provided by the token buyer to receive the coins.
          change_address: The (optional) address provided by the token buyer to receive the change.
          amount_coins: Amount of coins provided to buy the tokens.
          token: Label or ID of the token.
          units_token: Amount of tokens to receive for the coins.
          debug: Show additional debug information.
        """
        #TODO: swap check still has bug: if no change output is added, it will raise an error.

        ei.run_command(self.__check, _txstring,
                       buyer_change_address=change_address,
                       token_receiver_address=buyer_address,
                       deckstr=token,
                       amount=amount_coins,
                       token_amount=units_token,
                       debug=debug
                       )

    def __check(self, _txstring: str, deckstr: str=None, buyer_change_address: str=None, token_receiver_address: str=None, amount: str=None, token_amount: str=None, return_state: bool=False, debug: bool=False):

        deckid = eu.search_for_stored_tx_label("deck", deckstr, debug=debug)
        fail, notmine = False, False
        txhex = ce.show("transaction", _txstring, quiet=True)
        if txhex is None:
            txhex = _txstring
        try:
            txjson = provider.decoderawtransaction(txhex)
            txstruct = bxu.get_tx_structure(tx=txjson, ignore_blockhash=True)
        except:
            raise ei.PacliInputDataError("No valid transaction hex string or label provided.")

        print("Checking swap ...")
        pprint("Senders and receivers of the swap transaction:")
        pprint(txstruct)
        try:
            # Note: outputs 2 and 4 go to the token seller, so they aren't checked here in detail.
            token_seller = txstruct["inputs"][0]["sender"][0]
            token_buyer = txstruct["inputs"][1]["sender"][0]
            amount_provided = Decimal(str(txstruct["inputs"][1]["value"]))
            p2th_address = txstruct["outputs"][0]["receivers"][0]
            token_receiver = txstruct["outputs"][2]["receivers"][0] # was 3
            change_receiver = txstruct["outputs"][5]["receivers"][0]
            change_returned = Decimal(str(txstruct["outputs"][5]["value"]))
            all_inputs = sum([Decimal(str(i["value"])) for i in txstruct["inputs"]])
            all_outputs = sum([Decimal(str(o["value"])) for o in txstruct["outputs"]])
            tx_fee = all_inputs - all_outputs
            p2th_fee = Decimal(str(txstruct["outputs"][0]["value"]))

            op_return_fee = Decimal(str(txstruct["outputs"][1]["value"]))
            card_transfer_fee = Decimal(str(txstruct["outputs"][2]["value"]))

            all_fees = tx_fee + p2th_fee + op_return_fee + card_transfer_fee

            op_return_output = txjson["vout"][1]
        except (KeyError, IndexError):
            raise ei.PacliDataError("Incorrect transaction structure. Don't proceed with the transaction.")

        pprint("Token seller's address: {}".format(token_seller))
        pprint("Token buyer's address: {}".format(token_buyer))
        pprint("Token receiver's address: {}".format(token_receiver))
        if token_receiver != token_buyer:
            print("NOTE: The address providing the coins for the swap isn't identic to the address which will receive the tokens.")
            print("This may be intentionally set up by the token buyer, e.g. for privacy reasons.")
            print("If you are the token buyer, make sure the token receiver address {} belongs to you (will be checked in the ownership check).".format(token_receiver))

        if token_receiver_address is not None and (token_receiver != token_receiver_address):
            ei.print_red("The token receiver address you provided in this check isn't the address receiving the tokens in the swap transaction.")
            fail = True
        pprint("Change receiver's address: {}".format(change_receiver))
        pprint("Change returned: {}".format(change_returned))
        if buyer_change_address is not None and (change_receiver != buyer_change_address):
            ei.print_red("The change receiver address you provided in this check isn't the address receiving the change coins in the swap transaction.")
            fail = True
        pprint("Fees paid: {}".format(all_fees))
        paid_amount = amount_provided - change_returned - all_fees
        pprint("Amount paid for the tokens (not including fees): {}".format(paid_amount))
        if amount is not None:
            intended_amount = Decimal(str(amount))
            if intended_amount < paid_amount:
                ei.print_red("The token buyer didn't receive all the change or will pay more than expected.")
                ei.print_red("Missing amount: {}.".format(paid_amount - intended_amount))
                fail = True

        for adr in token_receiver, change_receiver:
            validation = provider.validateaddress(adr)
            if validation.get("ismine") != True:
                notmine = True
                fail = True
        if notmine is True:
            ei.print_red("Ownership check failed: At least one of the addresses which should be under the token buyer's control in this swap (token receiver and change receiver) isn't part of your current wallet.")
            print("This may be intentional if you provided an address of another wallet, or are using this command running the client with a different wallet than the swap's wallet, but can also be a manipulation by the token buyer.")
        else:
            print("Ownership check passed: Both the token receiver and the change address for the provided coins are part of your currently used wallet.")

        card_transfer = eu.decode_card(op_return_output)
        card_amount = card_transfer["amount"][0]
        decimals = card_transfer["number_of_decimals"]
        formatted_card_amount = Decimal(str(dxu.exponent_to_amount(card_amount, decimals)))
        if token_amount is not None:
            if formatted_card_amount != Decimal(str(token_amount)):
                fail = True
                ei.print_red("The number of tokens transferred is {}, while the expected token amount is {}.".format(formatted_card_amount, token_amount))
            else:
                print("Token transfer check passed: tokens transferred: {}, expected: {}.".format(formatted_card_amount, token_amount))

        print("Deck ID and lock check (may take some time) ....")
        matching_decks = eu.find_decks_by_address(p2th_address, addrtype="p2th_main", debug=False)
        deck = matching_decks[0]["deck"]
        if deck.id != deckid:
            fail = True
            ei.print_red("Transferred token is not the expected one. Expected token: {}, transferred token: {}.".format(deckid, deck.id))

        # lock check: tokens need to be locked until at least 100 blocks (default) in the future
        blockheight = provider.getblockcount()
        if not dxu.check_lock(deck, token_seller, token_receiver, token_amount, blockheight, limit=100, debug=debug):
            fail = True

        if return_state is True:
            return fail
        else:
            if fail is True:
                ei.print_red("SWAP CHECK FAILED. If you are the token buyer and see this or any red warning, it is advised to abandon the swap.")
            else:
                print("SWAP CHECK PASSED. If there is a warning, read it carefully to avoid any losses.")
