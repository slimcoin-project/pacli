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
from pacli.config import Settings, default_conf, write_settings, conf_dir
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
            delete: bool=False,
            modify: bool=False,
            replace: bool=False,
            now: bool=False,
            quiet: bool=False,
            extended: str=None,
            compatibility_mode: bool=False) -> None:
        """Changes configuration settings of the basic or extended configuration file.

           WARNING: The basic configuration file contains many settings which may lead immediately to problems if changed.

           Usage modes:

           pacli config set LABEL VALUE -r [-e CATEGORY]

               Replaces the VALUE associated with LABEL in the basic configuration file or in a
               category CATEGORY of the extended configuration file.
               WARNING: If changing the parameters of the basic configuration file,
               the application may not work anymore! In this case you have to modify
               the file manually.
               (NOTE: In compatibility mode, the -r flag can be omitted.)

           pacli config set LABEL VALUE -e CATEGORY

               Adds a new setting (LABEL/VALUE pair) to the extended configuration file.
               The CATEGORY is mandatory.

           pacli config set LABEL -d -e CATEGORY [--now]

               Deletes a setting (LABEL and its associated value) in the extended configuration file.
               Use --now to really delete it, otherwise a dry run will be performed.

           pacli config set NEW_LABEL OLD_LABEL -m -e CATEGORY

               Modifies a label in the extended configuration file (OLD_LABEL gets replaced by NEW_LABEL).

           pacli config set [True|False] -c

               Enables (True) or disables (False) the compatibility mode.
               Compatibility mode will format all outputs of commands like 'vanilla' PeerAssets,
               and ensures the original commands and their flags work as expected.
               Please refer to the original PeerAssets README.

           Notes:

               The basic configuration settings 'network', 'provider' 'rpcuser', 'rpcpassword' and 'rpcport'
               need to match the configuration of the coin client and the network/blockchain used.
               They should only be changed if pacli is to be used with a different network (e.g. testnet instead of mainnet)
               or wallet file/data directory. Once the setting has been changed you can't work with the old settings.
               The errors can be only solved changing back the values manually in pacli.conf.
               The setting 'deck_version' should only be changed by developers, as currently only version 1 is used
               and otherwise it will lead to errors with decks.
               Changing 'production' setting to False will enable a test environment for test tokens/decks which is
               incompatible with normal decks, this should also only be changed by developers.
               To change from testnet to mainnet and vice versa, use the 'network' setting.

           Args:

             extended: Use the extended configuration file.
             replace: Replaces the value of a setting (mandatory to change settings in basic configuration file).
             modify: Modify the label of a setting (only extended configuration file).
             delete: Delete a setting (only extended configuration file).
             now: Really delete a setting, in combination with -d/--delete.
             quiet: Suppress output, printout in script-friendly way.
             value: To be used as a positional argument (flag keyword is not mandatory), see 'Usage modes' above.
             compatibility_mode: Enable or disable compatibility mode. See Usage modes.

"""

        return ei.run_command(self.__set, label, value=value, category=extended, delete=delete, modify=modify, replace=replace, now=now, quiet=quiet, compatibility_mode=compatibility_mode)

    def __set(self,
              label: str,
              value: Union[str, bool]=None,
              category: str=None,
              delete: bool=False,
              modify: bool=False,
              replace: bool=False,
              now: bool=False,
              quiet: bool=False,
              compatibility_mode: bool=False) -> None:

        if category is not None:
            if type(category) != str:
                # if -e is given without cat, it gets replaced by a bool value (True).
                raise ei.PacliInputDataError("You have to provide a category if modifying the extended config file.")
            else:
                if delete is True:
                    return ce.delete(category, label=str(label), now=now)
                else:
                    return ce.setcfg(category, label=label, value=value, modify=modify, replace=replace, quiet=quiet)

        if compatibility_mode is True:
            if label in ("True", "true", "yes", "1", True):
                value = "True"
            else:
                value = "False"
            label = "compatibility_mode"
            if not quiet:
                print("Setting compatibility mode to {}.".format(value))
                print("Compatibility mode affects the output of some original commands,")
                print("but doesn't affect the inner workings nor the extended commands.")
        else:

            if value is None:
                raise ei.PacliInputDataError("No value provided.")
            if modify is True or delete is True:
                raise ei.PacliInputDataError("Modifying labels or deleting them in the basic config file is not permitted.")
            if label not in default_conf.keys():
                if Settings.compatibility_mode == "True":
                    raise ValueError({'error': 'Invalid setting key.'}) # ValueError added # this was mainly for compatibility.
                else:
                    raise ei.PacliInputDataError("Invalid setting key. This label doesn't exist in the basic configuration file. See permitted labels with: 'config list'.")
            if replace is False:
                if Settings.compatibility_mode == "False":
                    # compat mode works without the -r flag.
                    raise ei.PacliInputDataError("Basic settings can only be modified with the --replace/-r flag. New labels can't be added.")

            if not quiet and (Settings.compatibility_mode == "False"):
                print("Changing basic config setting: {} to value: {}.".format(label, value))
                ei.print_red("WARNING: Changing most of these settings can make pacli unusable or lead to strange errors!\nOnly change these settings if you know what you are doing.")
                print("If this happens, change pacli.conf (located in {}) manually.".format(conf_dir))
                print("It is always advisable to make a backup of pacli.conf before any setting is changed.")
                if not ei.confirm_continuation():
                    print("Aborted.")
                    return

        write_settings(label, str(value))


    def show(self,
             value_or_label: str,
             label: bool=False,
             find: bool=False,
             quiet: bool=False,
             extended: str=None):
        """Shows a setting in the basic or extended configuration file.

        Usage modes:

        pacli config show LABEL

            Shows setting (value associated with LABEL) in the basic configuration file.

        pacli config show LABEL -e CATEGORY

            Shows setting (value associated with LABEL) in a category CATEGORY of the extended configuration file.

        pacli config show VALUE -f [-e CATEGORY]
        pacli config show VALUE -l [-e CATEGORY]

            Searches a VALUE and prints out existing labels for it.
            The -f/--find option allows to search for parts of the value string,
            while the -l/--label option only accepts exact matches (in analogy to 'address show --label').

            The CATEGORY value refers to a category in the extended config file.
            Get all categories with: `pacli config list -e -c`

        Args:

          extended: Use the extended configuration file (see above).
          quiet: Suppress output, printout the result in script-friendly way.
          label: Find label for an exact value.
          find: Find label for a string which is present in the value."""

        return ei.run_command(self.__show, value_or_label, category=extended, label=label, find=find, quiet=quiet)


    def __show(self,
             value_or_label: str,
             category: str=None,
             label: bool=False,
             find: bool=False,
             quiet: bool=False):

        if category is None:
            result = []
            if find or label:
                searchstr = value_or_label
                for label, value in Settings.__dict__.items():
                    exact_value = (label and (str(searchstr) == str(value)))
                    string_found = (find and (str(searchstr) in str(value)))
                    if exact_value or string_found:
                        result.append(label)

            else:
                try:
                    result = Settings.__dict__[value_or_label]
                except KeyError:
                    raise ei.PacliInputDataError("This setting label does not exist in the basic configuration file.")


        elif type(category) != str:
            raise ei.PacliInputDataError("You have to provide a category if showing the extended config file.")

        else:
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
            if find or label:
                print("Label(s) stored for value {}:".format(value_or_label))
            else:
                print("Value of label {}:".format(value_or_label))
            pprint(result)


    def list(self, extended: bool=False, categories: bool=False, all_basic_settings: bool=False):
        """Shows basic configuration settings or entries in the extended configuration file.

        Args:

          extended: Shows extended configuration file.
          categories: Shows list of available categories (only in combination with -e/--extended).
          all_basic_settings: Shows complete list of basic settings, not only pacli.conf file contents. These settings can't be changed as they're loaded on each Pacli start.
        """
        # TODO if anything which is not an argument is shown behind "-e" then it is assumed to be false.
        if extended is True:
            if categories is True:
                return [cat for cat in ce.get_config()]
            else:
                return ce.get_config()
        elif categories is True:
            print("Currently there are no different categories in the basic configuration file.")
        elif all_basic_settings is True:
            pprint(Settings.__dict__)
        else:
            settings = Settings.__dict__
            pprint({s:settings[s] for s in settings if s in default_conf.keys()})


    def update_extended_categories(self, quiet: bool=False):
        """Update the category list of the extended config file.

        Args:

          quiet: Suppress output.
        """
        # TODO perhaps integrate into config set?

        ce.update_categories(quiet=quiet)



class ExtAddress:

    def set(self,
            label: str=None,
            address: str=None,
            to_account: str=None,
            fresh: bool=False,
            delete: bool=False,
            modify: bool=False,
            quiet: bool=False,
            keyring: bool=False,
            now: bool=False,
            import_all_keyring_addresses: bool=False):

        """Sets the current main address or stores / deletes a label for an address.

        Usage modes:

        pacli address set LABEL ADDRESS

            Without flags, stores a label for an address.

        pacli address set LABEL [-f]

            Without flags, sets the LABEL as the main address.
            If -f/--fresh is used, a new address is generated with label LABEL.

        pacli address set -a ADDRESS

            Set an address as the current main address.

        pacli address set LABEL -d [--now]

            Deletes a label LABEL for an address.

        pacli address set NEW_LABEL OLD_LABEL -m

            Modifies a label (OLD_LABEL is replaced by NEW_LABEL).

        Args:

          fresh: Creates an address/key with the wallet software and assigns it a label.
          delete: Deletes the specified address label. Use --now to delete really.
          modify: Replaces the label for an address by another one.
          now: Really delete an entry.
          keyring: Use the keyring of the operating system (Linux/Unix only) for the labels. Otherwise the extended config file is used.
          to_account: Imports main key or any stored key to an account in the wallet managed by RPC node. Works only with keyring labels.
          import_all_keyring_addresses: Stores all labels/addresses stored in the keyring in the extended config file and imports them to the wallet. -m allows existing entries to be replaced, otherwise they won't be changed.
          quiet: Suppress output, printout in script-friendly way.
          address: Address. To be used as positional argument (flag keyword not mandatory). See Usage modes.
          label: Label. To be used as positional argument (flag keyword not mandatory). See Usage modes.
        """

        # (replaces: `address set_main`, `address fresh`, `tools store_address`, `address set_label`, `tools store_address_from_keyring`, `address delete_label`, `tools delete_address_label`,  `address import_to_wallet` and  `tools store_addresses_from_keyring`) (Without flag it would work like the old address set_main, flag --new will generate a new address, like the current "fresh" command, other options are implemented with new flags like --delete, --keyring, --from-keyring, --all-keyring-labels, --into-wallet)
        # keyring commands will be added in a second step
        # NOTE: --backup options could be trashed. This option is now very unlikely to be used. Setting it to None for now.

        kwargs = locals()
        del kwargs["self"]
        kwargs.update({"debug" : True})
        ei.run_command(self.__set_label, **kwargs)


    def __set_label(self,
            label: str=None,
            address: str=None,
            to_account: str=None,
            fresh: bool=False,
            delete: bool=False,
            modify: bool=False,
            quiet: bool=False,
            keyring: bool=False,
            now: bool=False,
            import_all_keyring_addresses: bool=False,
            debug: bool=False):

        if label is None and address is None:
            if import_all_keyring_addresses:
                return ec.store_addresses_from_keyring(quiet=quiet, replace=modify)
            else:
                raise ei.PacliInputDataError("No label provided. See -h for options.")

        elif fresh is True:
            return ec.fresh_address(label, set_main=True, backup=None, keyring=keyring, quiet=quiet)

        elif delete is True:
            """deletes a key with an user-defined label. Cannot be used to delete main key."""
            return ec.delete_label(label, keyring=keyring, now=now)

        elif to_account is not None:
            """creates an account and imports key to it."""
            return ke.import_key_to_wallet(to_account, label)

        elif label is not None and address is not None: # ex: tools store_address
            """Stores a label for an address in the extended config file."""
            # ec.store_address(label, address=address, modify=modify)
            ec.set_label(label, address, set_main=True, keyring=keyring, modify=modify, network_name=Settings.network)
            if not quiet:
                print("Stored address {} with label {}.".format(address, label))

        else: # set_main
            """Declares a key identified by a label or address as the main one."""
            return ec.set_main_key(label=label, address=address, backup=None, keyring=keyring, quiet=quiet)


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

        Usage modes:

        pacli address show

            Shows current main address.

        pacli address show LABEL

            Shows address corresponding to label LABEL.

        pacli address show [ADDRESS] -l

            Shows label and address corresponding to address.


        Args:

          label: Shows label for an address (see Usage options)
          keyring: Use the keyring of your operating system (Linux/Unix only)
          wif: Show private key in Wallet Interchange Format (WIF). Only with --keyring option. (WARNING: exposes private key!)
          privkey: Shows private key. Only with --keyring option. (WARNING: exposes private key!)
          pubkey: Shows public key. Only with --keyring option.
          addr_id: To be used as a positional argument (flag keyword not mandatory). See Usage modes above.
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
             p2th: bool=False,
             quiet: bool=False,
             blockchain: str=Settings.network,
             debug: bool=False,
             include_all: bool=False):
        """Shows a list of addresses, and optionally balances of coins and/or tokens.

        Usage modes:

        pacli address list

            Shows a table of all named addresses and those which contain coins, PoD and PoB tokens

        pacli address list -a

            Advanced mode. Shows a JSON string of all stored addresses and all or some tokens.
            -o/--only_labels and -w/--without_labels are exclusive flags for this mode.

        pacli address list -l
        pacli address list -f

            Shows only the labels which were stored.
            These modes only accept the -b/--blockchain and -k/--keyring additional flags.
            -f/--full_labels shows the labels with the network prefix (useful mainly for debugging).

        Args:

          advanced: Advanced mode, see Usage modes above.
          labels: Show only stored labels.
          full_labels: Show only stored labels with network prefix (debugging option).
          named: Shows only addresses which were named with a label.
          keyring: Uses the keyring of your operating system.
          coinbalances: Only shows coin balances, not tokens (faster).
          quiet: Suppress output, printout in script-friendly way.
          blockchain: If pacli is used with various blockchains, Limit the results to those for a specific blockchain network. By default, it's the network used in the config file.
          debug: Show debug information.
          only_labels: In advanced mode, if a label is present, show only the label.
          p2th: Show only P2TH addresses.
          include_all: Show all genuine wallet addresses, also those with empty balances which were not named. P2TH are not included.
          without_labels: In advanced mode, never show labels, only addresses.
        """
        # TODO: P2TH addresses should normally not be shown, implement a flag for them.

        return ei.run_command(self.__list, advanced=advanced, keyring=keyring, coinbalances=coinbalances, labels=labels, full_labels=full_labels, no_labels=without_labels, only_labels=only_labels, named=named, quiet=quiet, p2th=p2th, network=blockchain, include_all=include_all, debug=debug)

    def __list(self,
               advanced: bool=False,
               keyring: bool=False,
               coinbalances: bool=False,
               labels: bool=False,
               full_labels: bool=False,
               no_labels: bool=False,
               only_labels: bool=False,
               p2th: bool=False,
               named: bool=False,
               quiet: bool=False,
               network: str=Settings.network,
               debug: bool=False,
               include_all: bool=False):

        # excluded_addresses = eu.get_p2th() if p2th is False else []
        if p2th:
            p2th_dict = eu.get_p2th_dict()
            include_only = p2th_dict.keys()
            coinbalances = True
        else:
            include_only = None

        if (coinbalances is True) or (labels is True) or (full_labels is True):
            # TODO: doesn't seem towork with keyring.
            # ex tools show_addresses
            if (labels is True) or (full_labels is True):
                named = True

            # address_labels = ec.get_labels_and_addresses(prefix=network, keyring=keyring, named=named, empty=include_all, exclude=excluded_addresses)
            address_labels = ec.get_labels_and_addresses(prefix=network, keyring=keyring, named=named, empty=include_all, include_only=include_only)

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
                    if "(unlabeled" in label:
                        label = ""

                    try:
                        balance = str(provider.getbalance(address))
                    except TypeError:
                        balance = "0"
                        if debug is True:
                            print("No valid balance for address with label {}. Probably not a valid address.".format(label))

                    if balance != "0":
                        balance = balance.rstrip("0")

                    if (network is None) or (network == network_name):
                        addr_dict = {"label": label,
                                     "address" : address,
                                     "network" : network_name,
                                     "balance" : balance}
                        if p2th:
                            addr_dict.update({"account" : p2th_dict.get(address)})
                        addresses.append(addr_dict)

                ei.print_address_list(addresses, p2th=p2th)
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
                                  empty=include_all,
                                  include_only=include_only,
                                  debug=debug)

    def balance(self, label_or_address: str=None, keyring: bool=False, wallet: bool=False):
        """Shows the balance of an address, by default of the current main address.

        Usage modes:

        pacli address balance

            Shows main address balance.

        pacli address balance LABEL

            Shows balance of the address corresponding to label.

        pacli address balance ADDRESS

            Shows balance of address. Does only work with addresses stored in your wallet file.

        pacli address balance -w

            Shows balance of whole wallet.

        Args:

           keyring: Use an address stored in the keyring of your operating system.
           wallet: Show balance of the whole wallet, see above.
           address_or_label: To be used as a positional argument (without flag keyword), see "Usage modes" above.
        """

        # REPLACES address balance
        return ei.run_command(self.__balance, label_or_address=label_or_address, keyring=keyring, wallet=wallet)

    def __balance(self, label_or_address: str=None, keyring: bool=False, wallet: bool=False):

        if label_or_address is not None:
            address = ec.process_address(label_or_address, keyring=keyring)

            if address is None:
                raise ei.PacliInputDataError("Label was not found.")

        elif wallet is True:
            address = None
        else:
            address = Settings.key.address

        try:
            balance = provider.getbalance(address)
            if (balance == 0) and (address not in eu.get_wallet_address_set(empty=True)):
                raise ei.PacliInputDataError("This address is not in your wallet. Command works only for wallet addresses.")
        except TypeError:
            raise ei.PacliInputDataError("Address does not exist.")


        pprint(
            {'balance': float(balance)}
            )


class ExtDeck:

    def set(self,
            label: str,
            id_deck: str=None,
            modify: bool=False,
            delete: bool=False,
            quiet: bool=False,
            now: bool=False):
        """Sets, modifies or deletes a label for a deck.

        Usage:

        pacli deck set LABEL DECKID

        Sets LABEL for DECKID.

        pacli deck set LABEL -d [--now]

        Deletes LABEL from extended configuration file.

        pacli deck set NEW_LABEL OLD_LABEL -m

        Modifies the label, replacing OLD_LABEL by NEW_LABEL.

        Args:

          modify: Modify the label for a value.
          delete: Delete the specified label. Use --now to delete really.
          quiet: Suppress output, printout in script-friendly way.
          id_deck: Deck ID. To be used as a positional argument (flag keyword not mandatory), see Usage section above.
        """

        # (replaces `tools store_deck` - is a power user command because most users would be fine with the default PoB and PoD token)

        deckid = id_deck
        if delete is True:
            return ce.delete("deck", label=str(label), now=now)
        else:
            return ce.setcfg("deck", label, deckid, modify=modify, quiet=quiet)


    def list(self,
             burntoken: bool=False,
             podtoken: bool=False,
             attoken: bool=False,
             named: bool=False,
             show_p2th: bool=False,
             without_initstate: bool=False,
             quiet: bool=False,
             debug: bool=False):
        """Lists all decks (default), or those of a specified token type, or those with a stored label.

        Note: The deck's global 'name' is not guaranteed to be unique. To give a deck a (locally) unique identifier, store it with a label.

        Usage:

        pacli deck list

        Note: In compatibility mode, the table of 'deck list' without flags is slightly different. It includes the local label and the initialization status.

        Args:

          named: Only show decks with a stored label.
          quiet: Suppress output, printout in script-friendly way.
          burntoken: Only show PoB token decks.
          podtoken: Only show dPoD token decks.
          attoken: Only show AT token decks.
          without_initstate: Don't show initialized status.
          show_p2th: Shows P2TH address. When used with -d, show all P2TH addresses of the deck.
          debug: Show debug information.
        """

        return ei.run_command(self.__list, pobtoken=burntoken, dpodtoken=podtoken, attoken=attoken, named=named, show_p2th=show_p2th, without_initstate=without_initstate, quiet=quiet, debug=debug)

    def __list(self,
             pobtoken: bool=False,
             dpodtoken: bool=False,
             attoken: bool=False,
             named: bool=False,
             show_p2th: bool=False,
             without_initstate: bool=False,
             quiet: bool=False,
             debug: bool=False):

        show_initialized = False if without_initstate else True

        if (pobtoken is True) or (attoken is True):
            decks = list(ei.run_command(dmu.list_decks_by_at_type, provider, c.ID_AT))
            if pobtoken is True:
                decks = [d for d in decks if d.at_address == au.burn_address()]
        elif dpodtoken is True:
            decks = list(ei.run_command(dmu.list_decks_by_at_type, provider, c.ID_DT))
        elif show_p2th is True:
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
            return
        else:
            decks = list(ei.run_command(pa.find_all_valid_decks, provider, Settings.deck_version,
                                        Settings.production))


        if Settings.compatibility_mode == "True" and (not named):
            print_deck_list(decks)
        else:
            deck_label_dict = ce.list("deck", quiet=True)
            if named is True and quiet:
                """Shows all stored deck IDs and their labels."""
                print(deck_label_dict)
                return

            initialized_decks = eu.get_initialized_decks(decks, debug=debug) if show_initialized else []
            deck_list = ei.add_deck_data(decks, deck_label_dict, only_named=named, initialized_decks=initialized_decks, debug=debug)
            if debug:
                print(len(deck_list), "decks found.")
            ei.print_deck_list(deck_list, show_initialized=show_initialized)


    def show(self,
             deckstr: str,
             param: str=None,
             info: bool=False,
             find: bool=False,
             show_p2th: bool=False,
             quiet: bool=False):
        """Shows or searches a deck stored with a label.

        Usage:

        pacli deck show LABEL

        Shows deck stored with label LABEL.

        pacli deck show STRING -f

        Searches for a stored deck containing string STRING.

        Args:

          info: Shows deck values.
          find: Searches for a string in the Deck ID.
          quiet: Suppress output, printout in script-friendly way.
          param: Shows a specific parameter (only in combination with -i/--info).
          show_p2th: Shows P2TH addresses (in combination with -i/--info, only dPoD tokens)
        """
        # TODO: add --show_p2th address to all decks, not only dPoD.
        #TODO: an option to search by name would be fine here.
        # (replaces `tools show_deck` and `token deck_info` with --info flag) -> added find to find the label for a deckid.
        if info is True:
            deckid = eu.search_for_stored_tx_label("deck", deckstr)
            deckinfo = ei.run_command(eu.get_deckinfo, deckid, show_p2th)

            if param is not None:
                print(deckinfo.get(param))
            else:
                pprint(deckinfo)

        elif find is True:
            return ce.find("deck", deckstr, quiet=quiet)
        else:
            return ce.show("deck", deckstr, quiet=quiet)

    def init(self,
             id_deck: str=None,
             label: bool=False,
             no_label: bool=False,
             all_decks: bool=False,
             store_blockheights: int=None,
             quiet: bool=False,
             debug: bool=False) -> None:
        """Initializes a deck (token).
        This is mandatory to be able to use a token with pacli.
        By default, the global deck name is stored as a local label in the extended configuration file.

        Usage modes:

        pacli deck init

            Initialize the default PoB and dPoD tokens of this network.

        pacli deck init DECK

            Initialize a single deck. DECK can be a Deck ID or a label.

        pacli deck init [DECK] -s [BLOCKS] [-a]

        In addition to initializing, store blockheights of transactions relevant for the deck,
        to be used with the block explorer mode of 'transaction list' (-x).
        BLOCKS is the number of blocks to analyze. If not given, it will default to 50000.
        If the decks are already present in the locator file, it will continue from the last commonly checked block.
        If DECK is not given, apply this to standard PoB and dPoD decks.
        If -a is given, do it for all initialized decks.

        Args:

          label: Store a custom label. Does only work if a DECK is given.
          no_label: Do not store any label.
          quiet: Suppress output.
          all_decks: In combination with -s, store blockheights for all initialized decks.
          id_deck: Deck ID. To be used as a positional argument (flag keyword not mandatory). See Usage modes above.
          store_blockheights: Store blockheights for a deck.
          debug: Show debug information.
        """
        kwargs = locals()
        del kwargs["self"]
        ei.run_command(self.__init, **kwargs)

    def __init(self,
               id_deck: str=None,
               label: bool=False,
               no_label: bool=False,
               all_decks: bool=False,
               store_blockheights: int=None,
               quiet: bool=False,
               debug: bool=False) -> None:

        idstr = id_deck
        netw = Settings.network

        if idstr is None:
            pob_deck = pc.DEFAULT_POB_DECK[netw]
            dpod_deck = pc.DEFAULT_POD_DECK[netw]

            ei.run_command(eu.init_deck, netw, pob_deck, quiet=quiet, no_label=no_label)
            ei.run_command(dc.init_dt_deck, netw, dpod_deck, quiet=quiet, no_label=no_label)
            deckid = None
        else:
            deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", idstr, quiet=quiet)
            deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
            if "at_type" in deck.__dict__ and deck.at_type == c.ID_DT:
                ei.run_command(dc.init_dt_deck, netw, deckid, quiet=quiet, label=label, debug=debug, no_label=no_label)
            else:
                ei.run_command(eu.init_deck, netw, deckid, quiet=quiet, label=label, no_label=no_label)

        if store_blockheights:
            if store_blockheights == True:
                blocks = 5000
            elif type(store_blockheights) == int:
                blocks = store_blockheights
            ei.run_command(self.__storeblocks, deckid=deckid, blocks=blocks, all_decks=all_decks, quiet=quiet, debug=debug)
            #if all_decks:
            #    decks = list(pa.find_all_valid_decks(provider, Settings.deck_version, Settings.production))
            #    initialized_decks = eu.get_initialized_decks(decks)
            #elif deckid:
            #    decks = [pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)]
            #else:
            #    decks = [pa.find_deck(provider, pob_deck, Settings.deck_version, Settings.production),
            #            pa.find_deck(provider, dpod_deck, Settings.deck_version, Settings.production)]
            #ei.run_command(bx.store_blockheights, decks, quiet=quiet, debug=debug, blocks=store_blockheights)

    def storeblocks(self, idstr: str=None, blocks: int=50000, all_decks: bool=False, quiet: bool=False, debug: bool=False):
        """Stores blockheights for a deck.

        Usage modes:

            pacli deck storeblocks

        Store blockheights for the standard PoB and dPoD decks.

            pacli deck storeblocks IDSTR

        Store blockheights for a deck.

            pacli deck storeblocks -a

        Store blockheights for all initialized decks.

        Args:

          blocks: Number of blocks to store (default: 50000).
          all_decks: Store blockheights for all initialized decks.
          quiet: Suppress output.
          idstr: Deck label or Deck ID. To be used as a positional argument
          debug: Show additional debug information."""

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", idstr, quiet=quiet) if idstr is not None else None
        ei.run_command(self.__storeblocks, deckid=deckid, blocks=blocks, all_decks=all_decks, quiet=quiet, debug=debug)

    def __storeblocks(self, deckid: str, blocks: int=None, all_decks: bool=False, quiet: bool=False, debug: bool=False):

        if all_decks:
            decks = list(pa.find_all_valid_decks(provider, Settings.deck_version, Settings.production))
            initialized_decks = eu.get_initialized_decks(decks)
        elif deckid:
             decks = [pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)]
        else:
             netw = Settings.network
             decks = [pa.find_deck(provider, pc.DEFAULT_POB_DECK[netw], Settings.deck_version, Settings.production),
                      pa.find_deck(provider, pc.DEFAULT_POD_DECK[netw], Settings.deck_version, Settings.production)]
        ei.run_command(bx.store_blockheights, decks, quiet=quiet, debug=debug, blocks=blocks)



class ExtCard:
    def list(self, deck: str, quiet: bool=False, valid: bool=False):
        """List all cards of a deck (with support for deck labels).

        Usage:

        pacli card list

        Args:

          quiet: Suppresses additional output, printout in script-friendly way.
          valid: Only shows valid cards according to Proof-of-Timeline rules, where no double spend has been recorded."""

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
            txdata: str=None,
            modify: bool=False,
            delete: bool=False,
            now: bool=False,
            quiet: bool=False) -> None:
        """Stores a transaction with label and hex string.

           Usage modes:

           pacli transaction set LABEL TX_HEX

               Stores hex string of transaction (TX_HEX) together with label LABEL.

           pacli transaction set LABEL TXID

               Stores hex string of transaction identified by the given TXID.

           pacli transaction set TX_HEX

               Stores hex string of transaction TX with the transaction ID (TXID) as label. Do not use for partially signed transactions!

           pacli transaction set LABEL -d [--now]

               Deletes label (use --now to delete really).

           pacli transaction set NEWLABEL OLDLABEL -m

               Modifies a label, replacing OLDLABEL with NEWLABEL.

           Args:

             modify: Changes the label.
             quiet: Suppress output, printout in script-friendly way.
             delete: Delete a transaction label/value pair.
             now: Really delete a transaction label/value pair.
             txdata: Transaction data. To be used as a positional argument (flag keyword not mandatory). See Usage modes above.

        """

        return ei.run_command(self.__set, label_or_tx, tx=txdata, modify=modify, delete=delete, now=now, quiet=quiet)

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


    def show(self, label_or_txid: str, quiet: bool=False, structure: bool=False, decode: bool=False, id: bool=False):

        """Shows a transaction, by default a stored transaction by its label.

        Usage modes:

        pacli transaction show LABEL

            Shows a transaction stored in the extended config file, by label, as HEX or JSON string (with -d) or a TXID (with -i).

        pacli transaction show TXID

            Shows any transaction's content, as HEX string or (with -d) as JSON string.

        pacli transaction show TXID -s

            Shows senders and receivers of any transaction.

        Args:

           structure: Show senders and receivers (not supported in the mode with LABELs).
           quiet: Suppress output, printout in script-friendly way.
           decode: Show transaction in JSON format (default: hex format).
           id: Show transaction ID.

        """
        return ei.run_command(self.__show, label_or_txid, quiet=quiet, structure=structure, decode=decode, txid=id)

    def __show(self, label_or_txid: str, quiet: bool=False, structure: bool=False, decode: bool=False, txid: bool=False):
        # TODO: would be nice to support --structure mode with Labels.

        hexstr = decode is False and structure is False

        if structure is True:

            if not eu.is_possible_txid(label_or_txid):
                raise ei.PacliInputDataError("The identifier you provided isn't a valid TXID. The --structure/-s mode currently doesn't support labels.")

            tx_structure = ei.run_command(bx.get_tx_structure, label_or_txid)

            if quiet is True:
                return tx_structure
            else:
                pprint(tx_structure)

        else:
            result = ce.show("transaction", label_or_txid, quiet=True)
            if result is None:
                try:
                    result = provider.getrawtransaction(label_or_txid)
                    assert type(result) == str
                except AssertionError:
                    if not quiet:
                        raise ei.PacliInputDataError("Unknown transaction identifier. Label wasn't stored or transaction doesn't exist on the blockchain.")

            try:
                tx_decoded = provider.decoderawtransaction(result)
                tx_txid = tx_decoded["txid"]
            except:
                if not quiet:
                    print("WARNING: Transaction was not stored correctly.")
                tx_decoded = {}

            if decode is True:
                result = tx_decoded
            elif txid is True:
                result = tx_txid

            if (quiet is True) or hexstr:
                return result
            else:
                pprint(result)


    def list(self,
             _value1: str=None,
             _value2: str=None,
             advanced: bool=False,
             burntxes: bool=None,
             claimtxes: bool=None,
             debug: bool=False,
             end_height: str=None,
             from_height: str=None,
             ids: bool=False,
             keyring: bool=False,
             named: bool=False,
             origin: str=None,
             param: str=None,
             quiet: bool=False,
             received: bool=False,
             gatewaytxes: bool=None,
             zraw: bool=False,
             locator: bool=False,
             sent: bool=False,
             total: bool=False,
             unclaimed: bool=False,
             view_coinbase: bool=False,
             wallet: bool=False,
             xplore: bool=False) -> None:
        """Lists transactions, optionally of a specific type (burn transactions and claim transactions).

        Usage modes:

        pacli transaction list [ADDRESS]

            Lists transactions sent and/or received by a specific address of the wallet.
            ADDRESS is optional and can be a label or an address.
            If ADDRESS is not given, the current main address is used.
            Can be slow if used on wallets with many transactions.

        pacli transaction list -n

            Lists transactions stored with a label in the extended config file
            (e.g. for DEX purposes).

        pacli transaction list [DECK -u] -b
        pacli transaction list DECK -g

            Lists burn transactions or gateway TXes (e.g. donation/ICO) for AT/PoB tokens stored in wallet.
            DECK is mandatory in the case of gateway transactions. It can be a label or a deck ID.
            In the case of -b, DECK is only necessary if combined with -u.

        pacli transaction list DECK -c

            List token claim transactions.
            DECK can be a label or a deck ID.

        pacli transaction list -x [RECEIVER_ADDRESS] [-o ORIGIN_ADDRESS] [-f STARTHEIGHT] [-e ENDHEIGHT]

            Block explorer mode: List all transactions between two block heights.
            RECEIVER_ADDRESS is optional. ORIGIN_ADDRESS is an address of a sender.
            STARTHEIGHT and ENDHEIGHT can be block heights or dates of block timestamps (format YYYY-MM-DD).
            -f and -t options are not mandatory but highly recommended.
            WARNING: VERY SLOW if used with large block height ranges!
            Note: In this mode, both ORIGIN_ADDRESS and RECEIVER_ADDRESS can be any address, not only wallet addresses.

        pacli transaction list -p PARAM

            Show a single parameter or variable of the transactions, together with the TXID.
            This mode can be combined with all other modes.
            Possible parameters are all first-level keys of the dictionaries output by the different modes of this command.
            If used together with --advanced, the possible parametes are the first-level keys of the transaction JSON string,
            with the exception of -c/--claims mode, where the attributes of a CardTransfer object can be used.

        Args:

          advanced: Show complete transaction JSON or card transfer dictionary of claim transactions.
          burntxes: Only show burn transactions.
          claimtxes: Show reward claim transactions (see Usage modes).
          debug: Provide debugging information.
          end_height: Block height or date to end the search at (only in combination with -x).
          from_height: Block height or date to start the search at (only in combination with -x).
          gatewaytxes: Only show transactions going to a gateway address of an AT token.
          ids: Only show transaction ids (TXIDs). If used without -q, 100000 is the maximum length of the list.
          keyring: Use a label of an address stored in the keyring (not supported by -x mode).
          locator: Use block locator (only in combination with -x).
          zraw: List corresponds to raw output of the listtransactions RPC command (debugging option).
          named: Show only transactions stored with a label (see Usage modes).
          origin: Show transactions sent by a specific sender address (only in combination with -x).
          param: Show the value of a specific parameter/variable of the transaction.
          quiet: Suppress additional output, printout in script-friendly way.
          sent: Only show sent transactions (not in combination with -n, -c, -b or -g).
          total: Only count transactions, do not display them.
          unclaimed: Show only unclaimed burn or gateway transactions (only -b and -g, needs a deck to be specified).
          wallet: Show all specified transactions of all addresses in the wallet.
          view_coinbase: Show coinbase transactions (not in combination with -n, -c, -b or -g).
          xplore: Block explorer mode (see Usage modes).
          _value1: Deck or address. Should be used only as a positional argument (flag keyword not mandatory). See Usage modes above.
          _value2: Address (in some modes). Should be used only as a positional argument (flag keyword not mandatory). See Usage modes above.
          received: Only show received transactions (not in combination with -n, -c, -b or -g).
        """
        kwargs = locals()
        del kwargs["self"]
        return ei.run_command(self.__list, **kwargs)

    def __list(self,
             _value1: str=None,
             _value2: str=None,
             advanced: bool=False,
             burntxes: bool=None,
             claimtxes: bool=None,
             debug: bool=False,
             end_height: str=None,
             from_height: str=None,
             gatewaytxes: bool=None,
             ids: bool=False,
             keyring: bool=False,
             locator: bool=False,
             named: bool=False,
             param: str=None,
             origin: str=None,
             quiet: bool=False,
             received: bool=False,
             sent: bool=False,
             unclaimed: bool=False,
             total: bool=False,
             view_coinbase: bool=False,
             wallet: bool=False,
             xplore: bool=False,
             zraw: bool=False) -> None:

        # free letters: j, l, m, y, z

        # v could be view_coinbase
        # o could be only_txids, only_count, only_amount?
        # m could be
        # TODO: Further harmonization: Results are now:
        # -e: tx_structure or tx JSON
        # -b/-g: custom dict with sender_label and sender_address
        # -a: always tx JSON
        # without any label: custom dict with main parameters

        start = from_height
        end = end_height
        burns = burntxes
        reftxes = gatewaytxes
        claims = claimtxes
        txids = ids
        all = xplore
        address_or_deck = _value1
        address = _value2
        count = total
        coinbase = view_coinbase
        raw = zraw
        sender = origin

        if address:
            address = ec.process_address(address, keyring=keyring, try_alternative=False)

        if (not named) and (not quiet):
            print("Searching transactions (this can take several minutes) ...")

        if all is True:
            if (burns is True) or (reftxes is True):
                txes = bx.show_txes(deck=address_or_deck, sending_address=sender, start=start, end=end, quiet=quiet, advanced=advanced, debug=debug, burns=burns, use_locator=locator)
            else:
                txes = bx.show_txes(sending_address=sender, receiving_address=address_or_deck, start=start, end=end, coinbase=coinbase, advanced=advanced, quiet=quiet, debug=debug, burns=False, use_locator=locator)
        elif burns is True:
            txes = au.my_txes(address=address, deck=address_or_deck, unclaimed=unclaimed, wallet=wallet, keyring=keyring, advanced=advanced, quiet=quiet, debug=debug, burns=True)
        elif reftxes is True:
            txes = au.my_txes(address=address, deck=address_or_deck, unclaimed=unclaimed, wallet=wallet, keyring=keyring, advanced=advanced, quiet=quiet, debug=debug, burns=False)
        elif claims is True:
            txes = eu.show_claims(deck_str=address_or_deck, address=address, wallet=wallet, full=advanced, param=param, quiet=quiet, debug=debug)
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

        elif len(txes) == 0 and not quiet:
            print("No matching transactions found.")


        elif (txids is True) and (not raw):
            if claims is True:
                txes = ([{"txid" : t["TX ID"]} for t in txes]) # TODO: ugly hack, improve this

            if named is True:
                for tx in txes:
                    for k, v in tx.items():
                        try:
                            print({k : provider.decoderawtransaction(v)["txid"]})
                        except KeyError:
                            if not quiet:
                                print("Invalid transaction skipped:", k)


            elif quiet is True:
                print([t["txid"] for t in txes])
            else:
                pprint([t["txid"] for t in txes], max_seq_len=100000)
        elif quiet is True:
            return txes

        elif (param is not None) and not claims:
            try:
                if quiet is True:
                    return [{t["txid"] : t.get(param)} for t in txes]
                else:
                    pprint([{t["txid"] : t.get(param)} for t in txes])
            except KeyError:
                raise ei.PacliInputDataError("Parameter does not exist in the JSON output of this mode, or you haven't entered a parameter. You have to enter the parameter after --param/-p.")
        else:
            for txdict in txes:
                pprint(txdict)

    # the following commands are perhaps subject to be integrated into the normal transaction commands as flags.

    def set_utxo(self,
                 label: str,
                 _value1: str=None,
                 _value2: int=None,
                 modify: bool=False,
                 delete: bool=False,
                 now: bool=False,
                 quiet: bool=False) -> None:

        """Stores a label for the transaction ID and output number (vout) of a specific UTXO. Use mostly for DEX purposes.

        Usage modes:

        pacli transaction set_utxo LABEL TXID OUTPUT

            Stores a label for an UTXO with a TXID and an output number OUTPUT.

        pacli transaction set_utxo NEWLABEL OLDLABEL -m

            Modifies a label for an UTXO.

        pacli transaction set_utxo LABEL -d [--now]

            Deletes a label for an UTXO (--now to delete really).

        Args:

          quiet: Supresses output, printout in script-friendly way.
          modify: Modifies a label.
          delete: Deletes a label/utxo entry (default: dry run, see Usage modes).
          now: In combination with -d, deletes a label permanently.
          _value1: TXID or old label. To be used as a positional argument (flag keyword not mandatory). See Usage modes above.
          _value2: Output. To be used as a positional argument (flag keyword not mandatory). See Usage modes above."""

        txid_or_oldlabel = _value1
        outut = _value2
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

        Args:

          quiet: Suppress additional output."""

        return ce.show("utxo", label, quiet=quiet)

    def list_utxos(self, quiet: bool=False) -> None:
        """Shows all stored UTXOs and their labels.

        Usage:

        pacli transaction list_utxos

        Args:

          quiet: Suppress output, printout in script-friendly way."""

        return ce.list("utxo", quiet=quiet)

