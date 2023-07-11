# Tools class, for new pacli commands not directly related to a token type.

from pacli.provider import provider
from pacli.config import Settings
import pacli.config_extended as ce
import pacli.keystore_extended as ke
import pacli.extended_utils as eu
from prettyprinter import cpprint as pprint

class Tools:

    # Addresses
    def store_address(self, label: str, address: str) -> None:
        ke.store_address(label, address=address)
        print("Stored address {} with label {}.".format(address, label))

    def store_address_from_keyring(self, label: str) -> None:
        print("Searching for label label {} in keyring, and storing its address.".format(label))
        ke.store_address(label)

    def store_addresses_from_keyring(self) -> None:
        print("Storing all addresses of network", provider.network, "from keyring into extended config file.")
        print("The config file will NOT store private keys. It only allows faster access to addresses.")
        labels = ke.get_labels_from_keyring(provider.network)
        print("Labels retrieved from keyring:", labels)
        for label in labels:
            ke.store_address(label, full=True)

    def show_address(self, label: str) -> str:
        return ke.get_address(label)

    def show_address_label(self, address: str) -> str:
        return ce.search_value("address", address)[0]

    def show_stored_addresses(self, network: str=None) -> None:
        """Get all addresses from this wallet which were stored in the json config file."""
        addresses = ce.get_config()["address"]
        for fulllabel in addresses:
            addr = addresses[fulllabel]
            lparams = ce.process_fulllabel(fulllabel)
            label, networkname = lparams[0], lparams[1] # lparams["label"], lparams["network"]
            balance = str(provider.getbalance(addr))

            if network and (networkname == network):
                print(label.ljust(16), balance.ljust(16), addr)
            else:
                print(label.ljust(16), networkname.ljust(6), balance.ljust(16), addr)

    def get_legacy_address_labels(self, prefix: str=provider.network) -> None:
        """For debugging only."""
        print(ke.get_all_labels(prefix))

    # Checkpoints and reorg tests

    def store_checkpoint(self, height: int=None) -> None:
        return eu.store_checkpoint(height=height)

    def show_checkpoint(self, height: int=None) -> str:
        return eu.retrieve_checkpoint(height=height)

    def show_stored_checkpoints(self) -> list:
        return eu.retrieve_all_checkpoints()

    def delete_checkpoint(self, height: int=None, now: bool=False) -> None:
        ce.delete_item("checkpoint", str(height), now=now)

    def prune_old_checkpoints(self, depth: int=2000, silent: bool=False) -> None:
        eu.prune_old_checkpoints(depth=depth, silent=silent)

    def reorg_check(self) -> None:
        return eu.reorg_check()

    # Decks and proposals

    def store_deck(self, label: str, deckid: str) -> None:
        ce.write_item(category="deck", key=label, value=deckid)

    def show_deck(self, label: str) -> str:
        deck = ce.read_item(category="deck", key=label)
        return deck

    def show_stored_decks(self) -> None:
        pprint(ce.get_config()["deck"])

    def store_proposal(self, label: str, proposal_id: str) -> None:
        ce.write_item(category="proposal", key=label, value=proposal_id)

    def show_proposal(self, label: str) -> str:
        proposal = ce.read_item(category="proposal", key=label)
        return proposal

    def show_stored_proposals(self) -> None:
        pprint(ce.get_config()["proposal"])

    # Transactions

    def store_transaction(self, label: str, tx_hex: str) -> None:
        ce.write_item(category="transaction", key=label, value=tx_hex)

    def show_transaction(self, label) -> str:
        txhex = ce.read_item(category="transaction", key=identifier)
        return txhex

    def show_stored_transactions(self) -> None:
        pprint(ce.get_config()["transaction"])

    def store_tx_by_txid(self, tx_hex: str) -> None:
        txid = provider.decoderawtransaction(tx_hex)["txid"]
        print("TXID used as label:", txid)
        ce.write_item(category="transaction", key=txid, value=tx_hex)

    # UTXOs
    def store_utxo(self, label: str, txid: str, output: int) -> None:
        utxo = "{}:{}".format(txid, str(output))
        ce.write_item(category="utxo", key=label, value=utxo)

    def show_utxo(self, label: str) -> str:
        return ce.read_item(category="utxo", key=label)

    def show_stored_utxos(self) -> None:
        pprint(ce.get_config()["utxo"])


    # General commands

    def update_categories(self, debug: bool=False) -> None:
        ce.update_categories(debug=debug)

    def delete_item(self, category: str, key: str, now: bool=False) -> None:
        ce.delete_item(category, key, now)

    def show_config(self) -> list:
        return ce.get_config()

