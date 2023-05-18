# Tools class, for new pacli commands not directly related to a token type.
# TODO: re-check if we need a way to store ints as keys specifically.
# TODO: (not urgent) there are some commands which are related to the new keystore. Maybe also integrate the extended keystore here, or create a new class (e.g. "keys", "ekeystore", "extkeys" ...?)

from pacli.provider import provider
from pacli.config import Settings
import pacli.config_extended as ce
import pacli.keystore_extended as ke
import pacli.extended_utils as eu
from prettyprinter import cpprint as pprint

class Tools:

    def store_address(self, label: str) -> None:
        print("Storing address for label", label)
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

    def show_label(self, address: str) -> str:
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

    def delete_item(self, category: str, key: str, now: bool=False) -> None:
        ce.delete_item(category, key, now)

    def show_config(self) -> list:
        return ce.get_config()

    def store_checkpoint(self, height: int=None) -> None:
        return eu.store_checkpoint(height=height)

    def show_checkpoint(self, height: int=None) -> str:
        return eu.retrieve_checkpoint(height=height)

    def show_stored_checkpoints(self):
        return eu.retrieve_all_checkpoints()

    def delete_checkpoint(self, height: int=None, now: bool=False):
        ce.delete_item("checkpoint", str(height), now=now)

    def reorg_check(self):
        return eu.reorg_check()

    def store_deck(self, label: str, deckid: str):
        ce.write_item(category="deck", key=label, value=deckid)

    def show_deck(self, label: str):
        deck = ce.read_item(category="deck", key=label)
        print(deck)

    def show_stored_decks(self):
        pprint(ce.get_config()["deck"])

    def store_proposal(self, label: str, proposal_id: str):
        ce.write_item(category="proposal", key=label, value=proposal_id)

    def show_proposal(self, label: str):
        proposal = ce.read_item(category="proposal", key=label)
        print(proposal)

    def show_stored_proposals(self):
        pprint(ce.get_config()["proposal"])

    def store_transaction(self, tx_hex: str):
        txid = provider.decoderawtransaction(tx_hex)["txid"]
        ce.write_item(category="transaction", key=txid, value=tx_hex)

    def store_txhex(self, identifier: str, tx_hex: str):
        ce.write_item(category="txhex", key=identifier, value=tx_hex)

    def show_transaction(self, txid):
        tx = ce.read_item(category="transaction", key=txid)
        print(tx)

    def show_txhex(self, identifier):
        txhex = ce.read_item(category="txhex", key=identifier)
        print(txhex)

    def get_all_legacy_labels(self, prefix: str=provider.network) -> None:
        """For debugging only."""
        print(ke.get_all_labels(prefix))

