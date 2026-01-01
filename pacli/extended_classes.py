from typing import Union
from decimal import Decimal
from prettyprinter import cpprint as pprint

import pypeerassets as pa
import pypeerassets.at.dt_misc_utils as dmu
import pypeerassets.at.constants as c
from pypeerassets.pautils import exponent_to_amount

import pacli.extended_constants as pc
import pacli.extended_keystore as ke
import pacli.extended_utils as eu
import pacli.at_utils as au
import pacli.extended_commands as ec
import pacli.extended_config as ce
import pacli.extended_interface as ei
import pacli.extended_queries as eq
import pacli.extended_token_queries as etq
import pacli.extended_token_txtools as ett
import pacli.extended_handling as eh
import pacli.dt_commands as dc
import pacli.blockexp as bx
import pacli.blockexp_utils as bu
import pacli.db_utils as dbu ### preliminary!

from pacli.provider import provider
from pacli.config import Settings, default_conf, write_settings, conf_dir, conf_file, write_default_config
from pacli.tui import print_deck_list, print_card_list

# extended_classes contains extensions of the main pacli classes only
# It seems not possible without import conflicts to do it "cleaner"
# the other way around, i.e. defining the Ext.. classes as children
# of the __main__ classes. So it seems to be necessary to comment
# out the methods in __main__ if there's a conflict.

class ExtConfig:

    def set(self,
            label: str,
            value: Union[str, bool]=None,
            delete: bool=False,
            modify: bool=False,
            replace: bool=False,
            now: bool=False,
            quiet: bool=False,
            flush_category: bool=False,
            extended: str=None,
            set_change_policy: bool=False,
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
               (NOTE: In compatibility mode using the basic configuration file, the -r flag can be omitted.)

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
               True and False are case sensitive.
               Compatibility mode will format all outputs of commands like 'vanilla' PeerAssets,
               and ensures the original commands and their flags work as expected.
               Please refer to the original PeerAssets README.

           pacli config set CATEGORY -f [--now]

               Flush (delete) the contents of an entire category. Requires --now, otherwise it will perform a dry run.
               Useful when switching to a new wallet file, to renew the 'address' category.

           pacli config set OPTION -s

               Set extended change policy. Options:
               - newaddress: Creates a new address for each change operation.
               - legacy: Uses PeerAssets policy: either a static change address ("default") or the current main address (see "change" setting).
               NOTE: Occasionally in heavily used wallets the "newaddress" mode may deliver an address which was already used. This applies above all if the wallet is encrypted. In this case it is advised to run the keypoolrefill command.

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
             now: Really delete (in combination with -d, -f) a setting or change a basic setting if compatibility mode is off.
             quiet: Suppress output, printout in script-friendly way.
             value: To be used as a positional argument (flag keyword is not mandatory), see 'Usage modes' above.
             compatibility_mode: Enable or disable compatibility mode. See Usage modes.
             set_change_policy: Enable and set advanced change policy. Options: "newaddress" and "legacy".

"""

        return eh.run_command(self.__set, label, value=value, category=extended, delete=delete, modify=modify, replace=replace, now=now, quiet=quiet, flush_category=flush_category, compatibility_mode=compatibility_mode, change_policy=set_change_policy)

    def __set(self,
              label: str,
              value: Union[str, bool]=None,
              category: str=None,
              delete: bool=False,
              modify: bool=False,
              replace: bool=False,
              now: bool=False,
              quiet: bool=False,
              flush_category: bool=False,
              compatibility_mode: bool=False,
              change_policy: str=None) -> None:

        if flush_category is True:
            category = label
            if not quiet:
                print("WARNING: This deletes the whole content of category '{}' in the extended configuration file.".format(category))
            return ce.flush(category, quiet=quiet, now=now)

        if category is not None or change_policy is True:
            if change_policy is True:
                change_policy_options = ("newaddress", "legacy")
                if ce.show("change_policy", "change_policy", quiet=True) is not None:
                    replace = True
                if label in change_policy_options:
                    value = label
                    category = "change_policy"
                    label = "change_policy"
                    if not quiet:
                        print("Setting change policy to:", value)
                        quiet = True # prevents "duplicate" output
                else:
                    raise eh.PacliInputDataError("Change policy can only be set to the following values: {}".format(change_policy_options))
            if type(category) != str:
                # if -e is given without cat, it gets replaced by a bool value (True).
                raise eh.PacliInputDataError("You have to provide a category if modifying the extended config file.")
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
                print("Compatibility mode affects the output of some original PeerAssets commands,")
                print("but doesn't affect the inner workings nor the extended commands.")

        else:


            if value is None:
                raise eh.PacliInputDataError("No value provided.")
            if modify is True or delete is True:
                raise eh.PacliInputDataError("Modifying labels or deleting them in the basic config file is not permitted.")
            if label not in default_conf.keys():
                if Settings.compatibility_mode == "True":
                    raise ValueError({'error': 'Invalid setting key.'}) # ValueError added # this was mainly for compatibility.
                else:
                    raise eh.PacliInputDataError("Invalid setting key. This label doesn't exist in the basic configuration file. See permitted labels with: 'config list'.")
            if replace is False:
                if Settings.compatibility_mode == "False":
                    # compat mode works without the -r flag.
                    raise eh.PacliInputDataError("Basic settings can only be modified with the --replace/-r flag. New labels can't be added.")

            if not quiet and (Settings.compatibility_mode == "False"):
                print("Changing basic config setting: {} to value: {}.".format(label, value))
                ei.print_red("WARNING: Changing most of these settings can make pacli unusable or lead to strange errors!\nOnly change these settings if you know what you are doing.")
                print("If this happens, change pacli.conf (located in {}) manually.".format(conf_dir))
                print("It is always advisable to make a backup of pacli.conf before any setting is changed.")
                # if not ei.confirm_continuation():
                if not now:
                    print("This is a dry run. Use --now to really change the setting.")
                    return

        write_settings(label, str(value))


    def show(self,
             value_or_label: str,
             label: bool=False,
             find: bool=False,
             quiet: bool=False,
             extended: str=None,
             debug: bool=False):
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
          find: Find label for a string which is present in the value.
          debug: Show exception tracebacks and debug info."""

        return eh.run_command(self.__show, value_or_label, category=extended, label=label, find=find, quiet=quiet, debug=debug)


    def __show(self,
             value_or_label: str,
             category: str=None,
             label: bool=False,
             find: bool=False,
             quiet: bool=False,
             debug: bool=False):


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
                    raise eh.PacliInputDataError("This setting label does not exist in the basic configuration file.")


        elif type(category) != str:
            raise eh.PacliInputDataError("You have to provide a category if showing the extended config file.")

        else:
            if find:
                result = eh.run_command(ce.search_value_content, category, str(value_or_label))
            elif label:
                """Shows a label for a value."""
                result = eh.run_command(ce.search_value, category, str(value_or_label))
            else:
                result = eh.run_command(ce.show, category, value_or_label, quiet=quiet)

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

    def default(self, quiet: bool=False, now: bool=False):
        """Revert the basic configuration file back to default configuration.

        Usage:

            pacli config default [--now]

        NOTE: The extended configuration file has no default setting, so it will not be modified.

        Args:

          quiet: Suppress output.
          now: Confirm the return to the default confirmation."""

        if (quiet is False) and (Settings.compatibility_mode != "True"):
            print("WARNING: Returning to the default configuration can make Pacli unusable.\nYou will have to enter your RPC credentials again in pacli.conf.")
            if not now:
                print("This is a dry run. Use --now to really return to the default confirmation.")
                return

        write_default_config(conf_file)


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
            import_all_keyring_addresses: bool=False,
            check_usage: bool=False,
            unusable: bool=False,
            show_debug_info: bool=False):

        """Sets the current main address or stores / deletes a label for an address.

        Usage modes:

        pacli address set LABEL ADDRESS [-k]

            Without flags, stores a label for an address.
           The label can be stored in the extended configuration file (default) or the local keyring (-k option, Linux/Unix only).

        pacli address set LABEL [-f]

            Without flags, sets the main address to the address named with LABEL.
            If -f/--fresh is used, a new address is generated with label LABEL and set as main address.
            NOTE: Occasionally in heavily used wallets this command may deliver an address which was already used. This applies above all if the wallet is encrypted. In this case it is advised to run the keypoolrefill command.

        pacli address set -a ADDRESS

            Set an address as the current main address.

        pacli address set LABEL -d [--now]

            Deletes a label LABEL for an address.

        pacli address set NEW_LABEL OLD_LABEL -m

            Modifies a label (OLD_LABEL is replaced by NEW_LABEL).

        pacli address set -u

            Locks the main address to prevent the access to any private key via the keyring.
            It deletes the current main key from the keyring and creates an unusable entry.
            Needs to be unlocked with any 'address set' option.

        Args:

          fresh: Creates an address/key with the wallet software, assigns it a label and sets it as the main address.
          check_usage: In combination with -f/--fresh, will check if a new address was already used (can happen in some cases if the node was mining).
          delete: Deletes the specified address label. Use --now to delete really.
          modify: Replaces the label for an address by another one.
          now: Really delete an entry.
          keyring: Use the keyring of the operating system (Linux/Unix only) for the labels. Otherwise the extended configuration file is used.
          to_account: Imports main key or any stored key to an account in the wallet managed by RPC node. Works only with keyring labels.
          import_all_keyring_addresses: Stores all labels/addresses stored in the keyring in the extended config file and imports them to the wallet. -m allows existing entries to be replaced, otherwise they won't be changed.
          quiet: Suppress output, printout in script-friendly way.
          address: Address. To be used as positional argument (flag keyword not mandatory). See Usage modes.
          label: Label. To be used as positional argument (flag keyword not mandatory). See Usage modes.
          unusable: Create an unusable entry in the keyring to lock the main address. See Usage modes.
          show_debug_info: Show debug information.
        """

        kwargs = locals()
        del kwargs["self"]
        kwargs.update({"SETTING_NEW_KEY" : True})
        eh.run_command(self.__set_label, **kwargs)


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
            check_usage: bool=False,
            import_all_keyring_addresses: bool=False,
            unusable: bool=False,
            SETTING_NEW_KEY: bool=False,
            show_debug_info: bool=False):


        if unusable is True:
            ke.set_key("key", ke.UNUSABLE_KEY)
            if not quiet:
                print("Main address locked: unusable key stored in the keyring.")
                print("To unlock, use 'address set' command with any address you like to use.")
            return

        elif label is None and address is None:
            if import_all_keyring_addresses:
                return ec.store_addresses_from_keyring(quiet=quiet, replace=modify)
            else:
                raise eh.PacliInputDataError("No label provided. See -h for options.")

        elif fresh is True:
            return ec.fresh_address(label, set_main=True, backup=None, keyring=keyring, check_usage=check_usage, quiet=quiet)

        elif delete is True:
            """deletes a key with an user-defined label. Cannot be used to delete main key."""
            return ec.delete_label(label, keyring=keyring, now=now)

        elif to_account is not None:
            """creates an account and imports key to it."""
            return ke.import_key_to_wallet(to_account, label)

        elif label is not None and address is not None: # ex: tools store_address
            """Stores a label for an address in the extended config file."""
            ec.set_label(label, address, keyring=keyring, modify=modify, network_name=Settings.network, quiet=quiet)
            return

        else: # set_main
            """Declares a key identified by a label or address as the main one."""
            return ec.set_main_key(label=label, address=address, backup=None, keyring=keyring, quiet=quiet)


    def show(self,
             addr_id: str=None,
             privkey: bool=False,
             pubkey: bool=False,
             wif: bool=False,
             keyring: bool=False,
             label: bool=False,
             burn_address: bool=False,
             debug: bool=False):

        # NOTE: it would be cool to have the --pubkey... option also for labeled addresses, but that may be quite difficult.
        """Shows the address corresponding to a label, or the main address.

        Usage modes:

        pacli address show

            Shows current main address.

        pacli address show LABEL

            Shows address corresponding to label LABEL.

        pacli address show [ADDRESS] -l

            Shows label and address corresponding to address ADDRESS.

        pacli address show -b

            Shows burn address, if the network supports proof-of-burn.

        Args:

          label: Shows label for an address (see Usage options)
          keyring: Use the keyring of your operating system (Linux/Unix only)
          wif: Show private key in Wallet Interchange Format (WIF). Only with --keyring option. (WARNING: exposes private key!)
          privkey: Shows private key. Only with --keyring option. (WARNING: exposes private key!)
          pubkey: Shows public key. Only with --keyring option.
          addr_id: To be used as a positional argument (flag keyword not mandatory). See Usage modes above.
          burn_address: Show burn address. See Usage modes. Cannot be combined with other flags.
          debug: Show additional debug information.
        """

        if burn_address is True:
            return au.burn_address()
        elif label is True:
            """Shows the label of the current main address, or of another address."""
            # TODO: evaluate if the output should really include label AND address, like in the old command.
            if addr_id is None:
                addr_id = ke.get_main_address()
            return eh.run_command(ec.show_label, addr_id, keyring=keyring)

        elif addr_id is not None:
            """Shows a stored alternative address or key.
            --privkey, --pubkey and --wif options only work with --keyring."""

            return eh.run_command(ec.show_stored_address, addr_id, Settings.network, pubkey=pubkey, privkey=privkey, wif=wif, keyring=keyring)

        else:

            return eh.run_command(self.__show, pubkey=pubkey, privkey=privkey, wif=wif, debug=debug)

    def __show(self, pubkey: bool=False, privkey: bool=False, wif: bool=False, debug: bool=False):

            ke.check_main_address_lock()
            if pubkey is True:
                return Settings.key.pubkey
            if privkey is True:
                return Settings.key.privkey
            if wif is True:
                return Settings.key.wif

            return Settings.key.address


    def list(self,
             keyring: bool=False,
             coinbalances: bool=False,
             labels: bool=False,
             full_labels: bool=False,
             named: bool=False,
             p2th: bool=False,
             only_initialized_p2th: bool=False,
             everything: bool=False,
             wallet: bool=False,
             json: bool=False,
             access_wallet: str=None,
             blockchain: str=Settings.network,
             include_all: bool=None,
             quiet: bool=False,
             debug: bool=False):
        """Shows a list of addresses, and optionally balances of coins and/or tokens.

        Usage modes:

        pacli address list

            Shows a table of addresses of the wallet. Includes named addresses and those which contain coins, PoD and PoB tokens.
            If P2TH addresses were named, they will be included in this list, otherwise not.
            NOTE: Due to an upstream bug, some addresses stay hidden (including most change addresses) and may not be shown. You may add the -a flag if this happens to access the wallet file directly (requires berkeleydb package, should be done only in safe environments because wallet data may be exposed to memory!).

        pacli address list -j

            JSON mode. Shows a (prettyprinted) JSON string of all stored addresses and all tokens.

        pacli address list -l [-b CHAIN]
        pacli address list -f [-b CHAIN]

            Shows only the labels which were stored.
            These modes only accept the -b/--blockchain and -k/--keyring additional flags.
            -f/--full_labels shows the labels with the network prefix (useful mainly for debugging).

        Args:

          labels: Show only stored labels.
          full_labels: Show only stored labels with network prefix (debugging option).
          named: Shows only addresses which were named with a label. Addresses which aren't part of the wallet are shown, but balances then cannot be retrieved.
          keyring: Uses the keyring of your operating system.
          coinbalances: Only shows coin balances, not tokens (faster). Cannot be combined with -j, -f and -l.
          blockchain: Only with -l or -f options: Show labels for a specific blockchain network, even if it's not the current one.
          json: JSON mode showing a JSON string, see Usage modes above.
          p2th: Show the P2TH addresses of all decks and all auxiliary P2TH addresses (can be a very long list).
          only_initialized_p2th: Shows P2TH addresses from initialized decks and auxiliary P2TH addresses stored in the wallet.
          include_all: Show all genuine wallet addresses, also those with empty balances which were not named. P2TH are not included.
          wallet: Show all wallet addresses, including P2TH addresses stored in the wallet (like a combination of -i and -o).
          everything: Show all wallet addresses and all P2TH addresses (like a combination of -i and -p), including those related to uninitialized tokens and auxiliary P2TH addresses, but even in this mode some hidden addresses (e.g. change addresses) may not be found. NOTE: If addresses are named and not part of the wallet, they are also shown but their coin balances cannot be retrieved.
          access_wallet: Access wallet file directly. May expose wallet data, so use only in safe environments. Shows also hidden addresses (e.g. change addresses) other modes sometimes don't find. Can be combined with all other flags except -b, -l and -f. Requires the berkeleydb Python package.
          quiet: Suppress output, printout in script-friendly way.
          debug: Show debug information.
        """
        kwargs = locals()
        del kwargs["self"]
        return eh.run_command(self.__list, **kwargs)

    def __list(self,
               keyring: bool=False,
               coinbalances: bool=False,
               labels: bool=False,
               full_labels: bool=False,
               json: bool=False,
               p2th: bool=False,
               only_initialized_p2th: bool=False,
               named: bool=False,
               include_all: bool=None,
               everything: bool=False,
               wallet: bool=False,
               access_wallet: str=None,
               blockchain: str=Settings.network,
               quiet: bool=False,
               debug: bool=False):

        if True not in (labels, full_labels) and (blockchain != Settings.network):
            raise eh.PacliInputDataError("Can't show balances from other blockchains. Only -l and -f can be combined with -b.")

        if True in (labels, full_labels): # labels/full_labels options

            result = eq.get_labels_and_addresses(access_wallet=access_wallet, prefix=blockchain, keyring=keyring, named=True, empty=True, labels=labels, full_labels=full_labels, debug=debug)
            if quiet is True:
                return result
            else:
                if not result:
                    return("No results found.")
                pprint(result)
                return
        else:

            if p2th or only_initialized_p2th or wallet or everything:
                if debug:
                    print("Retrieving decks ...")
                all_decks = pa.find_all_valid_decks(provider, Settings.deck_version, Settings.production)
                if debug:
                    print("Retrieving initialization status ...")
                if only_initialized_p2th: # or wallet: # TODO probably unnecessary if we do not use the include parameter (but also not exclude).
                    decks = etq.get_initialized_decks(all_decks, debug=debug)
                else:
                    decks = all_decks
            else:
                decks, all_decks = None, None

            if debug:
                print("Retrieving P2TH dict ...")
            # if -o option is given, the auxiliary P2THs will be checked for initialization.
            p2th_dict = eu.get_p2th_dict(decks=decks, check_auxiliary=only_initialized_p2th)

            if p2th or only_initialized_p2th:
                include_only, include = p2th_dict.keys(), None
                coinbalances = True
                named_and_nonempty, wallet_only = False, False
                include_all = True if include_all in (None, True) else False
                excluded_addresses = []
                excluded_accounts = []
                add_p2th_account = True
            elif everything or wallet:
                named_and_nonempty, wallet_only = True, wallet
                if everything:
                    include = p2th_dict.keys()
                    if not quiet:
                        print("Note: -e mode shows named non-wallet addresses, but their coin balances can't be retrieved and will be shown as 0. Token balances are shown.")
                else:
                    include = None
                include_all, include_only = True, None
                excluded_addresses = []
                excluded_accounts = []
                add_p2th_account = False
            else: # standard mode: all named + addresses with balance
                include_only, include = None, None
                named_and_nonempty, wallet_only = True, not named # wallet_only will resolve to False if named is chosen, otherwise True
                include_all = False if include_all in (None, False) else True
                excluded_addresses = p2th_dict.keys()
                excluded_accounts = p2th_dict.values()
                add_p2th_account = False


            # TODO: try to improve/unify the location of the deck search.
            deck_list = all_decks if (json and all_decks is not None) else None

            return etq.all_balances(wallet=True,
                                  keyring=keyring,
                                  exclude=excluded_addresses,
                                  excluded_accounts=excluded_accounts,
                                  only_tokens=False,
                                  no_tokens=coinbalances,
                                  add_p2th_account=add_p2th_account,
                                  p2th_dict=p2th_dict,
                                  advanced=json,
                                  named=named,
                                  named_and_nonempty=named_and_nonempty,
                                  wallet_only=wallet_only,
                                  quiet=quiet,
                                  empty=include_all,
                                  include_only=include_only,
                                  include=include,
                                  decks=deck_list,
                                  access_wallet=access_wallet,
                                  debug=debug)

    def balance(self,
                label_or_address: str=None,
                keyring: bool=False,
                integrity_test: bool=False,
                txbalance: bool=False,
                wallet: bool=False,
                json: str=None,
                skip_rpc: bool=False,
                quiet: bool=False,
                debug: bool=False):
        """Shows the balance of an address, by default of the current main address.

        Usage modes:

        pacli address balance

            Shows main address balance.

        pacli address balance LABEL

            Shows balance of the address corresponding to label.

        pacli address balance ADDRESS

            Shows balance of address. Does only work with addresses stored in your wallet file.

        pacli address balance ADDRESS -t [BLOCKHEIGHT]

            Use transaction data to calculate balance.
            This is slow, but often reacts faster than the UTXO set which may require a restart of the client.
            Can be used to calculate a balance at a block height BLOCKHEIGHT.

        pacli address balance -w

            Shows balance of whole wallet.

        pacli address balance [ADDRESS] -i [BLOCKHEIGHT]

            Performs an integrity test comparing blockchain data with output of RPC commands.
            If BLOCKHEIGHT is given, the command will return the balance at this blockheight,
            scanning blocks (and storing new locator data) if necessary.
            If not, the command will return the state from the last scan.

        Args:

           keyring: Use an address stored in the keyring of your operating system.
           wallet: Show balance of the whole wallet, see above.
           txbalance: Use transaction data to calculate balance. Not to be combined with -w.
           integrity_test: Performs an integrity test, comparing blockchain data with the data shown by SLM RPC commands (not in combination with -w).
           address_or_label: To be used as a positional argument (without flag keyword), see "Usage modes" above.
           quiet: Do not output additional information, only the balance.
           debug: Show debug information.
           skip_rpc: Skip RPC txes collection in the intergrity test (only with -i, faster).
           json: Store or load txes to/from json file FILENAME (only with -t and -i, debugging option).
        """

        return eh.run_command(self.__balance,
                              label_or_address=label_or_address,
                              keyring=keyring,
                              integrity_test=integrity_test,
                              txbalance=txbalance,
                              wallet=wallet,
                              json=json,
                              skip_rpc=skip_rpc,
                              quiet=quiet,
                              debug=debug)

    def __balance(self,
                  label_or_address: str=None,
                  keyring: bool=False,
                  integrity_test: bool=False,
                  txbalance: bool=False,
                  wallet: bool=False,
                  json: str=None,
                  skip_rpc: bool=False,
                  quiet: bool=False,
                  debug: bool=False):

        if label_or_address is not None:
            address = ec.process_address(label_or_address, keyring=keyring)

            if address is None:
                raise eh.PacliInputDataError("Label was not found.")

        elif wallet is True:
            address = None
        else:
            address = ke.get_main_address()

        try:
            balance = provider.getbalance(address)
            if (balance == 0) and eu.is_mine(address, debug=debug) is False:
                raise eh.PacliInputDataError("This address is not in your wallet. Command works only for wallet addresses.")
        except TypeError:
            raise eh.PacliInputDataError("Address does not exist.")

        if (integrity_test or txbalance) and not wallet:

            if type(integrity_test) == int:
                lastblockheight = integrity_test
            elif type(txbalance) == int:
                lastblockheight = txbalance
            else:
                lastblockheight = None

            if integrity_test or debug:
                print("Getting RPC txes ...")

            if json and not skip_rpc:
                try:
                    rpc_txes = bx.load_rpc_txes(json, sort=True, unconfirmed=False)
                    if debug:
                        print("Loading transactions from json file ...")
                except FileNotFoundError:
                    rpc_txes = eq.get_address_transactions(addr_string=address, advanced=True, include_coinbase=True, include_p2th=True, sort=True, reverse_sort=True, unconfirmed=False, debug=False)
                    bx.store_rpc_txes(rpc_txes, json)
                    return
            elif not skip_rpc:
                rpc_txes = eq.get_address_transactions(addr_string=address, advanced=True, include_coinbase=True, include_p2th=True, sort=True, reverse_sort=True, unconfirmed=False, debug=False)
            else:
                rpc_txes = None

            if integrity_test:
                return bx.integrity_test([address], rpc_txes, lastblockheight=lastblockheight, debug=debug) # TODO: implement lastblockheight
            elif txbalance:
                txes = [bu.get_tx_structure(tx=tx, human_readable=False, add_txid=True) for tx in rpc_txes]
                lastblockheight = provider.getblockcount() if lastblockheight is None else lastblockheight
                balance_dict = bx.get_balances_from_structs([address], txes, endblock=lastblockheight, debug=debug)
                if lastblockheight not in (0, True) and not quiet:
                    print("Showing state at block height:", lastblockheight)
                balance = balance_dict[address]["balance"]

        if quiet:
            return float(balance)
        pprint(
            {'balance': float(balance)}
            )

    def cache(self,
              _value: str=None,
              blocks: int=50000,
              keyring: bool=False,
              startblock: int=0,
              erase: bool=False,
              chain: bool=False,
              force: bool=False,
              quiet: bool=False,
              view: bool=False,
              all_locators: bool=False,
              prune_orphans: bool=False,
              debug: bool=False):
        """Cache the state of an address.

           Usage:

               pacli address cache ADDRESS [--force]

           Scans the blockchain and stores the blockheights where the address received or sent funds.
           The address can be identified by itself or by an address label.
           If used with -s and there are gaps between caching phases, i.e. your start block is higher than the last checked block, you have to add --force to proceed. Use with caution!

               pacli address cache "[ADDRESS1, ADDRESS2, ...]"

           Cache various addresses. The quotation marks and the brackets are mandatory (Python list format).

               pacli address cache ADDRESS -v
               pacli address cache "[ADDRESS1, ADDRESS2, ...]" -v
               pacli address cache -v -a

           View the currently cached block locators for a single address or list of addresses.
           The -a option shows all stored locators.
           Block locators show the heights of transactions to/from the addresses.

               pacli address cache ADDRESS -e [--force]

           Delete the state of the address ADDRESS.
           Add --force to really delete it, otherwise a dry run is performed.

               pacli address cache -p [--force]

           Prunes orphaned blocks, if one or various cached addresses' last processed block was orphaned.
           Add --force to really prune, otherwise a dry run is performed.

           Args:

             startblock: Block to start the cache process. Use this parameter if you know when the address was first used.
             blocks: Number of blocks to scan. Can be used as a positional argument. Default: 50000 blocks (ignored in combination with -c).
             chain: Scans without block limit (up to the whole blockchain). WARNING: Can take several hours up to days!
             force: Ignore warnings and proceed. See Usage modes.
             erase: Delete address entry in blocklocator.json. To be used when the locator data is faulty or inconsistent.
             prune_orphans: Prunes orphan blocks in blocklocator.json, see Usage section.
             quiet: Suppress output.
             debug: Show additional debug information.
             keyring: Use addresses/label(s) stored in keyring.
             view: Show the current state of the cached blocks.
             all_locators: Show all addresses with locators."""


        return eh.run_command(self.__cache, _value, startblock=startblock, blocks=blocks, chain=chain, keyring=keyring, erase=erase, force=force, quiet=quiet, view=view, all_locators=all_locators, prune_orphans=prune_orphans, debug=debug)


    def __cache(self,
                _value: str=None,
                startblock: int=0,
                blocks: int=50000,
                keyring: bool=False,
                chain: bool=False,
                erase: bool=False,
                force: bool=False,
                view: bool=False,
                all_locators: bool=False,
                prune_orphans: bool=False,
                quiet: bool=False,
                debug: bool=False):

        if type(_value) == str:
            addresses = [ec.process_address(_value, keyring=keyring)]
        elif type(_value) in (list, tuple):
            addresses = [ec.process_address(a, keyring=keyring) for a in _value]
        elif (all_locators is True and view is True) or (prune_orphans is True):
            addresses = None
        else:
            raise eh.PacliInputDataError("No valid address(es) entered.")

        if erase is True:
            return bu.erase_locator_entries(addresses, force=force, quiet=quiet, debug=debug) # TODO: improve this allowing startblock and endblock.
        elif prune_orphans is True:
            return bu.autoprune_orphans_from_locator(force=force, quiet=quiet, debug=debug)
        elif view is True:
            return bx.show_locators(value=addresses, quiet=quiet, debug=debug)
        else:
            if chain:
                blocks = provider.getblockcount() - startblock
                if not quiet:
                    print("Full chain scan selected. WARNING: This can take several days!")
                    print("You can interrupt the scan at any time with KeyboardInterrupt (e.g. CTRL-C) and continue later, calling the same command.")
            return bx.store_address_blockheights(addresses, start_block=startblock, blocks=blocks, force=force, quiet=quiet, debug=debug)


class ExtDeck:

    def set(self,
            label: str,
            id_deck: str=None,
            modify: bool=False,
            delete: bool=False,
            quiet: bool=False,
            now: bool=False):
        """Sets, modifies or deletes a local label for a token (deck).
        The label will be stored in the extended configuration file.

        Usage modes:

            pacli deck set LABEL DECKID
            pacli token set LABEL DECKID

        Sets LABEL for DECKID.

            pacli deck set LABEL -d [--now]
            pacli token set LABEL -d [--now]

        Deletes LABEL from extended configuration file.

            pacli deck set NEW_LABEL OLD_LABEL -m
            pacli token set NEW_LABEL OLD_LABEL -m

        Modifies the label, replacing OLD_LABEL by NEW_LABEL.

        Args:

          modify: Modify the label for a value.
          delete: Delete the specified label. Use --now to delete really.
          quiet: Suppress output, printout in script-friendly way.
          id_deck: Deck/Token ID or old label. To be used as a positional argument (flag keyword not mandatory), see Usage modes above.
        """

        return eh.run_command(self.__setcfg, label=label, id_deck=id_deck, modify=modify, delete=delete, quiet=quiet, now=now)

    def __setcfg(self,
            label: str,
            id_deck: str=None,
            modify: bool=False,
            delete: bool=False,
            quiet: bool=False,
            now: bool=False):

        deckid = id_deck
        if delete is True:
            return ce.delete("deck", label=str(label), now=now)
        elif modify or eu.is_possible_txid(deckid):
            return ce.setcfg("deck", label, deckid, modify=modify, quiet=quiet)
        else:
            raise eh.PacliInputDataError("Value is not a valid deck ID.")


    def list(self,
             burntoken: bool=False,
             podtoken: bool=False,
             attoken: bool=False,
             named: bool=False,
             standard: bool=False,
             only_p2th: bool=False,
             findstring: str=None,
             related: str=None,
             without_initstate: bool=False,
             quiet: bool=False,
             debug: bool=False):
        """Lists all tokens/decks (default), or those of a specified token type, or those with a stored label.

        Note: The token's global 'name' is not guaranteed to be unique. To give a token a (locally) unique identifier, store it with a label.

        Usage:

            pacli deck list
            pacli token list

        List all or a subset of all tokens (decks).
        Note: In compatibility mode, the table of the 'deck list' command without flags is slightly different. It does not include the local label and the initialization status.

            pacli deck list -r ADDRESS
            pacli token list -r ADDRESS

        Lists decks by a related address (P2TH or gateway/burn address).
        Can be combined with other modes.

            pacli deck list -f STRING [-n]
            pacli token list -f STRING [-n]

        Finds decks by a string.
        If used with -n, it only searches in the IDs of the decks stored and labelled locally (faster) and with a simplified output.
        In other options, the string can be present in the deck ID or in the global name.

        Args:

          named: Only show tokens/decks with a stored label.
          quiet: Suppress output, printout in script-friendly way.
          burntoken: Only show PoB tokens (decks).
          podtoken: Only show dPoD tokens (decks).
          standard: Only show the standard dPoD and PoB tokens (decks). Combined with -b, only the standard PoB token is shown, and with -p, only the dPoD token.
          attoken: Only show AT tokens (decks).
          find: Only show tokens (decks) with a certain string in the deck ID or global name. See Usage modes for combination with -n.
          related: Only show tokens (decks) related to an address. See Usage modes.
          without_initstate: Don't show initialized status.
          only_p2th: Shows only the P2TH address of each token (deck). When used with -p, shows all P2TH addresses of the dPoD tokens.
          debug: Show debug information.
        """

        return eh.run_command(self.__list, pobtoken=burntoken, dpodtoken=podtoken, attoken=attoken, named=named, only_p2th=only_p2th, related=related, without_initstate=without_initstate, findstring=findstring, standard=standard, quiet=quiet, debug=debug)

    def __list(self,
             pobtoken: bool=False,
             dpodtoken: bool=False,
             attoken: bool=False,
             named: bool=False,
             only_p2th: bool=False,
             standard: bool=False,
             related: str=None,
             findstring: str=None,
             without_initstate: bool=False,
             quiet: bool=False,
             debug: bool=False):

        show_initialized = False if without_initstate else True

        if standard is True:
            netw = Settings.network

            pob_default = pa.find_deck(provider, pc.DEFAULT_POB_DECK[netw], Settings.deck_version, Settings.production)
            dpod_default = pa.find_deck(provider, pc.DEFAULT_POD_DECK[netw], Settings.deck_version, Settings.production)

            if dpodtoken is True:
                decks = [dpod_default]
                table_title = "Standard dPoD token"
            elif pobtoken is True:
                decks = [pob_default]
                table_title = "Standard PoB token"
            else:
                decks = [pob_default, dpod_default]
                table_title = "Standard PoB and dPoD tokens (in this order)"

        elif findstring is not None and named is True:
            decks = ce.find("deck", findstring, quiet=quiet, debug=debug)
            return

        elif related is not None:

            #if not quiet:
            #    print("Searching for decks related to this address ...")
            decks_related = etq.find_decks_by_address(related, debug=debug)
            decks = [d["deck"] for d in decks_related]
            table_title = "Tokens associated with address {}".format(related)

        elif (pobtoken is True) or (attoken is True):
            decks = list(eh.run_command(dmu.list_decks_by_at_type, provider, c.ID_AT))
            if pobtoken is True:
                table_title = "PoB token decks"
                decks = [d for d in decks if d.at_address == au.burn_address()]
            else:
                table_title = "AT token decks (not including PoB)"
                decks = [d for d in decks if d.at_address != au.burn_address()]

        elif dpodtoken is True:
            decks = list(eh.run_command(dmu.list_decks_by_at_type, provider, c.ID_DT))
            table_title = "dPoD token decks"

        else:
            table_title = "Decks"
            decks = list(eh.run_command(pa.find_all_valid_decks, provider, Settings.deck_version,
                                        Settings.production))

        if findstring is not None:
            decks = [d for d in decks if findstring in d.id or findstring in d.name]
            table_title += " (with string {} in Deck ID or global name)".format(findstring)

        if only_p2th is True:
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

        if Settings.compatibility_mode == "True" and (not named):
            print_deck_list(decks)
        else:
            deck_label_dict = ce.list("deck", quiet=True)
            if named is True and quiet:
                print(deck_label_dict)
                return

            initialized_decks = etq.get_initialized_decks(decks, debug=debug) if show_initialized else []
            deck_list = ei.add_deck_data(decks, deck_label_dict, only_named=named, initialized_decks=initialized_decks, debug=debug)
            if debug:
                print(len(deck_list), "decks found.")
            ei.print_deck_list(deck_list, show_initialized=show_initialized, title=table_title)


    def show(self,
             _idstr: str,
             param: str=None,
             info: bool=False,
             rawinfo: bool=False,
             show_p2th: bool=False,
             xtradata: bool=False,
             checksha256: str=None,
             quiet: bool=False,
             debug: bool=False):
        """Shows or searches a deck stored with a label.

        Usage modes:

            pacli deck show LABEL
            pacli token show LABEL

        Shows token (deck) stored with a local label LABEL.

            pacli deck show STRING -i
            pacli token show STRING -i
            pacli deck show STRING -r
            pacli token show STRING -r

        Displays information about a token (deck). STRING can be a local or global label or an Deck ID.
        With -i, the basic data is displayed in a non-technical manner. -r displays all attributes of the deck object.
        If there is an extradata field present, it will be shown in the Python bytes format (which can be difficult to read, depending on the data).

            pacli deck show STRING -x
            pacli token show STRING -x

        If there is an extradata string, show the extradata string in hex format. STRING can be a local or global label or an Deck ID.

            pacli deck show STRING -x -c DATA
            pacli token show STRING -x -c DATA

        Checks if the extradata field corresponds correctly to the SHA256 hash of DATA.

        Args:

          info: Shows basic information about the deck/token (type, global name, creation block, issuer).
          rawinfo: Shows the Deck object values.
          quiet: Suppress output, printout in script-friendly way.
          param: Shows a specific parameter (only in combination with -r).
          show_p2th: Shows P2TH address(es) (only in combination with -i or -r).
          xtradata: Show extradata string in hex format.
          checksha256: Check sha256 hash of the extradata field.
        """
        return eh.run_command(self.__show, deckstr=_idstr, param=param, info=info, rawinfo=rawinfo, show_p2th=show_p2th, xtradata=xtradata, checksha256=checksha256, quiet=quiet, debug=debug)

    def __show(self,
             deckstr: str,
             param: str=None,
             info: bool=False,
             rawinfo: bool=False,
             show_p2th: bool=False,
             xtradata: bool=False,
             checksha256: str=None,
             quiet: bool=False,
             debug: bool=False):


        # deckid = eu.search_for_stored_tx_label("deck", deckstr, quiet=True)
        deck = eu.search_for_stored_tx_label("deck", deckstr, return_deck=True, quiet=True)


        if True in (info, rawinfo, xtradata):
            deckinfo = eu.get_deckinfo(deck, show_p2th)
            if xtradata is True:
                extradata = deckinfo.get("extradata")
                if extradata is None:
                    print("Token {} with global name {} has no extradata field.".format(deck.id, deck.name))
                else:
                    if not checksha256: # hash is not shown in the quiet check.
                        print(extradata.hex())
                    else:
                        return eu.check_extradata_hash(extradata, checksha256, quiet=quiet, debug=debug)

            elif param is not None:
                print(deckinfo.get(param))
            elif info is True:
                ei.print_deckinfo(deckinfo, burn_address=au.burn_address(), quiet=quiet)
            else:
                pprint(deckinfo)
        elif deck is not None:
            return deck.id

    def init(self,
             id_deck: str=None,
             label: str=None,
             no_label: bool=False,
             all_decks: bool=False,
             cache: int=None,
             quiet: bool=False,
             debug: bool=False) -> None:
        """Initializes a deck (token).

        This is mandatory to be able to use a token with pacli.
        By default, the global deck name is stored as a local label in the extended configuration file.
        IMPORTANT: After initializating a token, the client may still not be aware of this change. It should be restarted with the -rescan option to avoid issues.

        Usage modes:

            pacli deck init
            pacli token init

        Initialize the default PoB and dPoD tokens of this network.

            pacli deck init DECK
            pacli token init DECK

        Initialize a single deck. DECK can be a Deck ID or a label.

            pacli deck init [DECK] -c [BLOCKS] [-a]
            pacli token init [DECK] -c [BLOCKS] [-a]

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
          all_decks: In combination with -c, store blockheights for all initialized tokens/decks.
          id_deck: Deck/Token ID. To be used as a positional argument (flag keyword not mandatory). See Usage modes above.
          cache: Cache the deck's state, storing the blockheights with state changes.
          debug: Show debug information.
        """
        kwargs = locals()
        del kwargs["self"]
        eh.run_command(self.__init, **kwargs)

    def __init(self,
               id_deck: str=None,
               label: str=None,
               no_label: bool=False,
               all_decks: bool=False,
               cache: int=None,
               quiet: bool=False,
               debug: bool=False) -> None:

        idstr = id_deck
        netw = Settings.network

        if idstr is None:
            pob_deck = pc.DEFAULT_POB_DECK[netw]
            dpod_deck = pc.DEFAULT_POD_DECK[netw]

            eu.init_deck(netw, pob_deck, quiet=quiet, no_label=no_label, debug=debug)
            dc.init_dt_deck(netw, dpod_deck, quiet=quiet, no_label=no_label)
            deckid = None
        else:
            deckid = eu.search_for_stored_tx_label("deck", idstr, quiet=quiet, check_initialized=False)
            deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
            if "at_type" in deck.__dict__ and deck.at_type == c.ID_DT:
                dc.init_dt_deck(netw, deckid, quiet=quiet, label=label, debug=debug, no_label=no_label)
            else:
                eu.init_deck(netw, deckid, quiet=quiet, label=label, no_label=no_label, debug=debug)

        if cache:
            if type(cache) == int:
                blocks = cache
            else:
                blocks = 5000
            self.__cache(idstr=deckid, blocks=blocks, all_decks=all_decks, quiet=quiet, debug=debug)


    def cache(self,
              idstr: str=None,
              blocks: int=None,
              chain: bool=False,
              all_decks: bool=False,
              view: bool=False,
              quiet: bool=False,
              debug: bool=False):
        """Stores or shows data about token (deck) state changes (blockheights).

        Usage modes:

            pacli deck cache
            pacli token cache

        Cache deck state info for the standard PoB and dPoD tokens.

            pacli deck cache TOKEN
            pacli token cache TOKEN

        Cache deck state info for a deck. TOKEN can be label or token (deck) ID.

            pacli deck cache -a
            pacli token cache -a

        Cache deck state for all initialized decks.

            pacli deck cache TOKEN -v

        View the state of the block locators for the token TOKEN.

        Args:

          blocks: Number of blocks to store (default: 50000) (ignored in combination with -c).
          chain: Store blockheights for the whole blockchain (since the start block).
          all_decks: Store blockheights for all initialized tokens/decks.
          quiet: Suppress output.
          idstr: Token (deck) label or ID. To be used as a positional argument.
          view: Show the current state of the cached block locators. See Usage modes.
          debug: Show additional debug information."""


        eh.run_command(self.__cache, idstr=idstr, blocks=blocks, chain=chain, all_decks=all_decks, view=view, quiet=quiet, debug=debug)

    def __cache(self, idstr: str, blocks: int=None, chain: bool=False, all_decks: bool=False, view: bool=False, quiet: bool=False, debug: bool=False):

        deckid = eu.search_for_stored_tx_label("deck", idstr, quiet=quiet) if idstr is not None else None

        if view is True:
            return bx.show_locators(value=deckid, quiet=quiet, debug=debug)

        elif all_decks is True:
            decks = list(pa.find_all_valid_decks(provider, Settings.deck_version, Settings.production))
            decks = etq.get_initialized_decks(decks)

        elif deckid is not None:
             decks = [pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)]
        else:
             netw = Settings.network
             decks = [pa.find_deck(provider, pc.DEFAULT_POB_DECK[netw], Settings.deck_version, Settings.production),
                      pa.find_deck(provider, pc.DEFAULT_POD_DECK[netw], Settings.deck_version, Settings.production)]

        if blocks is None and not chain:
            blocks = 50000

        eh.run_command(bx.store_deck_blockheights, decks, quiet=quiet, chain=chain, debug=debug, blocks=blocks)



class ExtCard:

    def list(self, idstr: str, address: str=None, quiet: bool=False, blockheights: bool=False, show_invalid: bool=False, only_invalid: bool=False, valid: bool=False, debug: bool=False):
        """List all transactions (cards or CardTransfers, i.e. issues, transfers, burns) of a token.

        Usage:

            pacli card list TOKEN
            pacli token transfers TOKEN

        TOKEN can be a token (deck) ID or label.
        In standard mode, only valid transfers will be shown.
        In compatibility mode, standard output includes some invalid transfers: those in valid transactions which aren't approved by the Proof-of-Timeline rules.

        Args:

          address: Filter transfers by address. Labels are permitted. If no address is given after -a, use the current main address.
          blockheights: Show block heights instead of showing confirmations.
          quiet: Suppresses additional output, printout in script-friendly way.
          show_invalid: If compatibility mode is turned off, with this flag on also invalid transfers are shown.
          only_invalid: Show only invalid transfers.
          valid: If compatibility mode is turned on, this shows valid transactions according to Proof-of-Timeline rules, where no double spend has been recorded.
          debug: Show debug information."""

        deckid = eh.run_command(eu.search_for_stored_tx_label, "deck", idstr, quiet=quiet) if idstr else None
        return eh.run_command(self.__listext, deckid=deckid, address=address, quiet=quiet, valid=valid, blockheights=blockheights, show_invalid=show_invalid, only_invalid=only_invalid, debug=debug)

    def __listext(self, deckid: str, address: str=None, quiet: bool=False, valid: bool=False, blockheights: bool=False, show_invalid: bool=False, only_invalid: bool=False, debug: bool=False):



        if address:
            if type(address) == bool:
                address = ke.get_main_address()
            else:
                address = ec.process_address(address)

        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

        try:
            cards = pa.find_all_valid_cards(provider, deck)
        except pa.exceptions.EmptyP2THDirectory as err:
            raise eh.PacliDataError(err)

        if Settings.compatibility_mode == "True" or show_invalid == True:
            valid = False
        else:
            valid = True

        if only_invalid is True:
            if not quiet:
                print("Showing only invalid transfers.")
            # result = [t for t in cards if t not in pa.protocol.DeckState(cards).valid_cards]
            clist = list(cards)
            valid_clist = pa.protocol.DeckState(clist).valid_cards
            result = [t for t in clist if (t.txid, t.blockseq, t.cardseq) not in [(t.txid, t.blockseq, t.cardseq) for t in valid_clist]]

        elif valid is True:
            result = pa.protocol.DeckState(cards).valid_cards
        else:
            result = cards

        if address:
            result = [c for c in result if (address in c.sender) or (address in c.receiver)]

        try:
            if blockheights:
                ei.print_card_list_bheights(list(result))
            else:
                print_card_list(list(result))
        except IndexError:
            if not quiet:
                print("No transfers (cards) found.")

    def balances(self,
                param1: str=None,
                category: str=None,
                owners: bool=False,
                tokendeck: str=None,
                named: bool=False,
                json: bool=False,
                wallet: bool=False,
                keyring: bool=False,
                quiet: bool=False,
                debug: bool=False):
        """List the token balances of an address, the whole wallet or all users.

        Usage modes:

            pacli card balances [ADDRESS|-w|-n] -t DECK
            pacli token balances [ADDRESS|-w|-n] -t DECK

        Shows balances of a single token DECK (ID, global name or local label) on wallet addresses (-w), named addresses (-n) or only the specified address.
        If ADDRESS is not given and -w nor -n is not selected, the current main address is used.
        NOTE: This standard mode (without -j or -t) will not work in compatibility mode.

            pacli card balances [ADDRESS|-w|-n]
            pacli token balances [ADDRESS|-w|-n]

        Shows balances of the standard PoB and dPoD tokens.
        If ADDRESS is not given and -w nor -n is not selected, the current main address is used.

            pacli card balances [ADDRESS|-w|-n] -j
            pacli token balances [ADDRESS|-w|-n] -j

        Shows balances of all tokens in JSON format, either on the specified address or on wallet addresses (-w) or named addresses (-n).
        If ADDRESS is not given and -w nor -n is selected, the current main address is used.

            pacli card balances TOKEN -o
            pacli token balances TOKEN -o

        Shows balances of all owners of a token (addresses with cards of this deck) TOKEN (ID, global name or local label).
        Similar to the vanilla 'card balances' command.
        If compatibility mode is active, this is the standard mode and -o is not required; the "normal" standard mode will not work in this mode.
        Note: This command shows a balance of zero if an address has received tokens in the past but then all were moved. If addresses were never used with a token, they won't be shown.

        Args:

          tokendeck: A token (deck) whose balances should be shown. See Usage modes.
          category: In combination with -j, limit results to one of the following token types: PoD, PoB or AT (case-insensitive).
          json: See above. Shows balances of all tokens in JSON format. Not in combination with -o nor -t.
          owners: Show balances of all holders of cards of a token. Cannot be combined with other options except -q.
          keyring: In combination with -j or -t (not -w), use an address stored in the keyring.
          named: Show balances on addresses which are named with labels. Does also show addresses outside of the wallet if -w is not chosen.
          quiet: Suppresses informative messages.
          debug: Display debug info.
          param1: Token (deck) or address. To be used as a positional argument (flag keyword not necessary). See Usage modes.
          wallet: Show balances of all addresses in the wallet."""

        kwargs = locals()
        del kwargs["self"]
        return eh.run_command(self.__balance, **kwargs)

    def __balance(self,
                param1: str=None,
                category: str=None,
                owners: bool=False,
                tokendeck: str=None,
                json: bool=False,
                wallet: bool=False,
                named: bool=False,
                keyring: bool=False,
                quiet: bool=False,
                debug: bool=False):

        if json and not quiet:
                print("Retrieving token states to show balances ...")

        if owners is True or (Settings.compatibility_mode == "True" and not (json or tokendeck)):

            deck_str = param1
            if deck_str is None:
                raise eh.PacliInputDataError("Owner mode requires a token (deck) ID, global name or local label.")

            deckid = eh.run_command(eu.search_for_stored_tx_label, "deck", deck_str, quiet=quiet)

            deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
            cards = pa.find_all_valid_cards(provider, deck)

            state = pa.protocol.DeckState(cards)

            balances = [exponent_to_amount(i, deck.number_of_decimals)
                        for i in state.balances.values()]

            pprint(dict(zip(state.balances.keys(), balances)))

        elif tokendeck is not None: # single token mode
            addr_str = param1
            deck_str = tokendeck
            if not wallet and not named:
                address = ec.process_address(addr_str) if addr_str is not None else ke.get_main_address()
            else:
                address = None
            deckid = eu.search_for_stored_tx_label("deck", deck_str, quiet=quiet)
            return etq.single_balance(deck=deckid, address=address, wallet=wallet, keyring=keyring, quiet=quiet)
        else:
            # TODO seems like label names are not given in this mode if a an address is given.

            if not wallet and not named: # ((wallet or named), param1) == (False, None):
                address = ke.get_main_address() if param1 is None else ec.process_address(param1)
            else:
                address = None
            # address = ec.process_address(param1) if (wallet or named) is False else None
            try:
                deck_type = c.get_deck_type(category.lower()) if category is not None else None
            except AttributeError:
                raise eh.PacliInputDataError("No category specified.")

            # replaced wallet with wallet or named, to trigger "multi address" mode with -n.
            return etq.all_balances(address=address,
                                   wallet=wallet or named,
                                   named=named, keyring=keyring,
                                   only_tokens=True,
                                   advanced=json,
                                   wallet_only=wallet,
                                   deck_type=deck_type,
                                   quiet=quiet,
                                   debug=debug)


    def transfer(self, idstr: str, receiver: str, amount: str, asset_specific_data: str=None, locktime: int=None, change: str=None, sign: bool=None, send: bool=None, verify: bool=False, nocheck: bool=False, force: bool=False, quiet: bool=False, debug: bool=True):
        """Transfer tokens to one or multiple receivers in a single transaction.

        Usage modes:

            pacli card transfer TOKEN RECEIVER AMOUNT
            pacli token transfer TOKEN RECEIVER AMOUNT

        Transfer AMOUNT of a token (deck) TOKEN (ID, global name or label) to a single receiver RECEIVER.

            pacli card transfer TOKEN "[RECEIVER1, RECEIVER2, ...]" "[AMOUNT1, AMOUNT2, ...]"
            pacli token transfer TOKEN "[RECEIVER1, RECEIVER2, ...]" "[AMOUNT1, AMOUNT2, ...]"

        Transfer to multiple receivers. AMOUNT1 goes to RECEIVER1 and so on.
        The brackets are mandatory, but they don't have to be escaped.

        Args:

          change: Specify a change address.
          verify: Verify transaction with Cointoolkit (Peercoin only).
          quiet: Suppress output and printout in a script-friendly way.
          debug: Show additional debug information.
          nocheck: Do not perform a balance check (faster).
          force: Ignore warnings (reorg check etc.) and create the transaction if possible (be careful!).
          sign: Signs the transaction (True by default, use --send=False for a dry run)
          send: Sends the transaction (True by default, use --send=False for a dry run)
        """
        # NOTE: This is not a wrapper of card transfer, so the signature errors from P2PK are also fixed.

        kwargs = locals()
        del kwargs["self"]
        return eh.run_command(self.__transfer, **kwargs)


    def __transfer(self, idstr: str, receiver: str, amount: str, asset_specific_data: str=None, locktime: int=None, change: str=None, nocheck: bool=False, sign: bool=None, send: bool=None, verify: bool=False, force: bool=False, quiet: bool=False, debug: bool=False):

        ke.check_main_address_lock()
        sign, send = eu.manage_send(sign, send)

        if type(receiver) not in (list, tuple, str, int, type(None)) or type(amount) not in (list, tuple, str, int, float):
            raise eh.PacliInputDataError("The receiver and amount parameters have to be strings/numbers or lists.")

        if type(receiver) == str:
            receiver = [receiver]
        if type(amount) in (int, float):
            amount = [Decimal(str(amount))]
        elif type(amount) not in (list, tuple):
            raise eh.PacliInputDataError("Amount must be a number.")

        deckid = eh.run_command(eu.search_for_stored_tx_label, "deck", idstr, quiet=quiet)
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        change_address = ec.process_address(change)

        if receiver is None: # CardBurn: receiver is only None when set by the card burn function or explicitly in card transfer
            receiver_addresses = [deck.issuer]
            if not quiet:
                print("Cards selected for burning: {}".format(amount[0]))
        else:
            receiver_addresses = [ec.process_address(r) for r in receiver]



        if not quiet:
            print("Sending tokens to the following receivers:", receiver)

        return ett.advanced_card_transfer(deck,
                                 amount=amount,
                                 receiver=receiver_addresses,
                                 change=change_address,
                                 locktime=0,
                                 asset_specific_data=None,
                                 sign=sign,
                                 send=send,
                                 balance_check=not nocheck,
                                 force=force,
                                 verify=verify,
                                 debug=debug
                                 )

class ExtTransaction:

    def set(self,
            label_or_tx: str,
            txdata: str=None,
            modify: bool=False,
            delete: bool=False,
            now: bool=False,
            quiet: bool=False,
            show_debug_info: bool=False) -> None:
        """Stores a transaction with a local label and hex string.
           It will be stored in the extended configuration file.

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
             show_debug_info: Show debug information.

        """
        return eh.run_command(self.__set, label_or_tx, tx=txdata, modify=modify, delete=delete, now=now, quiet=quiet, show_debug_info=show_debug_info)

    def __set(self, label_or_tx: str,
            tx: str=None,
            modify: bool=False,
            delete: bool=False,
            now: bool=False,
            quiet: bool=False,
            show_debug_info: bool=False) -> None:

        if delete is True:
            return ce.delete("transaction", label=label_or_tx, now=now)

        if tx is None:
            value = label_or_tx
            if not quiet:
                print("No label provided, TXID is used as label.")
        else:
            # if "tx" is a TXID, get the transaction hex string from blockchain
            value = provider.getrawtransaction(tx)
            if modify or type(value) != str:
                value = tx


        if not modify:
            # we can't do this check with modify enabled, as the value here isn't a TXHEX
            try:
                txid = provider.decoderawtransaction(value)["txid"]
            except KeyError:
                raise eh.PacliInputDataError("Invalid value. This is neither a valid transaction hex string nor a valid TXID.")

        label = txid if (tx is None) and (not modify) else label_or_tx

        return ce.setcfg("transaction", label, value=value, quiet=quiet, modify=modify, debug=show_debug_info)


    def show(self,
             label_or_idstr: str,
             claim: str=None,
             txref: str=None,
             structure: bool=False,
             decode: bool=False,
             opreturn: bool=False,
             id: bool=False,
             utxo_check: bool=False,
             access_wallet: str=None,
             quiet: bool=False):

        """Shows a transaction, by default a stored transaction by its label.

        Usage modes:

        pacli transaction show LABEL

            Shows a transaction stored in the extended config file, by label, as HEX or JSON string (with -d) or a TXID (with -i).

        pacli transaction show TXID

            Shows any transaction's content, as HEX string or (with -d) as JSON string.

        pacli transaction show TXID -s

            Shows senders and receivers of any transaction.

        pacli transaction show TXID -o

            Shows OP_RETURN content of the transaction, if present.

        pacli transaction show TOKEN -c CLAIM_TXID

            Shows parameters of a claim transaction CLAIM_TXID.

        pacli transaction show TOKEN -c -t TXID

            Shows a claim transaction for token TOKEN corresponding to a burn, gateway or donation transaction TXID.

        pacli transaction show TXHEX -u
        pacli transaction show TXID -u
        pacli transaction show TXID:VOUT -u

            Perform a check if UTXOs were already spent or not.
            If the user provides TXID or hex string of a transaction (TXHEX), all inputs of this transaction will be checked.
            Alternatively, the UTXO can be entered directly in the format TXID:VOUT.
            NOTE: Works only with UTXOs that were sent to addresses in the current wallet.
            When checking swap transactions, this means that both exchange partners should run this command to get information about their own UTXOs.

        Args:

           structure: Show senders and receivers (not supported in the mode with LABELs).
           claim: Shows a claim transaction.
           txref: In combination with -c, shows a claim corresponding to a burn, gateway or donation transaction.
           quiet: Suppress output, printout in script-friendly way.
           decode: Show transaction in JSON format (default: hex format).
           opreturn: Show the OP_RETURN byte string(s) in the transaction.
           utxo_check: Show if UTXOs are spent or not (see Usage modes).
           access_wallet: Access wallet file directly. Provide location after -a if the wallet file is not in standard datadir.
           id: Show transaction ID.

        """
        return eh.run_command(self.__show, label_or_idstr, claim=claim, txref=txref, quiet=quiet, structure=structure, opreturn=opreturn, utxo_check=utxo_check, access_wallet=access_wallet, decode=decode, txid=id)

    def __show(self,
               idstr: str,
               claim: str=None,
               txref: str=None,
               structure: bool=False,
               opreturn: bool=False,
               decode: bool=False,
               txid: bool=False,
               utxo_check: bool=False,
               access_wallet: str=None,
               quiet: bool=False):
        # TODO: would be nice to support --structure mode with Labels.

        hexstr = decode is False and structure is False

        if claim:
            if type(claim) == str:
                txes = etq.show_claims(deck_str=idstr, quiet=quiet, claim_tx=claim)
            elif type(claim) == bool and txref is not None:
                txes = etq.show_claims(deck_str=idstr, quiet=quiet, donation_txid=txref)
            else:
                raise eh.PacliInputDataError("You have to provide a claim transaction or the corresponding burn/gateway/donation transaction.")

            if quiet:
                return txes
            else:
                pprint(txes)

        elif utxo_check is True:

             if ":" in idstr:
                txid, vout = idstr.split(":")
                try:
                    utxodata = [(txid, int(vout))]
                except ValueError:
                    raise eh.PacliDataError("UTXO format incorrect. Please provide it in the format TXID:OUTPUT, with OUTPUT being an integer number.")
             else:
                try:
                    if eu.is_possible_txid(idstr):
                        tx = provider.getrawtransaction(idstr, 1)
                    else:
                        tx = provider.decoderawtransaction(idstr)
                    utxodata = []
                    for inp in tx["vin"]:
                        utxodata.append((inp["txid"], inp["vout"]))
                except KeyError:
                    raise eh.PacliInputDataError("Transaction is not stored in the wallet or the data is corrupted.")
             return eh.run_command(eq.utxo_check, utxodata, access_wallet=access_wallet, quiet=quiet)

        elif structure is True or opreturn is True:

            if not eu.is_possible_txid(idstr):
                raise eh.PacliInputDataError("The identifier you provided isn't a valid TXID. The --structure/-s and --opreturn/-o modes currently don't support labels.")

            if structure is True:
                result = eh.run_command(bu.get_tx_structure, txid=idstr)
            elif opreturn is True:
                result = eu.read_all_tx_opreturns(idstr)

            if quiet is True:
                return result
            else:
                pprint(result)

        else:
            result = ce.show("transaction", idstr, quiet=True)
            if result is None:
                try:
                    result = provider.getrawtransaction(idstr)
                    assert type(result) == str
                except AssertionError:
                    if not quiet:
                        raise eh.PacliInputDataError("Unknown transaction identifier. Label wasn't stored or transaction doesn't exist on the blockchain.")

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
             access_wallet: str=None,
             end_height: str=None,
             from_height: str=None,
             origin: str=None,
             param: str=None,
             ids: bool=False,
             keyring: bool=False,
             named: bool=False,
             mempool: bool=None,
             json: bool=False,
             burntxes: bool=None,
             claimtxes: bool=None,
             debug: bool=False,
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
            With -w, all transactions sent or received by the wallet will be shown.
            NOTE: Due to an upstream bug, transactions involving some addresses (most prominently change addresses) may not be shown. You may add the -a flag if this happens to access the wallet file directly (requires berkeleydb package, should be done only in safe environments because wallet data may be exposed to memory!).

        pacli transaction list -n

            Lists transactions stored with a label in the extended config file
            (e.g. for DEX purposes).

        pacli transaction list DECK -b [-o [ORIGIN_ADDRESS]] [-u] [-w]
        pacli transaction list -b [-o [ORIGIN_ADDRESS]] [-w]
        pacli transaction list DECK -g [-o [ORIGIN_ADDRESS]] [-u] [-w]

            Lists burn transactions or gateway TXes (e.g. donation/ICO) for AT/PoB tokens.
            If -o is given, only show those sent from a specific ORIGIN_ADDRESS in the wallet.
            DECK is mandatory in the case of gateway transactions. It can be a label or a deck ID.
            In the case of burn transactions (-b), DECK is only necessary if combined with -u. Without DECK all burn transactions will be listed.
            ORIGIN_ADDRESS is optional. In the case -o is given without address, the main address is used.
            If -w is given, only transactions sent from wallet addresses will be shown.
            If no origin address nor -w is given, all burn/gateway transactions spending from and receiving to any address in your wallet, including P2TH, will be shown.
            NOTE: Due to an upstream bug, transactions involving some addresses (most prominently change addresses) may not be shown. You may add the -a flag if this happens to access the wallet file directly (requires berkeleydb package, should be done only in safe environments because wallet data may be exposed to memory!).

        pacli transaction list DECK [-o ORIGIN_ADDRESS] -c

            List token claim transactions.
            In standard mode, all claim transactions in the blockchain from all senders are shown.
            Alternatively they can be limited to those sent from wallet addresses (-w) or those sent from a specific ORIGIN_ADDRESS (-o) in the wallet.
            DECK can be a label or a deck ID.
            ORIGIN_ADDRESS is optional. In the case -o is given without address, the main address is used.

        pacli transaction list [RECEIVER_ADDRESS] -x [-o ORIGIN_ADDRESS] [-f STARTHEIGHT] [-e ENDHEIGHT]
        pacli transaction list DECK -x -g [-o ORIGIN_ADDRESS] [-f STARTHEIGHT] [-e ENDHEIGHT]
        pacli transaction list DECK -x -b [-o ORIGIN_ADDRESS] [-f STARTHEIGHT] [-e ENDHEIGHT]

            Block explorer mode: List all transactions between two block heights.
            RECEIVER_ADDRESS is optional. ORIGIN_ADDRESS is the address of a sender.
            STARTHEIGHT and ENDHEIGHT can be block heights or dates of block timestamps (format YYYY-MM-DD).
            -f and -e options are not mandatory but highly recommended.
            WARNING: VERY SLOW if used with large block height ranges!

            Notes:
            - In this mode, both ORIGIN_ADDRESS and RECEIVER_ADDRESS can be any address, not only wallet addresses.
            - To use the locator feature -l an origin or receiver address or a deck has to be provided.
            - The mode with DECK only works for AT and PoB tokens together with -g or -b options and tracks the burn or gateway address.

        pacli transaction list [DECK] [ADDRESS] -p PARAM

            Show a single parameter or variable of the transactions, together with the TXID.
            This mode can be combined with all other modes.
            Possible parameters are all first-level keys of the dictionaries output by the different modes of this command.
            If used together with --json, the possible parametes are the first-level keys of the transaction JSON string,
            with the exception of -c/--claims mode, where the attributes of a CardTransfer object can be used.

        Args:

          access_wallet: Access wallet database directly (use only in safe environments, may expose wallet data!). A custom data directory can be given after -a. Cannot be combined with -x, -c, -m nor -s and -r. Requires berkeleydb package. Slow.
          burntxes: Only show burn transactions.
          claimtxes: Show reward claim transactions (see Usage modes) (not to be combined with -x, -b, -g and -a).
          debug: Provide debugging information.
          end_height: Block height or date to end the search at (only in combination with -x).
          from_height: Block height or date to start the search at (only in combination with -x).
          gatewaytxes: Only show transactions going to a gateway address of an AT token.
          ids: Only show transaction ids (TXIDs). If used without -q, 100000 is the maximum length of the list.
          json: Show complete transaction JSON or card transfer dictionary of claim transactions.
          keyring: Use a label of an address stored in the keyring (not supported by -x mode).
          locator: In -x mode, use existing block locators to speed up the blockchain retrieval, while caching uncached blocks in the selected block interval. See Usage modes above. NOTE: No caching will be done if -l is used with the -f flag, because this combination could lead to inconsistent caching.
          zraw: List corresponds to raw output of the listtransactions RPC command (debugging option).
          mempool: Show unconfirmed transactions in the mempool or the wallet. Adding 'only' shows only unconfirmed ones (not in combination with -x).
          named: Show only transactions stored with a label (see Usage modes).
          origin: Show transactions sent by a specific sender address (only necessary in combination with -x, -b, -g and -c).
          param: Show the value of a specific parameter/variable of the transaction.
          quiet: Suppress additional output, printout in script-friendly way.
          sent: Only show sent transactions (not in combination with -n, -c, -b, -g and -a). In block explorer mode (-x), it only works together with -w.
          received: Only show received transactions (not in combination with -n, -c, -b, -g and -a). In block explorer mode (-x), it only works together with -w.
          total: Only count transactions, do not display them.
          unclaimed: Show only unclaimed burn or gateway transactions (only -b and -g, needs a deck to be specified, -x not supported).
          wallet: Show transactions related to addresses in the wallet. See Usage modes for combinations with other options (-n not supported).
          view_coinbase: Include coinbase transactions in the output (not in combination with -n, -c, -b or -g).
          xplore: Block explorer mode (see Usage modes).
          _value1: Deck or address. Should be used only as a positional argument (flag keyword not mandatory). See Usage modes above.
          _value2: Address (in some modes). Should be used only as a positional argument (flag keyword not mandatory). See Usage modes above.
        """
        kwargs = locals()
        del kwargs["self"]
        return eh.run_command(self.__list, **kwargs)

    def __list(self,
             _value1: str=None,
             _value2: str=None,
             access_wallet: str=None,
             burntxes: bool=None,
             claimtxes: bool=None,
             debug: bool=False,
             end_height: str=None,
             from_height: str=None,
             gatewaytxes: bool=None,
             ids: bool=False,
             keyring: bool=False,
             json: bool=False,
             locator: bool=False,
             mempool: bool=None,
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

        # TODO: Further harmonization: Results are now:
        # -x: tx_structure or tx JSON
        # --access_wallet: tx_structure or tx JSON
        # -j: always tx JSON
        # -z: listtransactions output
        # without any label: tx JSON, tx structure or custom dict with main parameters if --sent or --received was used.
        # -c: very custom "embellished" dict, in "basic" mode shows a more "standard" dict
        # NOTE: harmonization of -o done for -c -g and -b it is mandatory now if result should be restricted to an address.

        address_or_deck = _value1
        address = _value2
        ignore_confpar = False
        txstruct = False

        if (burntxes or gatewaytxes or claimtxes) and (origin == True):
            origin = ke.get_main_address()

        # TODO: -c should show senders if -o is not given.

        if address:
            address = ec.process_address(address, keyring=keyring, try_alternative=False)
        if access_wallet is not None:
            # use_db, mempool = True, "ignore"
            use_db = True
            wholetx = True if ids is False else False # when only requesting IDs the getrawtransaction query isn't necessary
            json = json or (not claimtxes and (ids or total))  # if only txids or the count are needed, we don't need the struct. NOTE: doesn't work with claimtxes.
        else:
            use_db = False
        datadir = None if type(access_wallet) == bool else access_wallet # always None when access_wallet is not selected

        if (not named) and (not quiet):
            print("Searching transactions (this can take several minutes) ...")

        if xplore is True:
            if (burntxes is True) or (gatewaytxes is True):
                txes = bx.show_txes(deck=address_or_deck, sending_address=origin, start=from_height, end=end_height, use_locator=locator, burntoken=burntxes, advanced=json, quiet=quiet, debug=debug)
            else:
                if wallet:
                    if sent is True or received is True:
                        wallet_mode = "sent" if sent is True else "received"
                    else:
                        wallet_mode = "all"
                    txes = bx.show_txes(wallet_mode=wallet_mode, start=from_height, end=end_height, coinbase=view_coinbase, advanced=json, use_locator=locator, quiet=quiet, debug=debug)
                else:
                    txes = bx.show_txes(sending_address=origin, receiving_address=address_or_deck, start=from_height, end=end_height, coinbase=view_coinbase, advanced=json, use_locator=locator, quiet=quiet, debug=debug)
        elif (burntxes is True) or (gatewaytxes is True):
            address = au.burn_address() if burntxes is True else None
            deckid = eu.search_for_stored_tx_label("deck", address_or_deck, quiet=quiet) if address_or_deck else None
            txes = au.show_wallet_dtxes(sender=origin, deckid=deckid, unclaimed=unclaimed, wallet=wallet, keyring=keyring, advanced=json, tracked_address=address, access_wallet=access_wallet, quiet=quiet, debug=debug)
        elif claimtxes is True:
            txes = etq.show_claims(deck_str=address_or_deck, address=origin, wallet=wallet, full=json, quiet=quiet, debug=debug)
        elif named is True:
            # Shows all stored transactions and their labels.
            ignore_confpar = True
            txes = ce.list("transaction", quiet=quiet, prettyprint=False, return_list=True)
            if json is True:
                txes = [{key : provider.decoderawtransaction(item[key])} for item in txes for key in item]
        else:
            if wallet or zraw:
                address, wallet = None, True
            else:
                # returns all transactions from or to that address in the wallet.
                address = ke.get_main_address() if address_or_deck is None else address_or_deck

            if use_db is True:
                txstruct = False if json else True
                txes = dbu.get_all_transactions(address=address, sort=True, advanced=json, datadir=datadir, include_coinbase=view_coinbase, wholetx=wholetx, debug=debug)

            else:
                txstruct = False if (json or sent or received) else True
                txes = eq.get_address_transactions(addr_string=address, wallet=wallet, sent=sent, received=received, raw=zraw, advanced=json, keyring=keyring, include_coinbase=view_coinbase, sort=True, txstruct=txstruct, debug=debug)

        if (xplore or burntxes or gatewaytxes or txstruct) and (not json):
            confpar = "blockheight"
        elif claimtxes:
            confpar = "tx_confirmations" if json else "Block height"
        else:
            confpar = "confirmations"

        # mempool can be: None (no option, means only confirmed txes), True (all txes), ignore (all txes without sorting), only (only unconfirmed)
        if mempool in (None, "only") and (xplore != True) and not ignore_confpar:
            if mempool is None: # show only confirmed txes
                txes = [t for t in txes if (confpar in t) and (t[confpar] is not None and t[confpar] > 0)]
                try:
                    # TODO: maybe this should be skipped in cases where previous sorting is done
                    txes.sort(key=lambda d: d[confpar])
                except KeyError:
                    pass
            elif mempool == "only": # show only unconfirmed txes
                txes = [t for t in txes if (confpar not in t) or t[confpar] in (None, 0)]

        if total is True:
            return len(txes)

        elif len(txes) == 0 and not quiet:
            print("No matching transactions found.")

        elif (ids is True) and (not zraw):
            if claimtxes is True and not quiet:
                txes = ([{"txid" : t["Claim transaction ID"]} for t in txes]) # TODO: ugly hack, improve this

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

        elif param is not None:
            msg_additionalparams =  "Some available parameters for this mode:\n{}".format([k for k in txes[0]])
            if param is True:
                raise eh.PacliInputDataError("No parameter was given.\n" + msg_additionalparams)
            txidstr = "Claim transaction ID" if (claimtxes is True and quiet is False) else "txid"
            try:
                result = {t[txidstr] : t.get(param) for t in txes}
                assert set(result.values()) != set([None]) # at least one tx should have a value

            except TypeError: # if the result is an unhashable type this is thrown, but it can be ignored
                pass
            except (KeyError, AssertionError):
                print("Parameter '{}' does not exist in the listed transactions of this mode.".format(param))
                print(msg_additionalparams)
                return

            if quiet is True:
                return result
            else:
                pprint(result)
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
        It will be stored in the extended configuration file.

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

        return eh.run_command(self.__set_utxo, label, _value1, _value2, modify, delete, now, quiet)

    def __set_utxo(self,
                 label: str,
                 _value1: str=None,
                 _value2: int=None,
                 modify: bool=False,
                 delete: bool=False,
                 now: bool=False,
                 quiet: bool=False) -> None:

        txid_or_oldlabel = _value1
        output = _value2

        if delete is True:
            return ce.delete("utxo", str(label), now=now)

        if output is None:
            if modify is True:
                utxo = txid_or_oldlabel
            else:
                raise eh.PacliInputDataError("You need to specify an output number.")

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

