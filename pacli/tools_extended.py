# Tools class, for example to store recent blockhash.
# TODO: re-check if we need a way to store ints as keys specifically.

from pacli.provider import provider
from pacli.config import Settings
import pacli.config_extended as ce
import pacli.keystore_extended as ke

class Tools:

    def store_address(self, label: str) -> None:
        print("Storing address for label", label)
        ke.store_address(label)

    def store_addresses_from_keyring(self) -> None:
        print("Storing all addresses of network", provider.network, "from keyring into extended config file.")
        print("The config file will NOT store private keys. It only allows faster access to addresses.")
        labels = ke.get_all_labels(provider.network)
        print(labels)
        for label in labels:
            ke.store_address(label, full=True)

    def get_address(self, label: str) -> str:
        return ke.get_address(label)

    def get_all_addresses(self) -> None:
        addresses = ce.get_config()["address"]
        for label in addresses:
           print(label, " - ", addresses[label])

    def delete_item(self, category: str, key: str, now: bool=False) -> None:
        ce.delete_item(category, key, now)

    def get_config(self) -> list:
        return ce.get_config()


    def store_checkpoint(self, height: int=None) -> None:
        if height is None:
            height = provider.getblockcount()
        blockhash = provider.getblockhash(height)
        print("Storing hash of block as a checkpoint to control re-orgs.\n Height: {} Hash: {}".format(height, blockhash))
        ce.write_item(category="checkpoint", key=height, value=blockhash)

    def get_checkpoint(self, height: int=None) -> str:
        # TODO move main part in extended_utils
        config = ce.get_config()
        bheights = sorted([ int(h) for h in config["checkpoint"] ])
        if height is None:
            # default: show latest checkpoint
            height = max(bheights)
        else:
            height = int(height)
            if height not in bheights:
                # if height not in blockheights, show the highest below it
                for i, h in enumerate(bheights):
                    if h > height:
                        new_height = bheights[i-1]
                        break
                else:
                    # if the highest checkpoint is below the required height, use it
                    new_height = bheights[-1]

                print("No checkpoint for height {}, closest (lower) checkpoint is: {}".format(height, new_height))
                height = new_height



        return {height : config["checkpoint"][str(height)]}

    def reorg_check(self):
        # TODO move main part in extended_utils
        print("Looking for reorg.")
        config = ce.get_config()
        bheights = sorted([ int(h) for h in config["checkpoint"] ])
        last_height = bheights[-1]
        stored_bhash = config["checkpoint"][str(last_height)]
        print("Last checkpoint found: height {} hash {}".format(last_height, stored_bhash))
        checked_bhash = provider.getblockhash(last_height)
        if checked_bhash == stored_bhash:
            print("No reorganization found. Everything seems to be ok.")
        else:
            print("WARNING! Chain reorganization found.")
            print("Block hash for height {} in current blockchain: {}".format(last_height, checked_bhash))
            print("This is not necessarily a problem. But make sure you check token balances and other states.")

    def store_deck(self, label: str, deckid: str):
        ce.write_item(category="deck", key=label, value=deckid)

    def get_deck(self, label: str):
        deck = ce.read_item(category="deck", key=label)
        print(deck)

    def store_proposal(self, label: str, proposal_id: str):
        ce.write_item(category="proposal", key=label, value=proposal_id)

    def get_proposal(self, label: str):
        proposal = ce.read_item(category="proposal", key=label)
        print(proposal)







