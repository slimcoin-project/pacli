# Block locator
# Lightweight storage system for relevant blocks
# First concept idea:
# keys are addresses (including P2TH for decks).
# only block heights are stored. A reorg check with the checkpoint list is performed everytime something is stored or read.
# The lastblock parameter refers to a blockhash.

import json, os
from pacli.config import conf_dir
from pacli.provider import provider

LOCATORFILE = os.path.join(conf_dir, "blocklocator.json")

# TODO do we need a "start" parameter too?
# Normally we could say that the start parameter is always the lowest block.

class BlockLocator:

    def __init__(self, address_dict, filename: str=None):

       self.filename = filename if filename is not None else LOCATORFILE
       self.addresses = {}
       for address, values in address_dict.items():
           self.addresses.update({address : BlockLocatorAddress.from_dict(values)})

    @classmethod
    def empty(cls):
        """Returns an empty locator."""
        return cls({})

    @classmethod
    def from_file(cls, locatorfilename: str=None, quiet: bool=False, debug: bool=False) -> dict:
        """Gets the content from the file (list of addresses with block heights)."""

        if locatorfilename is None:
            locatorfilename = LOCATORFILE
        if debug:
           print("Reading locator file ...")
        try:
            with open(locatorfilename, "r") as locatorfile:
                try:
                    return cls(json.load(locatorfile))
                except json.JSONDecodeError as e:
                    if len(locatorfile.read()) == 0:
                        if not quiet:
                            print("Empty locator file.")
                        return cls.empty()
                    else:
                        raise json.JSONDecodeError(e)
        except FileNotFoundError:
            if not quiet:
                print("File does not exist.")
            return cls.empty()

    def to_dict(self):
        result = {}
        for address, values in self.addresses.items():
            result.update({address : values.to_dict()})
        return result

    def get_address(self, address: str):
        if address in self.addresses:
            return self.addresses[address]
        else:
            return BlockLocatorAddress.empty()


    def delete_address(self, address: str):
        try:
            del self.addresses[address]
        except KeyError:
            raise ei.PacliInputDataError("Address not found.")

    def store(self, quiet: bool=False, debug: bool=False):
        """Stores the whole locator dict."""
        if not quiet:
            print("Storing new locator block heights.")
        #if debug:
        #    print("New Locator dict:", self.to_dict()) # very long output, not really necessary as one can check the json file
        with open(self.filename, "w") as locatorfile:
            json.dump(self.to_dict(), locatorfile)

    def store_blockheights(self, address: str, heights: list, lastblockheight: int, lastblockhash: str=None, quiet: bool=False):
        """Updates block heights of an address in the locator file."""
        # Storage should be done always at the end of a block exploring step.
        # locator = get_locator(quiet=quiet)


        if address in self.addresses:
            last_stored_height = self.addresses[address].lastblockheight
            # prevents block heights being overwritten
            if lastblockheight < last_stored_height:
                return
            existing_heights = self.addresses[address].heights
            self.addresses[address].update_lastblock(lastblockheight=lastblockheight, lastblockhash=lastblockhash)
        else:
            existing_heights = []
            # locator.update({address : {"heights" : [], "last" : 0})
            self.addresses.update({address : BlockLocatorAddress.empty(lastblockhash=lastblockhash)})

        new_heights = []

        for height in heights:
            if height in existing_heights:
                continue
            else:
                new_heights.append(height)

        heights = existing_heights + new_heights
        heights.sort()
        # locator[address]["last"] = lastblock

        self.addresses[address].heights = heights


    def prune_orphans(self, cutoff_height: int):
        """Prunes all block heights above a defined cutoff height.
        Should be called by the reorg_check in checkpoints.py."""
        # cutoff height is the LAST block to be conserved.
        # locator = get_locator(quiet=quiet)
        for address, addr_dict in self.addresses.items():
            after_cutoff = [h for h in addr_dict.heights if h > cutoff_height]
            if len(after_cutoff) > 0:
                new_heights = [h for h in addr_dict.heights if h <= cutoff_height]
                self.address[address].heights = new_heights
        # store_locator(locator, quiet=quiet)


class BlockLocatorAddress:

    def __init__(self, heights: list, lastblockhash: str=None, lastblockheight: int=0):
        # Can be initialized with block height or block hash.
        # Hash is stored in the file.
        self.heights = heights
        self.update_lastblock(lastblockhash=lastblockhash, lastblockheight=lastblockheight)


    @classmethod
    def empty(cls, lastblockhash: str=""):
        # Returns empty BlockLocatorAddress
        return cls(heights=[], lastblockhash=lastblockhash)

    def to_dict(self):
        result = {"heights" : self.heights, "lastblock" : self.lastblockhash}
        #if lastblockheight:
        #    result.update({"lastblock" : lastblockheight})
        return result

    @classmethod
    def from_dict(cls, addr_dict):
        return cls(heights=addr_dict["heights"], lastblockhash=addr_dict["lastblock"])

    def update_lastblock(self, lastblockheight: int=None, lastblockhash: str=None):

        if lastblockhash:
            self.lastblockheight = provider.getblock(lastblockhash)["height"]
            self.lastblockhash = lastblockhash
        elif lastblockheight:
            self.lastblockheight = lastblockheight
            self.lastblockhash = provider.getblockhash(lastblockheight)
        else:
            self.lastblockheight = 0
            self.lastblockhash = provider.getblockhash(0)

