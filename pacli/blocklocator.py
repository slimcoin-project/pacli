# Block locator
# Lightweight storage system for relevant blocks
# First concept idea:
# keys are addresses (including P2TH for decks).
# only block heights are stored. A reorg check with the checkpoint list is performed everytime something is stored or read.
# The lastblock parameter refers to a blockhash.

import json, os
import pacli.extended_handling as eh
from pacli.config import conf_dir
from pacli.provider import provider

LOCATORFILE = os.path.join(conf_dir, "blocklocator.json")

# NOTES:
# - start and discontinuous attributes from BlockLocatorAddress will only be stored if necessary.
# - ignore_orphans must only be used when reading or pruning orphans in the locator, as it will change the locator data.

class BlockLocator:

    def __init__(self, address_dict, filename: str=None, ignore_orphans: bool=False):

       self.filename = filename if filename is not None else LOCATORFILE
       self.addresses = {}
       for address, values in address_dict.items():
           self.addresses.update({address : BlockLocatorAddress.from_dict(values, ignore_orphans=ignore_orphans)})

    @classmethod
    def empty(cls):
        """Returns an empty locator."""
        return cls({})

    @classmethod
    def from_file(cls, locatorfilename: str=None, ignore_orphans: bool=False, quiet: bool=False, debug: bool=False) -> dict:
        """Gets the content from the file (list of addresses with block heights)."""

        if locatorfilename is None:
            locatorfilename = LOCATORFILE
        if debug:
           print("Reading locator file ...")
        try:
            with open(locatorfilename, "r") as locatorfile:
                try:
                    param_dict = json.load(locatorfile)
                    return cls(param_dict, ignore_orphans=ignore_orphans)
                except json.JSONDecodeError as e:
                    if len(locatorfile.read()) == 0:
                        if not quiet:
                            print("Empty locator file.")
                        return cls.empty()
                    else:
                        raise json.JSONDecodeError(e)
        except FileNotFoundError:
            if debug:
                print("Locator file does not exist.")
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
            raise eh.PacliInputDataError("Address not found in the locator file.")

    def store(self, quiet: bool=False, debug: bool=False):
        """Stores the whole locator dict."""
        if debug:
            print("Storing locator data on file.")
        #if debug:
        #    print("New Locator dict:", self.to_dict()) # very long output, not really necessary as one can check the json file
        with open(self.filename, "w") as locatorfile:
            json.dump(self.to_dict(), locatorfile)

    def store_blockheights(self, address: str, heights: list, lastblockheight: int, startheight: int=0, lastblockhash: str=None, quiet: bool=False, debug: bool=False):
        """Updates block heights of an address in the locator file."""
        # Storage should be done always at the end of a block exploring step.
        # discontinuous attribute is stored in this step.

        discontinuous = False
        if address in self.addresses:
            last_stored_height = self.addresses[address].lastblockheight
            stored_startheight = self.addresses[address].startheight
            # prevents block heights being overwritten
            if lastblockheight < last_stored_height:
                if debug:
                    print("Caching process ignored for address {}: stored lastblockheight {} is higher than the last cached block {}.".format(address, last_stored_height, lastblockheight))
                return
            if lastblockheight < stored_startheight:
                if debug:
                    print("Caching process ignored for address {}: stored startheight {} is higher than the last cached block {}.".format(address, stored_startheight, lastblockheight))
                return
            stored_tx_heights = self.addresses[address].heights
            max_height = max(stored_tx_heights) if stored_tx_heights else 0

            if lastblockheight < max_height:
                if debug:
                    print("Lastblockheight {} ignored for address {}: highest stored block {} is higher and becomes new lastblockheight.".format(lastblockheight, address, max_height))
                lastblockheight, lastblockhash = max_height, None
            if (last_stored_height > 0) and (startheight > (last_stored_height + 1)):
                if debug:
                    print("Address {} marked as discontinuously scanned: Last stored height was {}, but the last scanning process started at block {}.".format(address, lastblockheight, startheight))
                discontinuous = True

            self.addresses[address].update_lastblock(lastblockheight=lastblockheight, lastblockhash=lastblockhash)
            if discontinuous:
                self.addresses[address].discontinuous = discontinuous
            elif self.addresses[address].discontinuous == True and startheight == 0:
                # edge case: if the address is cached completely again we can get rid of the discontinuous marker
                # It's unfortunately not possible with the current setup to remove it when the startheight is above 0.
                self.addresses[address].discontinupus = False
        else:
            stored_tx_heights = []
            self.addresses.update({address : BlockLocatorAddress.empty(lastblockhash=lastblockhash, startheight=startheight)})

        new_heights = []

        for height in heights:
            if height in stored_tx_heights:
                continue
            else:
                new_heights.append(height)

        heights = stored_tx_heights + new_heights
        heights.sort()
        self.addresses[address].heights = heights

    def prune_orphans(self, cutoff_height: int, quiet: bool=False, debug: bool=False) -> int:
        """Prunes all block heights above a defined cutoff height.
           Returns the number of pruned orphans."""
        # cutoff height is the LAST block to be conserved.
        # NOTE: this uses a workaround: processes the lastblockheight values
        # and those set to None are changed to the cutoff height.
        # We thus assume that the setting to None was done by the pruning algorithm.
        try:
            cutoff_hash = provider.getblockhash(cutoff_height) # this seems to be necessary to get the range
        except:
            raise eh.PacliInputDataError("Block height {} out of range.".format(cutoff_height))
        changed_addresses = 0
        for address, addr_obj in self.addresses.items():
            if debug:
                print("Processing address: {}, Lastblockheight: {}".format(address, addr_obj.lastblockheight))
            after_cutoff = [h for h in addr_obj.heights if h > cutoff_height]
            if len(after_cutoff) > 0:
                if not quiet or debug:
                    print("Pruning BlockLocator for address {} - erased heights:".format(address), after_cutoff)
                new_heights = [h for h in addr_obj.heights if h <= cutoff_height]
                self.addresses[address].heights = new_heights
                self.addresses[address].update_lastblock(lastblockheight=cutoff_height)
                changed_addresses += 1
            elif addr_obj.lastblockheight is None: # see above
                self.addresses[address].update_lastblock(lastblockheight=cutoff_height)
                changed_addresses += 1
        if not quiet:
            if changed_addresses > 0:
                print("Pruned orphans in {} address entries in blocklocator.json.".format(changed_addresses))
            else:
                print("No orphans were pruned from blocklocator.json.")
        return changed_addresses

    def get_address_data(self, address_list: list, debug: bool=False) -> tuple:
        # returns a list of all block heights of the address list and the last block
        heights = []
        lastblocks = []
        for address in address_list:
            if (address is not None) and (address in self.addresses):
                heights += self.addresses[address].heights
                lastblocks.append(self.addresses[address].lastblockheight)
        if heights:
            heights = sorted(set(heights))
        if lastblocks:
            lastblock = min(lastblocks)
        else:
            lastblock = 0
        return heights, lastblock

    def force_startblock(self, address_list: list, startblock: int, debug: bool=False) -> None:
        for address in address_list:
            if address not in self.addresses:
                self.addresses.update({address : BlockLocatorAddress.empty(startheight=startblock)})
            else:
                self.addresses[address].reset()
                self.addresses[address].startheight = startblock
            # The lastblockheight will be set to one block before the startblock.
            # This prevents caching before that height.
            # TODO this could also be skipped, but then the other functions would have to be aware of the startblock value.
            # self.addresses[address].update_lastblock(lastblockheight = startblock - 1)

class BlockLocatorAddress:

    def __init__(self,
                 heights: list,
                 startheight: int=0,
                 discontinuous: bool=False,
                 lastblockhash: str=None,
                 lastblockheight: int=0,
                 ignore_orphans: bool=False):
        # Can be initialized with block height or block hash.
        # Hash is stored in the file.
        self.heights = heights
        self.startheight = startheight
        self.discontinuous = discontinuous
        self.update_lastblock(lastblockhash=lastblockhash, lastblockheight=lastblockheight, ignore_orphans=ignore_orphans)


    @classmethod
    def empty(cls, lastblockhash: str="", startheight: int=None, discontinuous: bool=False):
        # Returns empty BlockLocatorAddress
        kwargs = {}
        if startheight is not None:
            kwargs.update({"startheight" : startheight})
        if discontinuous is True:
            kwargs.update({"discontinuous" : True})
        return cls(heights=[], lastblockhash=lastblockhash, **kwargs)

    def to_dict(self):
        result = {"heights" : self.heights, "lastblock" : self.lastblockhash}
        if self.startheight:
            result.update({"startheight" : self.startheight})
        if self.discontinuous:
            result.update({"discontinuous" : self.discontinuous})
        return result

    @classmethod
    def from_dict(cls, addr_dict: dict, ignore_orphans: bool=False):
        startheight = addr_dict["startheight"] if "startheight" in addr_dict else 0
        discontinuous = addr_dict["discontinuous"] if "discontinuous" in addr_dict else False
        return cls(heights=addr_dict["heights"],
                  startheight=startheight,
                  discontinuous=discontinuous,
                  lastblockhash=addr_dict["lastblock"],
                  ignore_orphans=ignore_orphans)

    def update_lastblock(self, lastblockheight: int=None, lastblockhash: str=None, ignore_orphans: bool=False):

        if lastblockhash:
            try:
                self.lastblockheight = provider.getblock(lastblockhash)["height"]
            except KeyError: # can happen after orphaned blocks
                # NOTE: ignore_orphans automatically affects all affected addresses with an orphan as lastblockhash, sets their lastblock to None.
                if ignore_orphans:
                    self.lastblockheight = None
                    self.lastblockhash = None
                else:
                    err_msg = "Last processed block {} not found in your current chain.\nProbably this means it was orphaned.\nPrune orphans with 'address cache -p'.".format(lastblockhash)
                    raise eh.PacliInputDataError(err_msg)
            self.lastblockhash = lastblockhash
        elif lastblockheight:
            self.lastblockheight = lastblockheight
            self.lastblockhash = provider.getblockhash(lastblockheight)
        else:
            self.lastblockheight = 0
            self.lastblockhash = provider.getblockhash(0)

    def reset(self):
        # allows to set all values to 0
        self.update_lastblock() # this resets the block heights to 0
        self.discontinuous = False
        self.startheight = 0
        self.heights = []


