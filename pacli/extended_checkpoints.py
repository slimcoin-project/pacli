# checkpoint functions
import time
import pacli.config_extended as ce
import pacli.extended_interface as ei
from pacli.provider import provider

class Checkpoint:

    def set(self,
            height: int=None,
            delete: bool=False,
            depth: int=2000,
            prune: bool=False,
            silent: bool=False,
            now: bool=False) -> None:
        """Store a checkpoint (block hash) for a given height or the current height (default).

        Usage:

        pacli checkpoint set [HEIGHT]

        Stores a checkpoint, the height becomes the label. If no height is given, the most recent block is used.

        pacli checkpoint set HEIGHT --delete [--now]

        Deletes a checkpoint corresponding to blockheight HEIGHT. Use --now to delete really.

        pacli checkpoint set --prune [--depth=DEPTH]

        Prunes several checkpoints. Depth parameter indicates the block depth where checkpoints are to be kept.
        By default, the checkpoints of the 2000 most recent blocks are kept.

        Other flags:

        --silent: Suppress output."""

        if delete:
            return ce.delete_item("checkpoint", str(height), now=now)
        if prune:


            # TODO: this command is quite slow, optimize it.
            return prune_old_checkpoints(depth=depth, silent=silent)
        else:
            return store_checkpoint(height=height)

    def show(self, height: int=None) -> str:
        """Show a checkpoint (block hash), by default the most recent.

        Usage:

        pacli checkpoint show [--height=HEIGHT]

        HEIGHT is the blockheight to lookup the checkpoint."""
        return retrieve_checkpoint(height=height)

    def list(self) -> list:
        """Show all checkpoints (block hashes)."""
        return retrieve_all_checkpoints()

    def reorg_check(self, silent: bool=False) -> None:
        """Performs a chain reorganization check:
        checks if the most recent checkpoint corresponds to the stored block hash.

        Usage:

        pacli checkpoint reorg_check [--silent]

        Flags:
        --silent: Script friendly output: 0 for passed and 1 for failed check."""
        return reorg_check(silent=silent)


# Checkpoint utils

def store_checkpoint(height: int=None, silent: bool=False) -> None:
    if height is None:
        height = provider.getblockcount()
    blockhash = provider.getblockhash(height)
    if not silent:
        print("Storing hash of block as a checkpoint to control re-orgs.\n Height: {} Hash: {}".format(height, blockhash))
    try:
        ce.write_item(category="checkpoint", key=height, value=blockhash)
    except ei.ValueExistsError:
        if not silent:
            print("Checkpoint already stored (probably node block height has not changed).")

def retrieve_checkpoint(height: int=None, silent: bool=False) -> dict:
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

            if not silent:
                print("No checkpoint for height {}, closest (lower) checkpoint is: {}".format(height, new_height))
            height = new_height

    return {height : config["checkpoint"][str(height)]}

def retrieve_all_checkpoints() -> dict:
    config = ce.get_config()
    checkpoints = sorted(config["checkpoint"].items())
    return checkpoints

def prune_old_checkpoints(depth: int=2000, silent: bool=False) -> None:
    checkpoints = [int(cp) for cp in ce.get_config()["checkpoint"].keys()]
    checkpoints.sort()
    # print(checkpoints)
    current_block = provider.getblockcount()
    index = 0
    if not silent:
        print("Pruning checkpoints up to block {} ({} blocks before the current block {}).".format(current_block - depth, depth, current_block))
    while len(ce.get_config()["checkpoint"]) > 5: # leave at least 5 checkpoints intact
       c = checkpoints[index]
       if c < current_block - depth:
           if not silent:
               print("Deleting checkpoint", c)
           ce.delete_item("checkpoint", str(c), now=True, silent=True)
           time.sleep(1)
       else:
           break # as checkpoints are sorted, we break out.
       index += 1

def reorg_check(silent: bool=False) -> None:
    if not silent:
        print("Looking for chain reorganizations ...")
    config = ce.get_config()

    try:
        bheights = sorted([ int(h) for h in config["checkpoint"] ])
        last_height = bheights[-1]
    except IndexError: # first reorg check
        if not silent:
            print("A reorg check was never performed on this node.")
            print("Saving first checkpoint.")
        return 0

    stored_bhash = config["checkpoint"][str(last_height)]

    if not silent:
        print("Last checkpoint found: height {} hash {}".format(last_height, stored_bhash))
    checked_bhash = provider.getblockhash(last_height)
    if checked_bhash == stored_bhash:
        if not silent:
            print("No reorganization found. Everything seems to be ok.")
        return 0
    else:
        if not silent:
            print("WARNING! Chain reorganization found.")
            print("Block hash for height {} in current blockchain: {}".format(last_height, checked_bhash))
            print("This is not necessarily an attack, it can also occur due to orphaned blocks.")
            print("Make sure you check token balances and other states.")
        return 1
