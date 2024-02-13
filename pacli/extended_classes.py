from typing import Optional, Union
import pypeerassets as pa
from prettyprinter import cpprint as pprint
from pprint import pprint as alt_pprint
import pypeerassets.at.dt_misc_utils as dmu
import pypeerassets.at.constants as c

import pacli.extended_constants as pc
import pacli.keystore_extended as ke
import pacli.extended_utils as eu
import pacli.at_utils as au
import pacli.extended_commands as ec
import pacli.config_extended as ce
import pacli.extended_interface as ei
import pacli.token_commands as tc
import pacli.dt_commands as dc
import pacli.blockexp as bx

from pacli.provider import provider
from pacli.config import Settings, default_conf, write_settings
from pacli.tui import print_deck_list, print_card_list

# extended_main contains extensions of the main pacli classes only
# It seems not possible without import conflicts to do it "cleaner"
# the other way around, i.e. defining the Ext.. classes as children
# of the __main__ classes. So it seems to be necessary to comment
# out the methods in __main__ if there's a conflict.

# NOTE: checkpoint functions went into own file (extended_checkpoints.py).


class ExtConfig:

    def set(self,
            label: str,
            value: Union[str, bool]=None,
            extended: str=None,
            delete: bool=False,
            modify: bool=False,
            replace: bool=False,
            now: bool=False,
            quiet: bool=False) -> None:
        """Changes configuration settings.

           Usage modes:

           pacli config set LABEL VALUE [-e/--extended CATEGORY]

           Adds a setting in the basic configuration file (by default: pacli.conf)
           or a category CATEGORY in the extended configuration file.

           pacli config set LABEL VALUE -r/--replace [-e/--extended CATEGORY]

           Replaces the value of LABEL in the basic configuration file or in a
           category CATEGORY of the extended configuration file.

           pacli config set LABEL -d/--delete [-e/--extended CATEGORY] [--now]

           Deletes a setting (by default: in the basic config file, with -e and -c in the extended config file).
           Use --now to really delete it, otherwise a dry run will be performed.

           pacli config set NEW_LABEL OLD_LABEL -m [-e/--extended CATEGORY]

           Modifies a label (OLD_LABEL gets replaced by NEW_LABEL).

           Args:

             extended: Use the extendid configuration file.
             replace: Replaces the value of a setting.
             modify: Modify the label of a setting.
             delete: Delete a setting.
             now: Really delete a setting, in combination with -d/--delete.
             quiet: Suppress output, printout in script-friendly way."""

        return ei.run_command(self.__set, label, value=value, category=extended, delete=delete, modify=modify, replace=replace, now=now, quiet=quiet)

    def __set(self,
              label: str,
              value: Union[str, bool]=None,
              category: str=None,
              delete: bool=False,
              modify: bool=False,
              replace: bool=False,
              now: bool=False,
              quiet: bool=False) -> None:

        if category is not None:
            if type(category) != str:
                # if -e is given without cat, it gets replaced by a bool value (True).
                raise ei.PacliInputDataError("You have to provide a category if modifying the extended config file.")
            else:
                if delete is True:
                    return ce.delete(category, label=str(label), now=now)
                else:
                    return ce.setcfg(category, label=label, value=value, modify=modify, replace=replace, quiet=quiet)
        else:
            if value is None:
                raise ei.PacliInputDataError("No value provided.")
            if label not in default_conf.keys():
                # raise ValueError({'error': 'Invalid setting key.'}) # ValueError added # this was mainly for compatibility.
                raise ei.PacliInputDataError("Invalid setting key. This key doesn't exist in the standard configuration file.")

            write_settings(label, value)


    def show(self,
             value_or_label: str,
             extended: str=None,
             label: bool=False,
             find: bool=False,
             quiet: bool=False):
        """Shows a setting in the basic or extended configuration file.

        Usage options:

        pacli config show LABEL

        Shows setting in the basic configuration file.

        pacli config show LABEL -e/--extended CATEGORY [options]

        Shows setting in a category CATEGORY of the extended configuration file.

        pacli config show VALUE -e/extended CATEGORY -f/--find
        pacli config show VALUE -e/extended CATEGORY -l/--label

        Searches a value and prints out existing labels for it (only in combination with -e/--extended).
        The -f/--find option allows to search for parts of the value string,
        while the -l/--label option only accepts exact matches (in analogy to 'address show --label').

        The CATEGORY value refers to a category in the extended config file.
        Get all categories with: `pacli config list -e -c`

        Other flags:

        -q, --quiet: Suppress output, printout in script-friendly way."""

        return ei.run_command(self.__show, value_or_label, category=extended, label=label, find=find, quiet=quiet)


    def __show(self,
             value_or_label: str,
             category: str=None,
             label: bool=False,
             find: bool=False,
             quiet: bool=False):

        if category is None:
            try:
                if quiet is True:
                   print(Settings.__dict__[value_or_label])
                else:
                   pprint(Settings.__dict__[value_or_label])
            except KeyError:
                raise ei.PacliInputDataError("This setting label does not exist in the basic configuration file.")
            return

        elif type(category) != str:
            raise ei.PacliInputDataError("You have to provide a category if showing the extended config file.")

        if find:
            result = ei.run_command(ce.search_value_content, category, str(value_or_label))
        elif label:
            """Shows a label for a value."""
            result = ei.run_command(ce.search_value, category, str(value_or_label))
        else:
            result = ei.run_command(ce.show, category, value_or_label, quiet=quiet)

        #if result is None and not quiet:
        #    print("No label was found.")
        if quiet is True:
            return result
        else:
            print("Label(s) stored for value {}:".format(value_or_label))
            pprint(result)


    def list(self, extended: bool=False, categories: bool=False):
        """Shows current contents of the standard or extended configuration file.

        Flags:
        -e, --extended: Shows extended configuration file.
        -c, --categories: Shows list of available categories (only in combination with -e/--extended).
        """
        if extended is True:
            if categories is True:
                return [cat for cat in ce.get_config()]
            else:
                return ce.get_config()
        else:
            pprint(Settings.__dict__)


    def update_extended_categories(self, quiet: bool=False):
        # (replaces `tools update_categories` -> this command will be used very seldom, so it's not problematic if it's long or unintuitive.)
        """Update the category list of the extended config file.

        Flags:
        -q / --quiet: Suppress output.
        """

        ce.update_categories(quiet=quiet)



class ExtAddress:

    # NEW COMMANDS
    def set(self,
            label: str=None,
            address: str=None,
            account: str=None,
            new: bool=False,
            delete: bool=False,
            modify: bool=False,
            quiet: bool=False,
            keyring: bool=False,
            now: bool=False,
            import_all_keyring_addresses: bool=False):

        """Sets the current main address or stores / deletes a label for an address.

        Usage options:

        pacli address set LABEL ADDRESS [options]

        Without flags, stores a label for an address.

        pacli address set LABEL [--new] [--delete] [options]

        Without flags, sets the LABEL as the main address.

        pacli address set NEW_LABEL OLD_LABEL --modify

        Modifies a label (OLD_LABEL is replaced by NEW_LABEL).

        Options and flags:

        -n, --new: Creates an address/key with the wallet software and assigns it a label.
        -d, --delete: Deletes the specified address label. Use --now to delete really.
        -m, --modify: Replaces the label for an address by another one.
        -k, --keyring: Use the keyring of the operating system (Linux/Unix only) for the labels. Otherwise the extended config file is used.
        -a, --account: Imports main key or any stored key to an account in the wallet managed by RPC node. Works only with keyring labels.
        -i, --import_all_keyring_addresses: Stores all labels/addresses stored in the keyring in the extended config file. --modify allows existing entries to be replaced, otherwise they won't be changed.
        -q, --quiet: Suppress output, printout in script-friendly way.
        """

        # (replaces: `address set_main`, `address fresh`, `tools store_address`, `address set_label`, `tools store_address_from_keyring`, `address delete_label`, `tools delete_address_label`,  `address import_to_wallet` and  `tools store_addresses_from_keyring`) (Without flag it would work like the old address set_main, flag --new will generate a new address, like the current "fresh" command, other options are implemented with new flags like --delete, --keyring, --from-keyring, --all-keyring-labels, --into-wallet)
        # keyring commands will be added in a second step
        # NOTE: --into-wallet flag is not necessary as the --account flag is only used in this option.
        # NOTE: --set_main in --new will be trashed. It's logical that it should be change to this address.
        # NOTE: --backup options could be trashed. This option is now very unlikely to be used. Setting it to None for now.

        kwargs = locals()
        del kwargs["self"]
        ei.run_command(self.__set_label, **kwargs)


    def __set_label(self,
            label: str=None,
            address: str=None,
            account: str=None,
            new: bool=False,
            delete: bool=False,
            modify: bool=False,
            quiet: bool=False,
            keyring: bool=False,
            now: bool=False,
            import_all_keyring_addresses: bool=False):

        if label is None:
            if import_all_keyring_addresses:
                return ec.store_addresses_from_keyring(quiet=quiet, replace=modify)
            else:
                raise ei.PacliInputDataError("No label provided. See -h for options.")

        elif new is True:
            return ec.fresh_address(label, set_main=True, backup=None, keyring=keyring, quiet=quiet)

        elif delete is True:
            """deletes a key with an user-defined label. Cannot be used to delete main key."""
            return ec.delete_label(label, keyring=keyring, now=now)

        elif account is not None:
            """"""
            return ke.import_key_to_wallet(account, label)

        elif address is not None: # ex: tools store_address
            """Stores a label for an address in the extended config file."""
            # ec.store_address(label, address=address, modify=modify)
            ec.set_label(label, address, set_main=True, keyring=keyring, modify=modify, network_name=Settings.network)
            if not quiet:
                print("Stored address {} with label {}.".format(address, label))

        else: # set_main
            """Declares a key identified by a label as the main one."""
            return ec.set_main_key(label, backup=None, keyring=keyring, quiet=quiet)


    def show(self,
             addr_id: str=None,
             privkey: bool=False,
             pubkey: bool=False,
             wif: bool=False,
             keyring: bool=False,
             label: bool=False):
        # This one has to REPLACE the Address command, and integrate more options. Thus the address show command in __main__ must be always commented out.
        # (unchanged from vanilla, but would now integrate also the commands `address show_label` and `tools show_address_label` if used with a label)
        # NOTE: it would be cool to have the --pubkey... option also for labeled addresses, but that may be quite difficult.
        """Shows the address corresponding to a label, or the main address.

        Usage options:

        pacli address show

        Shows current main address.

        pacli address show LABEL

        Shows address corresponding to label LABEL.

        pacli address show [ADDRESS] --label

        Shows label and address corresponding to address.


        Options and flags:
        -l, --label: Shows label for an address (see Usage options)
        -k, --keyring: Use the keyring of your operating system (Linux/Unix only)
        -w, --wif: Show private key in Wallet Interchange Format (WIF). Only with --keyring option. (WARNING: exposes private key!)
        --privkey: Shows private key. Only with --keyring option. (WARNING: exposes private key!)
        --pubkey: Shows public key. Only with --keyring option.
        """


        if label is True:
            """Shows the label of the current main address, or of another address."""
            # TODO: evaluate if the output should really include label AND address, like in the old command.
            if addr_id is None:
                addr_id = Settings.key.address
            return ei.run_command(ec.show_label, addr_id, keyring=keyring)

        elif addr_id is not None:
            """Shows a stored alternative address or key.
            --privkey, --pubkey and --wif options only work with --keyring."""

            return ei.run_command(ec.show_stored_address, addr_id, Settings.network, pubkey=pubkey, privkey=privkey, wif=wif, keyring=keyring)

        else:
            if pubkey is True:
                return Settings.key.pubkey
            if privkey is True:
                return Settings.key.privkey
            if wif is True:
                return Settings.key.wif

            return Settings.key.address


    def list(self,
             advanced: bool=False,
             keyring: bool=False,
             coinbalances: bool=False,
             labels: bool=False,
             full_labels: bool=False,
             named: bool=False,
             without_labels: bool=False,
             only_labels: bool=False,
             quiet: bool=False,
             blockchain: str=Settings.network,
             debug: bool=False):
        """Shows a list of addresses, and optionally balances of coins and/or tokens.

        Usage modes:

        pacli address list [options]

        Shows a table of all stored addresses and those which contain coins, PoD and PoB tokens

        pacli address list [-a/--advanced] [options]

        Shows a JSON string of all stored addresses and all or some tokens.

        Exclusive flags for this mode:
        -o, --only_labels: Do not show addresses, only labels.
        -w, --without_labels: Do not show labels, only addresses.

        pacli address list -l/--labels
        pacli address list -f/-full_labels

        Shows only the labels which were stored.
        These modes only accept the -b/--blockchain and -k/--keyring additional flags.
        -f/--full_labels shows the labels with the network prefix (useful mainly for debugging).

        Common options or flags for all or most modes:

        -n, --named: Shows only addresses which were named with a label.
        -k, --keyring: Uses the keyring of your operating system.
        -c, --coinbalances: Only shows coin balances, not tokens (faster).
        -q, --quiet: Suppress output, printout in script-friendly way.
        -b, --blockchain NETWORK: Limit the results to those for a specific blockchain network. By default, it's the network used in the config file.
        -d, --debug: Show debug information.
        """
        # TODO: P2TH addresses should normally not be shown, implement a flag for them.

        return ei.run_command(self.__list, advanced=advanced, keyring=keyring, coinbalances=coinbalances, labels=labels, full_labels=full_labels, no_labels=without_labels, only_labels=only_labels, named=named, quiet=quiet, network=blockchain, debug=debug)

    def __list(self,
               advanced: bool=False,
               keyring: bool=False,
               coinbalances: bool=False,
               labels: bool=False,
               full_labels: bool=False,
               no_labels: bool=False,
               only_labels: bool=False,
               named: bool=False,
               quiet: bool=False,
               network: str=Settings.network,
               debug: bool=False):

        if (coinbalances is True) or (labels is True) or (full_labels is True):
            # TODO: doesn't seem towork with keyring.
            # ex tools show_addresses
            if (labels is True) or (full_labels is True):
                named = True
            address_labels = ec.get_labels_and_addresses(prefix=network, keyring=keyring, named=named)

            if (labels is True) or (full_labels is True):
                if full_labels is True:
                    result = address_labels
                else:
                    result = [{ke.format_label(l, keyring=keyring) : address_labels[l]} for l in address_labels]
                if quiet is True:
                    return result
                else:
                    pprint(result)
                    return

            else:
                addresses = []
                for full_label, address in address_labels.items():
                    network_name, label = ce.process_fulllabel(full_label)

                    try:
                        balance = str(provider.getbalance(address))
                    except TypeError:
                        balance = "0"
                        if debug is True:
                            print("No valid balance for address with label {}. Probably not a valid address.".format(label))

                    if balance != "0":
                        balance = balance.rstrip("0")

                    if (network is None) or (network == network_name):
                        addresses.append({"label": label,
                                          "address" : address,
                                          "network" : network_name,
                                          "balance" : balance})

                ei.print_address_list(addresses)
                return
        else:

            return tc.all_balances(wallet=True,
                                  keyring=keyring,
                                  no_labels=no_labels,
                                  only_tokens=False,
                                  advanced=advanced,
                                  only_labels=only_labels,
                                  named=named,
                                  quiet=quiet,
                                  debug=debug)

    def balance(self, label: str=None, address: str=None, keyring: bool=False):
        """Shows the balance of an address, by default of the current main address.

        Usage:

        pacli address balance

        Shows main address balance.

        pacli address balance LABEL

        Shows balance of the address corresponding to label.

        pacli address balance --address=ADDRESS

        Shows balance of address. Does only work with addresses stored in your wallet file.

        Flags:
        -k, --keyring: Use an address stored in the keyring of your operating system.
        """

        # REPLACES address balance
        # (unchanged from vanilla, but with wrapper for labels)
        if label is not None:
            address = ei.run_command(ec.show_stored_address, label, keyring=keyring)
        elif address is None:
            address = Settings.key.address

        pprint(
            {'balance': float(provider.getbalance(address))}
            )


class ExtDeck:

    def set(self,
            label: str,
            deckid: str=None,
            modify: bool=False,
            delete: bool=False,
            quiet: bool=False,
            now: bool=False):
        """Sets, modifies or deletes a label for a deck.

        Usage:

        pacli set LABEL DECKID [--options]

        Sets LABEL for DECKID.

        pacli set LABEL --delete [--now]

        Deletes LABEL from extended configuration file.


        Options and flags:

        -m, --modify: Modify the label for a value.
        -d, --delete: Delete the specified label. Use --now to delete really.
        -q, --quiet: Suppress output, printout in script-friendly way.
        """

        # (replaces `tools store_deck` - is a power user command because most users would be fine with the default PoB and PoD token)

        if delete is True:
            return ce.delete("deck", label=str(label), now=now)
        else:
            return ce.setcfg("deck", label, deckid, modify=modify, quiet=quiet)


    def list(self,
             pobtoken: bool=False,
             dpodtoken: bool=False,
             attoken: bool=False,
             named: bool=False,
             show_p2th: bool=False,
             quiet: bool=False):
        """Lists all decks (default), or those of a specified token type, or those with a stored label.

        Note: The deck's 'name' is not unique. To give a deck a (locally) unique identifier, store it with a label.

        Usage:

        pacli deck list [options]

        Options and flags:

        -n, --named: Only show decks with a stored label.
        -q, --quiet: Suppress output, printout in script-friendly way.
        -p, --pobtoken: Only show PoB token decks.
        -d, --dpodtoken: Only show dPoD token decks.
        -a, --attoken: Only show AT token decks.
        -s, --show_p2th: Shows P2TH address. When used with -d, show all P2TH addresses of the deck.

        """
        # TODO: --pobtoken and --attoken currently show exactly the same decks. --pobtoken should only show PoB decks.
        # (vanilla command, but extended it replaces: `tools show_stored_decks`, `deck list` with --all flag, `pobtoken list_decks` with --pobtoken flag, and `podtoken list_decks` with --podtoken flag)
        if (pobtoken is True) or (attoken is True):
            decks = ei.run_command(dmu.list_decks_by_at_type, provider, c.ID_AT)
        elif dpodtoken is True:
            decks = ei.run_command(dmu.list_decks_by_at_type, provider, c.ID_DT)
        elif named is True:
            """Shows all stored deck IDs and their labels."""
            return ce.list("deck", quiet=quiet)
        else:
            decks = ei.run_command(pa.find_all_valid_decks, provider, Settings.deck_version,
                                        Settings.production)
        if show_p2th is True:
            if dpodtoken is True:
                deck_dict = {d.id : {"deck_p2th" : d.p2th_address,
                                     "proposal_p2th" : d.derived_p2th_address("donation"),
                                     "voting_p2th" : d.derived_p2th_address("voting"),
                                     "signalling_p2th" : d.derived_p2th_address("signalling"),
                                     "locking_p2th" : d.derived_p2th_address("locking"),
                                     "donation_p2th": d.derived_p2th_address("donation")}
                                     for d in decks}

            else:
                deck_dict = {d.id : d.p2th_address for d in decks}
            if quiet is True:
                print(deck_dict)
            else:
                pprint(deck_dict)
        else:
            print_deck_list(decks)


    def show(self,
             deckstr: str,
             param: str=None,
             info: bool=False,
             find: bool=False,
             p2th: bool=False,
             quiet: bool=False):
        """Shows or searches a deck stored with a label.

        Usage:

        pacli deck show LABEL [options]

        Shows deck stored with label LABEL.

        pacli deck show STRING --find

        Searches for a stored deck containing string STRING.

        Options and flags:

        -i, --info: Shows deck values.
        -f, --find: Searches for a string in the Deck ID.
        -q, --quiet: Suppress output, printout in script-friendly way.
        --param PARAM: Shows a specific parameter (only in combination with --info).
        --p2th: Shows P2TH addresses (in combination with --info, only dPoD tokens)
        """

        #TODO: an option to search by name would be fine here.
        # (replaces `tools show_deck` and `token deck_info` with --info flag) -> added find to find the label for a deckid.
        if info is True:
            deckid = eu.search_for_stored_tx_label("deck", deckstr)
            deckinfo = ei.run_command(eu.get_deckinfo, deckid, p2th)

            if param is not None:
                print(deckinfo.get(param))
            else:
                pprint(deckinfo)

        elif find is True:
            return ce.find("deck", deckstr, quiet=quiet)
        else:
            return ce.show("deck", deckstr, quiet=quiet)

    def init(self,
             idstr: str=None,
             dpodtoken: bool=False,
             store_label: bool=False,
             quiet: bool=False) -> None:
        """Initializes a deck (token).
        This is mandatory to be able to use a token with pacli.

        Usage:

        pacli deck init

        Initialize the default PoB and dPoD tokens of this network.

        pacli deck init DECK

        Initialize a single deck. DECK can be a Deck ID or a label.

        Flags:

        -d, --dpodtoken: Initialize a dPoD token.
        -s, --store_label LABEL: Store a label for the deck in the extended configuration file.
            Does only work if a deck is given.
        -q, --quiet: Suppress output.
        """

        netw = Settings.network

        if idstr is None:
            pob_deck = pc.DEFAULT_POB_DECK[netw]
            dpod_deck = pc.DEFAULT_POD_DECK[netw]

            ei.run_command(eu.init_deck, netw, pob_deck, quiet=quiet)
            ei.run_command(dc.init_dt_deck, netw, dpod_deck, quiet=quiet)
        else:
            deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", idstr, quiet=quiet)
            if dpodtoken is True:
                ei.run_command(dc.init_dt_deck, netw, deckid, quiet=quiet, store_label=store_label)
            else:
                ei.run_command(eu.init_deck, netw, deckid, quiet=quiet)



class ExtCard:
    def list(self, deck: str, quiet: bool=False, valid: bool=False):
        """List all cards of a deck (with support for deck labels).

        Usage:

        pacli card list [options]

        Options and flags:

        -q, --quiet: suppresses information about the deck when a label is used, printout in script-friendly way.
        -v, --valid: only shows valid cards according to Proof-of-Timeline rules,
        i.e. where no double spend has been recorded."""

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", deck, quiet=quiet) if deck else None
        return ei.run_command(self.__listext, deckid, quiet=quiet, valid=valid)

    def __listext(self, deckid: str, quiet: bool=False, valid: bool=False):

        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

        try:
            cards = pa.find_all_valid_cards(provider, deck)
        except pa.exceptions.EmptyP2THDirectory as err:
            # return err
            raise PacliInputDataError(err)

        if valid is True:
            result = pa.protocol.DeckState(cards).valid_cards
        else:
            result = cards

        print_card_list(list(result))



class ExtTransaction:

    def set(self,
            label_or_tx: str,
            tx: str=None,
            modify: bool=False,
            delete: bool=False,
            now: bool=False,
            quiet: bool=False) -> None:
        """Stores a transaction with label and hex string.

           Usage modes:

           pacli transaction set LABEL TX_HEX

           Stores hex string of transaction (TX_HEX) together with label LABEL.

           pacli transaction ste LABEL TXID

           Stores hex string of transaction identified by the given TXID.

           pacli transaction set TX_HEX

           Stores hex string of transaction TX with the transaction ID (TXID) as label. Do not use for partially signed transactions!

           pacli transaction set LABEL [-d|--delete] [--now]

           Deletes label (use --now to delete really).

           pacli transaction set NEWLABEL OLDLABEL --modify

           Changes the label.

           Options and flags:

           -m, --modify: changes the label.
           -q, --quiet: suppress output, printout in script-friendly way.

        """

        return ei.run_command(self.__set, label_or_tx, tx=tx, modify=modify, delete=delete, now=now, quiet=quiet)

    def __set(self, label_or_tx: str,
            tx: str=None,
            modify: bool=False,
            delete: bool=False,
            now: bool=False,
            quiet: bool=False) -> None:

        if delete is True:
            return ce.delete("transaction", label=label_or_tx, now=now)

        if tx is None:
            value = label_or_tx
            if not quiet:
                print("No label provided, TXID is used as label.")
        else:
            try:
                # if "tx" is a TXID, get the transaction hex from blockchain
                value = provider.getrawtransaction(tx)
            except:
                value = tx

        if not modify:
            # we can't do this check with modify enabled, as the value here isn't a TXHEX
            try:
                txid = provider.decoderawtransaction(value)["txid"]
            except KeyError:
                raise ei.PacliInputDataError("Invalid value. This is neither a valid transaction hex string nor a valid TXID.")

        label = txid if tx is None else label_or_tx

        return ce.setcfg("transaction", label, value=value, quiet=quiet, modify=modify)


    def show(self, txid_or_label: str, quiet: bool=False, structure: bool=False, decode: bool=False):

        """Shows a transaction, by default a stored transaction by its label.

        Usage:

           pacli transaction show LABEL [-d]

           Shows a transaction stored in the extended config file, by label, as HEX or JSON string.

           pacli transaction show TXID [-d]

           Shows any transaction's content, as HEX or JSON string.

           pacli transaction show TXID -a

           Shows senders and receivers of any transaction.

        Flags:

           -s, --structure: Show senders and receivers (not supported in the mode with LABELs).
           -q, --quiet: Suppress output, printout in script-friendly way.
           -d, --decode: Show transaction in JSON format (default: hex format).

        """
        return ei.run_command(self.__show, txid_or_label, quiet=quiet, structure=structure, decode=decode)

    def __show(self, txid_or_label: str, quiet: bool=False, structure: bool=False, decode: bool=False):
        # TODO: would be nice to support --structure mode with Labels.

        if structure is True:

            if not eu.is_possible_txid(txid_or_label):
                raise ei.PacliInputDataError("The identifier you provided isn't a valid TXID. The --structure/-s mode currently doesn't support labels.")

            tx_structure = ei.run_command(bx.get_tx_structure, txid_or_label)

            if quiet is True:
                return tx_structure
            else:
                pprint(tx_structure)

        else:
            result = ce.show("transaction", txid_or_label, quiet=True)
            if result is None:
                try:
                    result = provider.getrawtransaction(txid_or_label)
                    assert type(result) == str
                except AssertionError:
                    if not quiet:
                        raise ei.PacliInputDataError("Unknown transaction identifier. Label wasn't stored or transaction doesn't exist on the blockchain.")

            try:
                tx_decoded = provider.decoderawtransaction(result)
                assert tx_decoded["txid"] is not None
            except:
                if not quiet:
                    print("WARNING: Transaction was not stored correctly.")
                tx_decoded = {}

            if decode:
                if quiet is True:
                    print(tx_decoded)
                else:
                    pprint(tx_decoded)
            elif quiet is True:
                return result
            else:
                pprint(result)


    def list(self,
             address_or_deck: str=None,
             all: str=None,
             address: str=None,
             advanced: bool=False,
             burns: bool=None,
             claims: bool=None,
             coinbase: bool=False,
             count: bool=False,
             debug: bool=False,
             end: bool=False,
             keyring: bool=False,
             named: bool=False,
             param: str=None,
             quiet: bool=False,
             received: bool=False,
             receiver: str=None,
             reftxes: bool=None,
             raw: bool=False,
             sender: str=None,
             sent: bool=False,
             start: bool=False,
             unclaimed: bool=False,
             wallet: bool=False) -> None:
        """Lists transactions, optionally of a specific type (burn transactions and claim transactions).

        Usage:

        pacli transaction list [ADDRESS] [options] [--sent] [--received]

            Lists transactions sent and/or received by a specific address of the wallet (default: current main address). Can be slow if used on wallets with many transactions.
            ADDRESS can be a label or an address.

        pacli transaction list [-n|--named]

            Lists transactions stored with a label (e.g. for DEX purposes).

        pacli transaction list [--deck=DECK] [--burns | --reftxes]

            Lists burn transactions or referenced (e.g. donation/ICO) TXes for AT tokens stored in wallet. Deck is optional for burn transactions.
            DECK can be a label or a deck ID.

        pacli transaction list DECK --claims

            List token claim transactions.
            DECK can be a label or a deck ID.

        pacli transaction list --all [--burns | --reftxes] [--sender=SENDER] [--receiver=RECEIVER] --start=START --end=END

            Block explorer mode: List all transactions between two block heights. WARNING: VERY SLOW if used with large block height ranges!
            START and END can be block heights or the dates of the block timestamps (in format YYYY-MM-DD).
            Note: In this mode, --sender and --receiver can be any address, not only wallet addresses.


        Other options and flags:

        --sent: Only show sent transactions (not in combination with --named, --claims, --burns or --reftxes)
        --received: Only show received transactions (not in combination with --named, --claims, --burns or --reftxes)
        --advanced: Show complete transaction JSON or card transfer dictionary.
        -w, --wallet: Show all specified transactions of all addresses in the wallet.
        -u, --unclaimed: Show only unclaimed burn or referenced transactions (only --burns and --reftxes, needs a --deck to be specified).
        --coinbase: Show coinbase transactions (not in combination with --burns, --reftxes, --named or --claims).
        --sender: Show transactions sent by a specific sender address (only in combination with --all).
        --receiver: Show transactions received by a specific receiver address (only in combination with --all).
        -k, --keyring: Use an address/label stored in the keyring (not supported by --all mode).
        --count: Only count transactions, do not display them.
        -q, --quiet: Suppress additional output, printout in script-friendly way.
        -d, --debug: Provide debugging information.
        --raw: Show raw output of the RPC commands (debugging option).
        -p, --param PARAMETER: Show the result of a specific parameter of the transaction.
              Possible parameters are all first-level keys of the dictionaries output by the distinct modes of this command.
              If used together with --advanced, the possible parametes are the first-level keys of the transaction JSON string,
              with the exception of --claims mode, where the attributes of a CardTransfer object can be used.

        """
        kwargs = locals()
        del kwargs["self"]
        return ei.run_command(self.__list, **kwargs)

    def __list(self,
             address_or_deck: str=None,
             address: str=None,
             sender: str=None,
             burns: bool=None,
             reftxes: bool=None,
             claims: bool=None,
             all: str=None,
             named: bool=False,
             sent: bool=False,
             received: bool=False,
             coinbase: bool=False,
             advanced: bool=False,
             wallet: bool=False,
             param: str=None,
             receiver: str=None,
             unclaimed: bool=False,
             keyring: bool=False,
             start: bool=False,
             end: bool=False,
             count: bool=False,
             quiet: bool=False,
             debug: bool=False,
             raw: bool=False) -> None:
        # TODO: Further harmonization: Results are now:
        # --all: tx_structure or tx JSON
        # --burns/--reftxes: custom dict with sender_label and sender_address
        # --advanced: always tx JSON
        # without any label:

        if address:
            address = ec.process_address(address, keyring=keyring, try_alternative=False)

        if (not named) and (not quiet):
            print("Searching transactions (this can take several minutes) ...")

        if all is True:
            if (burns is True) or (reftxes is True):
                txes = bx.show_txes(deck=address_or_deck, sending_address=sender, start=start, end=end, quiet=quiet, advanced=advanced, debug=debug, burns=burns)
            else:
                txes = bx.show_txes(sending_address=sender, receiving_address=receiver, start=start, end=end, coinbase=coinbase, advanced=advanced, quiet=quiet, debug=debug, burns=False)
        elif burns is True:
            txes = au.my_txes(address=address, deck=address_or_deck, unclaimed=unclaimed, wallet=wallet, keyring=keyring, advanced=advanced, quiet=quiet, debug=debug, burns=True)
        elif reftxes is True:
            txes = au.my_txes(address=address, deck=address_or_deck, unclaimed=unclaimed, wallet=wallet, keyring=keyring, advanced=advanced, quiet=quiet, debug=debug, burns=False)
        elif claims is True:
            txes = eu.show_claims(deck_str=address_or_deck, address=address, wallet=wallet, full=advanced, param=param, debug=debug)
        elif named is True:
            """Shows all stored transactions and their labels."""
            txes = ce.list("transaction", quiet=quiet, prettyprint=False, return_list=True)
            if advanced is True:
                txes = [{key : provider.decoderawtransaction(item[key])} for item in txes for key in item]
        elif wallet or raw:
            txes = ec.get_address_transactions(sent=sent, received=received, advanced=advanced, sort=True, wallet=wallet, debug=debug, keyring=keyring, raw=raw)
        else:
            """returns all transactions from or to that address in the wallet."""

            address = Settings.key.address if address_or_deck is None else address_or_deck
            txes = ec.get_address_transactions(addr_string=address, sent=sent, received=received, advanced=advanced, keyring=keyring, sort=True, debug=debug)

        if count is True:
            return len(txes)
        elif quiet is True:
            return txes
        elif (param is not None) and not claims:
            try:
                if quiet is True:
                    return [{t["txid"] : t[param]} for t in txes]
                else:
                    pprint([{t["txid"] : t[param]} for t in txes])
            except KeyError:
                raise ei.PacliInputDataError("Parameter does not exist in the JSON output of this mode, or you haven't entered a parameter. You have to enter the parameter after --param/-p.")
        else:
            for txdict in txes:
                pprint(txdict)

    # the following commands are perhaps subject to be integrated into the normal transaction commands as flags.

    def set_utxo(self,
                 label: str,
                 txid_or_oldlabel: str=None,
                 output: int=None,
                 modify: bool=False,
                 delete: bool=False,
                 now: bool=False,
                 quiet: bool=False) -> None:

        """Stores a label for the transaction ID and output number (vout) of a specific UTXO. Use mostly for DEX purposes.

        Usage options:

        pacli transaction set_utxo LABEL TXID OUTPUT

        Stores a label for an UTXO with a TXID and an output number OUTPUT.

        pacli transaction set_utxo NEWLABEL OLDLABEL --modify

        Modifies a label for an UTXO.

        pacli transaction set_utxo LABEL --delete [--now]

        Deletes a label for an UTXO (--now to delete really).

        Flags:

        --quiet: Supresses output, printout in script-friendly way."""

        if delete is True:
            return ce.delete("utxo", str(label), now=now)

        if (modify is True) and (output is None):
            utxo = txid_or_oldlabel
        else:
            utxo = "{}:{}".format(txid_or_oldlabel, str(output))
        return ce.setcfg("utxo", label, value=utxo, quiet=quiet, modify=modify)

    def show_utxo(self, label: str, quiet: bool=False) -> str:
        """Shows a stored UTXO by its label.

        Usage:

        pacli transaction show_utxo LABEL

        Flag:
        -q, --quiet: Suppress additional output."""

        return ce.show("utxo", label, quiet=quiet)

    def list_utxos(self, quiet: bool=False) -> None:
        """Shows all stored UTXOs and their labels.

        Usage:

        pacli transaction list_utxos [--quiet]

        Flags:

        --quiet: Suppress output, printout in script-friendly way."""
        return ce.list("utxo", quiet=quiet)

