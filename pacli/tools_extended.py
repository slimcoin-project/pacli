# Tools class, for new pacli commands not directly related to a token type.

from decimal import Decimal
from pacli.provider import provider
from pacli.config import Settings
import pacli.config_extended as ce
import pacli.keystore_extended as ke
import pacli.extended_commands as ec
import pacli.extended_utils as eu
import pacli.extended_interface as ei
from prettyprinter import cpprint as pprint

class Tools:

    # Addresses
    def store_address(self, label: str, address: str, modify: bool=False) -> None:
        """Stores a label for an address in the extended config file."""
        ec.store_address(label, address=address, modify=modify)
        print("Stored address {} with label {}.".format(address, label))

    def store_address_from_keyring(self, label: str) -> None:
        """Stores a label for an address previously stored in the keyring in the extended config file."""
        print("Searching for label label {} in keyring, and storing its address.".format(label))
        ec.store_address(label)

    def store_addresses_from_keyring(self, network_name: str=Settings.network, replace: bool=False) -> None:
        """Stores all labels/addresses stored in the keyring in the extended config file."""
        print("Storing all addresses of network", network_name, "from keyring into extended config file.")
        print("The config file will NOT store private keys. It only allows faster access to addresses.")
        keyring_labels = ke.get_labels_from_keyring(network_name)
        print("Labels (with prefixes) retrieved from keyring:", keyring_labels)

        for full_label in keyring_labels:
            try:
                ec.store_address(full_label, full=True, replace=replace)
            except ei.ValueExistsError:
                print("Label {} already stored.".format("_".join(full_label.split("_")[2:])))
                continue

    def show_address(self, label: str) -> str:
        """Shows stored address given its label."""
        return ec.get_address(label)

    def show_address_label(self, address: str=Settings.key.address) -> str:
        """Shows label(s) of a stored address (can have multiple values)."""
        return ce.search_value("address", address)[0]

    def show_stored_addresses(self, network_name: str=None, debug: bool=False) -> None:
        """Show addresses and labels which were stored in the json config file.
        By default, all entries of the current network (blockchain) are shown."""

        address_labels = ce.get_config()["address"]
        addresses = []

        for full_label, address in address_labels.items():
            network, label = ce.process_fulllabel(full_label)

            try:
                balance = str(provider.getbalance(address))
            except TypeError:
                balance = "0"
                if debug:
                    print("No valid balance for address with label {}. Probably not a valid address.".format(label))

            if balance != "0":
                balance = balance.rstrip("0")

            if (network_name is None) or (network == network_name):
                addresses.append({"label": label,
                                  "address" : address,
                                  "network" : network,
                                  "balance" : balance})
        ei.print_address_list(addresses)


    def delete_address_label(self, label: str, network: str=Settings.network, now: bool=False) -> None:
        """Deletes stored address (add --now to delete really)."""
        fulllabel = network + "_" + label
        self.delete_item("address", fulllabel, now=now)

    # Checkpoints and reorg tests

    def store_checkpoint(self, height: int=None) -> None:
        """Store a checkpoint (block hash), height is optional."""
        return eu.store_checkpoint(height=height)

    def show_checkpoint(self, height: int=None) -> str:
        """Show a checkpoint (block hash), by default the most recent."""
        return eu.retrieve_checkpoint(height=height)

    def show_stored_checkpoints(self) -> list:
        """Show all checkpoints (block hashes)."""
        return eu.retrieve_all_checkpoints()

    def delete_checkpoint(self, height: int, now: bool=False) -> None:
        """Delete a checkpoint, by height (use --now to delete really)."""
        ce.delete_item("checkpoint", str(height), now=now)

    def prune_old_checkpoints(self, depth: int=2000, silent: bool=False) -> None:
        """Delete all old checkpoints.
        Depth parameter indicates the block depth where checkpoints are to be kept.
        By default, the checkpoints of the 2000 most recent blocks are kept."""
        # TODO: this command is quite slow, optimize it.
        eu.prune_old_checkpoints(depth=depth, silent=silent)

    def reorg_check(self) -> None:
        """Performs a chain reorganization check:
        checks if the most recent checkpoint corresponds to the stored block hash."""
        return eu.reorg_check()

    # Decks, proposals, transactions, UTXOs
    # Use the __store, __show, and __show_stored protected methods.

    def store_deck(self, label: str, deckid: str, modify: bool=False, silent: bool=False) -> None:
        """Stores a deck with label and deckid. Use --modify to change the label."""
        return self.__store("deck", label, value=deckid, silent=silent, modify=modify)

    def show_deck(self, label: str) -> str:
        """Shows a stored deck ID by label."""
        return self.__show("deck", label)

    def show_stored_decks(self, silent: bool=False) -> None:
        """Shows all stored deck IDs and their labels."""
        return self.__show_stored("deck", silent=silent)

    def store_proposal(self, label: str, proposal_id: str, modify: bool=False, silent: bool=False) -> None:
        """Stores a proposal with label and proposal id (TXID). Use --modify to change the label."""
        return self.__store("proposal", label, value=proposal_id, silent=silent, modify=modify)

    def show_proposal(self, label: str) -> str:
        """Shows a stored proposal ID (its txid) by label."""
        return self.__show("proposal", label)

    def show_stored_proposals(self, silent: bool=False) -> None:
        """Shows all stored proposal IDs and their labels."""
        return self.__show_stored("proposal", silent=silent)

    def store_transaction(self, label: str, tx_hex: str, modify: bool=False, silent: bool=False) -> None:
        """Stores a transaction with label and hex string. Use --modify to change the label."""
        return self.__store("transaction", label, value=tx_hex, silent=silent, modify=modify)

    def show_transaction(self, label) -> str:
        """Shows a stored transaction hex by label."""
        return self.__show("transaction", label)

    def show_stored_transactions(self, silent: bool=False) -> None:
        """Shows all stored transactions and their labels."""
        return self.__show_stored("transaction", silent=silent)

    def store_tx_by_txid(self, tx_hex: str, silent: bool=False) -> None:
        """Stores a transaction's hex string. The TXID is used as label."""
        txid = provider.decoderawtransaction(tx_hex)["txid"]
        if not silent:
            print("TXID used as label:", txid)
        return self.__store("transaction", txid, value=tx_hex, silent=silent)

    def store_utxo(self, label: str, txid_or_oldlabel: str, output: int=None, modify: bool=False, silent: bool=False) -> None:
        """Stores an UTXO with label, txid and output number (vout).
        Use --modify to change the label.
        If changing a label directly, omit the output."""
        if modify and (output is None):
            utxo = txid_or_oldlabel
        else:
            utxo = "{}:{}".format(txid_or_oldlabel, str(output))
        return self.__store("utxo", label, value=utxo, silent=silent, modify=modify)

    def show_utxo(self, label: str) -> str:
        """Shows a stored UTXO by its label."""
        return self.__show("utxo", label)

    def show_stored_utxos(self, silent: bool=False) -> None:
        """Shows all stored UTXOs and their labels."""
        return self.__show_stored("utxo", silent=silent)

    # General commands

    def update_categories(self, debug: bool=False) -> None:
        """Update the category list of the extended config file."""
        ce.update_categories(debug=debug)

    def delete_item(self, category: str, label: str, now: bool=False) -> None:
        """Deletes an item from the extended config file.
           Specify category and label.
           Use --now to delete really."""
        return ei.run_command(ce.delete_item, category, label, now=now)

    def show_config(self) -> list:
        """Shows current contents of the extended configuration file."""
        return ce.get_config()

    def show_label(self, category: str, value: str, silent: bool=False):
        """Shows a label for a value."""
        result = ei.run_command(ce.search_value, category, str(value))
        if not result and not silent:
            print("No label was found.")
        elif silent:
            return result
        else:
            print("Label(s) stored for value {}:".format(value))
            pprint(result)


    def find_label(self, category: str, content: str, silent: bool=False):
        """Searches for labels if only a part of the value (content) is known."""
        result = ei.run_command(ce.search_value_content, category, str(content))
        if not result and not silent:
            print("No label was found.")
        elif silent:
            return result
        else:
            print("Entries found with content {}:".format(content))
            pprint(result)

    # Other

    def get_tx_structure(self, txid: str, silent: bool=False):
        """Shows senders (looking at txids in inputs) and receivers of a tx."""
        structure = eu.get_tx_structure(txid)

        if not silent:
            pprint(structure)
        else:
            return structure

    # Helper commands
    def __store(self, category: str, label: str, value: str, modify: bool=False, silent: bool=False):
        return ei.run_command(ce.write_item, category=category, key=label, value=value, modify=modify, silent=silent)

    def __show(self, category: str, label: str):
        return ei.run_command(ce.read_item, category=category, key=label)

    def __show_stored(self, category: str, silent: bool=False):
        cfg = ei.run_command(ce.get_config, silent=silent)
        if silent:
            print(cfg[category])
        else:
            pprint(cfg[category])


