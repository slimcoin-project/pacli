# Tools class, for new pacli commands not directly related to a token type.

from pacli.provider import provider
from pacli.config import Settings
import pacli.config_extended as ce
import pacli.keystore_extended as ke
import pacli.extended_utils as eu
from prettyprinter import cpprint as pprint

class Tools:

    # Addresses
    def store_address(self, label: str, address: str, modify: bool=False) -> None:
        """Stores a label for an address in the extended config file."""
        ke.store_address(label, address=address, modify=modify)
        print("Stored address {} with label {}.".format(address, label))

    def store_address_from_keyring(self, label: str) -> None:
        """Stores a label for an address previously stored in the keyring in the extended config file."""
        print("Searching for label label {} in keyring, and storing its address.".format(label))
        ke.store_address(label)

    def store_addresses_from_keyring(self) -> None:
        """Stores all labels/addresses stored in the keyring in the extended config file."""
        print("Storing all addresses of network", provider.network, "from keyring into extended config file.")
        print("The config file will NOT store private keys. It only allows faster access to addresses.")
        labels = ke.get_labels_from_keyring(provider.network)
        print("Labels retrieved from keyring:", labels)
        # TODO: some legacy labels aren't correctly recognized as legacy,
        # and the algo tries to convert them to the new format.
        # e.g. case of key_bak_testslm02 => bak_testslm02, key_bak_tslm01 => bak_tslm01
        for label in labels:
            ke.store_address(label, full=True)

    def show_address(self, label: str) -> str:
        """Shows stored address given its label."""
        return ke.get_address(label)

    def show_address_label(self, address: str) -> str:
        """Shows label(s) of a stored address (can have multiple values)."""
        return ce.search_value("address", address)[0]

    def show_stored_addresses(self, network: str=None, debug: bool=False) -> None:
        """Show addresses and labels which were stored in the json config file.
        By default, all entries of the current network (blockchain) are shown."""

        addresses = ce.get_config()["address"]
        for fulllabel in addresses:
            addr = addresses[fulllabel]
            lparams = ce.process_fulllabel(fulllabel)
            networkname, label = lparams[0], lparams[1] # lparams["label"], lparams["network"]
            try:
                balance = str(provider.getbalance(addr))
            except TypeError:
                balance = "0"
                if debug:
                    print("No valid balance for address with label {}. Probably not a valid address.".format(label))

            if network and (networkname == network):
                print(label.ljust(16), balance.ljust(16), addr)
            else:
                print(label.ljust(16), networkname.ljust(6), balance.ljust(16), addr)

    def delete_address(self, label: str, network: str=Settings.network, now: bool=False) -> None:
        """Deletes stored address (add --now to delete really)."""
        fulllabel = network + "_" + label
        self.delete_item("address", fulllabel, now=now)

    def get_legacy_address_labels(self, prefix: str=provider.network) -> None:
        """For debugging only."""
        print(ke.get_all_labels(prefix))

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
        eu.prune_old_checkpoints(depth=depth, silent=silent)

    def reorg_check(self) -> None:
        """Performs a chain reorganization check:
        checks if the most recent checkpoint corresponds to the stored block hash."""
        return eu.reorg_check()

    # Decks and proposals

    def store_deck(self, label: str, deckid: str, modify: bool=False) -> None:
        """Stores a deck with label and deckid. Use --modify to change the label."""
        ce.write_item(category="deck", key=label, value=deckid, modify=modify)

    def show_deck(self, label: str) -> str:
        """Shows a stored deck ID by label."""
        deck = ce.read_item(category="deck", key=label)
        return deck

    def show_stored_decks(self) -> None:
        """Shows all stored deck IDs and their labels."""
        pprint(ce.get_config()["deck"])

    def store_proposal(self, label: str, proposal_id: str, modify: bool=False) -> None:
        """Stores a proposal with label and proposal id (TXID). Use --modify to change the label."""
        ce.write_item(category="proposal", key=label, value=proposal_id, modify=modify)

    def show_proposal(self, label: str) -> str:
        """Shows a stored proposal ID (its txid) by label."""
        proposal = ce.read_item(category="proposal", key=label)
        return proposal

    def show_stored_proposals(self) -> None:
        """Shows all stored proposal IDs and their labels."""
        pprint(ce.get_config()["proposal"])

    # Transactions

    def store_transaction(self, label: str, tx_hex: str, modify: bool=False) -> None:
        """Stores a transaction with label and hex string. Use --modify to change the label."""
        ce.write_item(category="transaction", key=label, value=tx_hex, modify=modify)

    def show_transaction(self, label) -> str:
        """Shows a stored transaction hex by label."""
        txhex = ce.read_item(category="transaction", key=identifier)
        return txhex

    def show_stored_transactions(self) -> None:
        """Shows all stored transactions and their labels."""
        pprint(ce.get_config()["transaction"])

    def store_tx_by_txid(self, tx_hex: str) -> None:
        """Stores a transaction's hex string. The TXID is used as label."""
        txid = provider.decoderawtransaction(tx_hex)["txid"]
        print("TXID used as label:", txid)
        ce.write_item(category="transaction", key=txid, value=tx_hex)

    # UTXOs
    def store_utxo(self, label: str, txid: str, output: int, modify: bool=False) -> None:
        """Stores an UTXO with label, txid and output number (vout).
        Use --modify to change the label."""
        utxo = "{}:{}".format(txid, str(output))
        ce.write_item(category="utxo", key=label, value=utxo, modify=modify)

    def show_utxo(self, label: str) -> str:
        """Shows a stored UTXO by its label."""
        return ce.read_item(category="utxo", key=label)

    def show_stored_utxos(self) -> None:
        """Shows all stored UTXOs and their labels."""
        pprint(ce.get_config()["utxo"])


    # General commands

    def update_categories(self, debug: bool=False) -> None:
        """Update the category list of the extended config file."""
        ce.update_categories(debug=debug)

    def delete_item(self, category: str, label: str, now: bool=False) -> None:
        """Deletes an item from the extended config file.
           Specify category and label.
           Use --now to delete really."""
        ce.delete_item(category, label, now)

    def show_config(self) -> list:
        """Shows current contents of the extended configuration file."""
        return ce.get_config()

