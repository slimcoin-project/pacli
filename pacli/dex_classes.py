import time
import pacli.dex_utils as dxu
import pacli.extended_interface as ei
import pacli.extended_utils as eu
import pypeerassets as pa
import pacli.extended_commands as ec
import pacli.config_extended as ce
import pacli.keystore_extended as ke
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
            lockaddr: str,
            lock: int=1000,
            blockheight: bool=False,
            addrtype: str="p2pkh",
            change: str=None,
            new_origin: str=None,
            force: bool=False,
            wait_for_confirmation: bool=False,
            sign: bool=True,
            send: bool=True,
            quiet: bool=False,
            debug: bool=False):
        """Locks a number of tokens on the receiving address.
        Transfers are only permitted to the Lock Address. This is the condition to avoid scams in the swap DEX.
        The lock is a token transaction, where the default receiver is the sender (the current main address).
        If the -n option is used, the tokens will be sent to a new address (NEW_ORIGIN) and locked after that process. This is only recommended with your own addresses, and the NEW_ORIGIN address becomes the one where you have to initiate a swap from.
        NOTE: The token buyer, by default, will reject swaps where the tokens are not locked for at least 100 blocks, counted from the moment they run the command to finalize the swap. 'swap create' will also reject locks under 100 blocks, so make sure you have time to run this command.
        For these reasons, it is recommended to choose a much higher locktime, e.g. 1000 blocks (the default).

        Usage modes:

            pacli swap lock TOKEN TOKEN_AMOUNT LOCK_ADDRESS [LOCK_BLOCKS] [-n NEW_ORIGIN]

        By default, you specify the relative number of blocks (counted from the current block height) to lock the tokens (default: 1000).

            pacli swap lock TOKEN TOKEN_AMOUNT LOCK_ADDRESS [BLOCKHEIGHT] [-n NEW_ORIGIN] -b

        Using -b/--blockheight, the third positional argument indicates the absolute block height.

        Args:

          sign: Sign the transaction.
          send: Send the transaction.
          blockheight: Lock to an absolute block height (instead of a relative number of blocks).
          new_origin: Send the tokens to a new origin address while locking the tokens (can be only one). NOTE: DO NOT confuse this address with the lock address! The new_origin address will be the full owner of the tokens after the lock expires!
          addrtype: Address type (default: p2pkh)
          change: Specify a custom change address.
          wait_for_confirmation: Wait for the first confirmation of the transaction and display a message.
          force: Create transaction even if the reorg check fails. Does not check balance (faster, but use with caution).
          quiet: Output only the transaction in hexstring format (script-friendly).
          debug: Show additional debug information.
         """

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", idstr, quiet=quiet, debug=debug)
        change_address = ei.run_command(ec.process_address, change, debug=debug)
        lock_address = ei.run_command(ec.process_address, lockaddr, debug=debug)

        return ei.run_command(dxu.card_lock, deckid=deckid, amount=str(amount), lock=lock, lockaddr=lock_address, addrtype=addrtype, absolute=blockheight, change=change_address, receiver=new_origin, sign=sign, send=send, force=force, confirm=wait_for_confirmation, txhex=quiet, debug=debug)

    @classmethod
    def create(self,
                 token: str,
                 partner_address: str,
                 partner_input: str,
                 amount_cards: str,
                 amount_coins: str,
                 buyer_change_address: str=None,
                 change_address: str=None,
                 label: str=None,
                 with_lock: int=None,
                 forcelock: bool=False,
                 quiet: bool=False,
                 no_checks: bool=False,
                 sign: bool=True,
                 debug: bool=False):
        """Creates a new swap transaction, signs it partially and outputs it in hex format to be submitted to the exchange partner.

        Usage:

            pacli swap create TOKEN PARTNER_ADDRESS PARTNER_INPUT TOKEN_AMOUNT COIN_AMOUNT

        Creates a swap only. PARTNER_ADDRESS and PARTNER_INPUT come from your exchange partner (see manual). PARTNER_ADDRESS can be an address or a label of a stored address.
        PARTNER_INPUT must be in the format TXID:OUTPUT, or be a valid label for a stored UTXO.

            pacli swap create TOKEN PARTNER_ADDRESS PARTNER_INPUT TOKEN_AMOUNT COIN_AMOUNT -w [LOCKTIME]

        Creates the swap and adds a lock transaction, which will by default lock the tokens 1000 blocks to the PARTNER_ADDRESS and use common default values. If you need more parameters for the lock process, use the 'swap lock' command and then the 'swap create' command without the '-w' flag.

        NOTES:
        - To pay the transaction fees, you need coins on your address which don't come directly from mining (coinbase inputs can't be used due to an upstream bug). It will work if you transfer mined coins in a regular transaction to the address you will be using for the swap.
        - If you provide a custom change address with -c, it will be used both for the locking transaction and the swap transaction. Privacy loss of this behavior is negligible as both transactions will be "linked together" anyway (due to the origin addresses being also the same), but to generate new change addresses for each transaction you can change the default change address policy with 'pacli config set newaddress -s' and use the command without the -c parameter.
        - The -w option requires additional coins on the origin address to be used for fees (0.05 in Slimcoin, 0.01 or 0.02 [depending on change policy] of them will return to the origin address).

        Args:

          sign: Sign the transaction.
          buyer_change_address: Specify a change address of the token buyer (default: sender address). Can be the address itself or a label of a stored address.
          label: Specify a label to save the transaction hex string with.
          with_lock: Lock the required tokens to the PARTNER_ADDRESS. A locktime (in blocks, minimum: 100) can be added, default is 1000.
          change_address: Change address for the remaining coins. If -w is used, it will also be used for the locking transaction (see Usage section how to prevent that).
          forcelock: Run the lock transaction even if an error is shown (only in combination with -w).
          no_checks: Skip the token balance and lock checks (faster). WARNING: This may result in an invalid swap!
          quiet: Suppress output.
          debug: Show additional debug information.
        """
        partner_address = ei.run_command(ec.process_address, partner_address, debug=debug)
        buyer_change_address = ei.run_command(ec.process_address, buyer_change_address, debug=debug) if buyer_change_address is not None else None
        change_address = ei.run_command(ec.process_address, change_address, debug=debug)
        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", token, quiet=quiet)
        if with_lock is not None:
             locktime = with_lock if type(with_lock) == int else 1000
             lock_tx = ei.run_command(dxu.card_lock, lock=locktime, deckid=deckid, amount=str(amount_cards), lockaddr=partner_address, addrtype="p2pkh", change=change_address, sign=True, send=True, confirm=False, txhex=quiet, return_txid=True, debug=debug, force=forcelock)
        else:
             lock_tx = None
        return ei.run_command(dxu.build_coin2card_exchange, deckid, partner_address, partner_input, Decimal(str(amount_cards)), Decimal(str(amount_coins)), sign=sign, change=change_address, tokenbuyer_change_address=buyer_change_address, without_checks=no_checks, save_identifier=label, lock_tx=lock_tx, debug=debug)

    def finalize(self,
                 ftxstr: str,
                 id_deck: str=None,
                 expected_tokens: str=None,
                 payment: str=None,
                 send: bool=False,
                 force: bool=False,
                 wait_for_confirmation: bool=False,
                 txhex: bool=False,
                 quiet: bool=False,
                 debug: bool=False):
        """Signs and broadcasts an exchange transaction.

        Usage:

            pacli swap finalize TX_HEXSTRING TOKEN EXPECTED_TOKENS PAYMENT [--send]

        TX_HEXSTRING is the partially signed transaction in the format of an hex string.
        TOKEN can be a label or a token (deck) ID. Mandatory for a safe swap.
        EXPECTED_TOKENS is the expected amount of tokens to acquire, PAYMENT the coins expected to be paid.
        Check first if everything is correct with a dry run, then add --send to broadcast transaction.
        Note: Before launching this command, be sure to change the Pacli main address to the address providing the coins to be able to sign the transaction. This is often, but not necessarily the same address where you'll receive the tokens, depending on which UTXO you provided to the token seller.
        Note 2: If the transaction doesn't broadcast correctly or doesn't confirm, it is possible that one of its inputs was already spent. Use 'pacli transaction show TXHEX -u' with the whole hex string to see if this is the case, and if yes, contact your counterparty to repeat the swap process.

        Args:

          send: Sends the transaction (by default set to False).
          id_deck: Token (deck) to conduct the swap.
          expected_tokens: Token units expected to get transferred in the swap.
          payment: The coins expected to be paid for the tokens.
          wait_for_confirmation: Waits for the transaction to confirm.
          force: Creates the transaction even if the checks fail. Only recommended for expert users. May create invalid transactions. WARNING: Use with caution, do not use if the token seller insists on it as it can lead to coin/token loss!
          txhex: Shows only the hex string of the transaction.
          quiet: Suppresses some printouts (with the exception of the --force warning).
          debug: Show additional debug information.
        """

        kwargs = locals()
        del kwargs["self"]
        return ei.run_command(self.__finalize, **kwargs)

    def __finalize(self,
                   ftxstr: str,
                   id_deck: str=None,
                   expected_tokens: str=None,
                   payment: str=None,
                   send: bool=False,
                   force: bool=False,
                   wait_for_confirmation: bool=False,
                   txhex: bool=False,
                   quiet: bool=False,
                   debug: bool=False):

        txhexstr = ce.show("transaction", ftxstr, quiet=True)
        if txhexstr is None:
            txhexstr = ftxstr

        if force:
            print("WARNING: --force option used. Do only proceed if you REALLY know what your are doing.")
            print("NEVER use this option if your swap counterparty (the token seller) insists on using it.")
            print("You have 20 seconds to abort the exchange with a keyboard interruption (e.g. CTRL-C or CTRL-D depending on the operating system) or closing the terminal window.")
            time.sleep(20)
        else:
            if None in (id_deck, expected_tokens, payment):
                raise ei.PacliInputDataError("Not all required parameters provided. For a safe swap, you have to provide the name or Deck ID of the token, the expected tokens to be transferred, and the expected payment (in coins).")
            fail = ei.run_command(self.__check, txhexstr, return_state=True, token=id_deck, token_amount=expected_tokens, amount=payment, presign_check=True, require_amounts=True, utxo_check=True, debug=debug)
            if fail is True:
                raise ei.PacliDataError("Swap check failed. It is either not possible to continue or highly recommended to NOT proceed with the exchange. If you are REALLY sure everything is correct and you will receive the tokens (and the change of the coins you paid) on addresses you own, use --force. Do NOT use the --force option if you have the slightest doubt the token seller may trick you into a fraudulent swap.")
        return ei.run_command(dxu.finalize_coin2card_exchange, txhexstr, send=send, force=force, confirm=wait_for_confirmation, quiet=quiet, txhex=txhex, debug=debug)

    @classmethod
    def list_locks(self, idstr: str, blockheight: int=None, quiet: bool=False, debug: bool=False):
        """Shows all current locks of a token (deck).

        Usage:

            pacli swap list_locks TOKEN

        Args:

          blockheight: Specify a block height to show locks at. To be used as a positional argument (flag name not necessary).
          quiet: Don't prettyprint the lock dictionary and suppress additional output.
          debug: Show debug information.
        """

        blockheight = provider.getblockcount() if blockheight is None else blockheight
        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", idstr, quiet=quiet)
        locks, deck = ei.run_command(dxu.get_locks, deckid, blockheight, return_deck=True, debug=debug)

        if quiet is True:
            return locks
        else:
            return ei.run_command(dxu.prettyprint_locks, locks, blockheight, decimals=deck.number_of_decimals)

    @classmethod
    def select_coins(self, amount: int=0, address: str=None, wallet: bool=False, utxo_type="pubkeyhash", fees: bool=False, debug: bool=False):
        """Prints out all suitable utxos for an exchange transaction.

        Usage:

            pacli swap select_coins [AMOUNT] [-w] [-f]
            pacli swap select_coins AMOUNT ADDRESS [-f]

        If ADDRESS is not given, the current main address is used.
        AMOUNT default value is 0, i.e. if no amount is given all matching UTXOs will be shown. If ADDRESS is given, an amount has to be given too.
        Using the -w flag instead of an address searches UTXOs in the whole wallet.
        Use the -f flag to calculate all swap fees and search for UTXOs with an amount of coins including these.
        NOTE: due to an upstream bug, coinbase UTXOs can't be used for swaps. They will be ignored by this command.

        Args:

          address: Alternative address to show suitable UTXOs instead of the main address. To be used as a positional argument (flag name not necessary).
          fees: Calculate all necessary fees and add them to the amount.
          utxo_type: Specify a different UTXO type (default: pubkeyhash)
          wallet: Search UTXOs in all addresses of the wallet.
          debug: Show additional debug information.
        """

        # addr = None if wallet is True else ei.run_command(ec.process_address, address, debug=debug)
        kwargs = locals()
        del kwargs["self"]
        return ei.run_command(self.__select_coins, **kwargs)


    def __select_coins(amount: int=0, address: str=None, wallet: bool=False, utxo_type="pubkeyhash", fees: bool=False, debug: bool=False):
        if wallet is True:
            addr = None
        elif address is None:
            addr = ke.get_main_address()
        else:
            addr = ec.process_address(address, debug=debug)
        return dxu.select_utxos(minvalue=Decimal(str(amount)), address=addr, utxo_type=utxo_type, fees=fees, show_address=wallet, debug=debug)

    def check(self,
              _txstring: str,
              token: str=None,
              change_address: str=None,
              buyer_address: str=None,
              amount_coins: str=None,
              units_token: str=None,
              presign_check: bool=False,
              debug: bool=False):
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
          presign_check: Check if the current main address is able to sign the transaction.
          units_token: Amount of tokens to receive for the coins.
          debug: Show additional debug information.
        """
        #TODO: swap check still has bug: if no change output is added, it will raise an error.

        ei.run_command(self.__check, _txstring,
                       buyer_change_address=change_address,
                       token_receiver_address=buyer_address,
                       token=token,
                       amount=amount_coins,
                       token_amount=units_token,
                       presign_check=presign_check,
                       debug=debug
                       )

    def __check(self,
                _txstring: str,
                token: str=None,
                buyer_change_address: str=None,
                token_receiver_address: str=None,
                amount: str=None,
                token_amount: str=None,
                return_state: bool=False,
                presign_check: bool=False,
                utxo_check: bool=False,
                require_amounts: bool=False,
                debug: bool=False):

        deckid = None if token is None else eu.search_for_stored_tx_label("deck", token, debug=debug)
        if require_amounts is True and (None in (token_amount, amount)):
            raise ei.PacliInputDataError("Both the expected payment in coins and the expected token amount have to be provided for a safe swap check.")
        txhex = ce.show("transaction", _txstring, quiet=True)
        if txhex is None:
            txhex = _txstring

        return dxu.check_swap(txhex,
               deckid=deckid,
               buyer_change_address=buyer_change_address,
               token_receiver_address=token_receiver_address,
               amount=amount,
               token_amount=token_amount,
               return_state=return_state,
               presign_check=presign_check,
               utxo_check=utxo_check,
               debug=debug)
