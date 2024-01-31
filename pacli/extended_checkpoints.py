# checkpoint functions
import time
import pacli.config_extended as ce
import pacli.extended_interface as ei
from pacli.provider import provider

class Checkpoint:

    def set(self,
            blockheight: int=None,
            delete: bool=False,
            prune: int=None,
            quiet: bool=False,
            now: bool=False) -> None:
        """Store a checkpoint (block hash) for a given height or the current height (default).

        Usage:

        pacli checkpoint set [HEIGHT]

        Stores a checkpoint, the height becomes the label. If no height is given, the most recent block is used.

        pacli checkpoint set HEIGHT --delete [--now]

        Deletes a checkpoint corresponding to blockheight HEIGHT. Use --now to delete really.

        pacli checkpoint set --prune [DEPTH]

        Prunes several checkpoints. DEPTH indicates the block depth where checkpoints are to be kept.
        By default, the checkpoints of the 2000 most recent blocks are kept.

        Other flags:

        -q / --quiet: Suppress output."""

        if delete:
            return ce.delete_item("checkpoint", str(blockheight), now=now, quiet=quiet)
        if prune:
            if type(prune) != int:
                prune = 2000 # default value
            # TODO: this command is quite slow, optimize it.
            return ei.run_command(prune_old_checkpoints, depth=prune, quiet=quiet)
        else:
            return ei.run_command(store_checkpoint, height=blockheight, quiet=quiet)

    def show(self, height: int=None) -> str:
        """Show a checkpoint (block hash), by default the most recent.

        Usage:

        pacli checkpoint show [BLOCKHEIGHT]

        BLOCKHEIGHT is the blockheight to lookup the checkpoint."""
        return ei.run_command(retrieve_checkpoint, height=height)

    def list(self) -> list:
        """Show all checkpoints (block hashes)."""
        return ei.run_command(retrieve_all_checkpoints)

    def reorg_check(self, quiet: bool=False) -> None:
        """Performs a chain reorganization check:
        checks if the most recent checkpoint corresponds to the stored block hash.

        Usage:

        pacli checkpoint reorg_check [--quiet]

        Flags:
        -q, --quiet: Script friendly output: 0 for passed and 1 for failed check."""
        return ei.run_command(reorg_check, quiet=quiet)


# Checkpoint utils

def store_checkpoint(height: int=None, quiet: bool=False) -> None:
    if height is None:
        height = provider.getblockcount()
    elif type(height) != int:
        raise ei.PacliInputDataError("You can only save a checkpoint block height as a integer number. Please provide a valid block height.")

    blockhash = provider.getblockhash(height)
    if not quiet:
        print("Storing hash of block as a checkpoint to control re-orgs.\n Height: {} Hash: {}".format(height, blockhash))
    try:
        ce.set("checkpoint", label=height, value=blockhash, quiet=quiet)
    except ei.ValueExistsError:
        if not quiet:
            print("Checkpoint already stored (probably node block height has not changed).")

def retrieve_checkpoint(height: int=None, quiet: bool=False) -> dict:
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

            if not quiet:
                print("No checkpoint for height {}, closest (lower) checkpoint is: {}".format(height, new_height))
            height = new_height

    return {height : config["checkpoint"][str(height)]}

def retrieve_all_checkpoints() -> dict:
    config = ce.get_config()
    checkpoints = sorted(config["checkpoint"].items())
    return checkpoints

def prune_old_checkpoints(depth: int=2000, quiet: bool=False) -> None:
    checkpoints = [int(cp) for cp in ce.get_config()["checkpoint"].keys()]
    checkpoints.sort()
    # print(checkpoints)
    current_block = provider.getblockcount()
    index = 0
    if not quiet:
        print("Pruning checkpoints up to block {} ({} blocks before the current block {}).".format(current_block - depth, depth, current_block))
    while len(ce.get_config()["checkpoint"]) > 5: # leave at least 5 checkpoints intact
       c = checkpoints[index]
       if c < current_block - depth:
           if not quiet:
               print("Deleting checkpoint", c)
           ce.delete_item("checkpoint", str(c), now=True, quiet=True)
           time.sleep(1)
       else:
           break # as checkpoints are sorted, we break out.
       index += 1

def reorg_check(quiet: bool=False) -> None:
    if not quiet:
        print("Looking for chain reorganizations ...")
    config = ce.get_config()

    try:
        bheights = sorted([ int(h) for h in config["checkpoint"] ])
        last_height = bheights[-1]
    except IndexError: # first reorg check
        if not quiet:
            print("A reorg check was never performed on this node.")
            print("Saving first checkpoint.")
        else:
            return 0

    stored_bhash = config["checkpoint"][str(last_height)]

    if not quiet:
        print("Last checkpoint found: height {} hash {}".format(last_height, stored_bhash))
    checked_bhash = provider.getblockhash(last_height)
    if checked_bhash == stored_bhash:
        if not quiet:
            print("No reorganization found. Everything seems to be ok.")
        else:
            return 0
    else:
        if not quiet:
            print("WARNING! Chain reorganization found.")
            print("Block hash for height {} in current blockchain: {}".format(last_height, checked_bhash))
            print("This is not necessarily an attack, it can also occur due to orphaned blocks.")
            print("Make sure you check token balances and other states.")
        else:
            return 1
