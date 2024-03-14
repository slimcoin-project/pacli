import json, os
import pacli.extended_interface as ei
from prettyprinter import cpprint as pprint
from pacli.config import conf_dir, Settings

# This stores some settings in an additional config file, for example short keys for addresses, proposals, decks etc.
# An alternative for the future could be to use sqlite3 eventually.

EXT_CONFIGFILE = os.path.join(conf_dir, "extended_config.json")
CATEGORIES = ["address", "checkpoint", "deck", "proposal", "donation", "transaction", "utxo"]
CAT_INIT = {c : {} for c in CATEGORIES}

# Common error messages
ERR_NOCAT = "Category does not exist or is missing. See list of available categories with 'pacli config list -e -c'."

# modes:
# "replace" : value gets replaced, key stays the same
# "modify" : label gets replaced (entry is deleted and a new entry is generated)
# "add" : an item is added to a list
# "protect" : only allows additions of new labels, no modifications (default)
MODES = ["replace", "modify", "add", "protect"]

def get_config(configfilename: str=EXT_CONFIGFILE, quiet: bool=False) -> dict:

    try:
        with open(configfilename, "r") as configfile:
            try:
                return json.load(configfile)
            except json.JSONDecodeError as e:
                if len(configfile.read()) == 0:
                    if not quiet:
                        print("Empty file. Returning default config.")
                    return CAT_INIT
                else:
                    raise json.JSONDecodeError(e)
    except FileNotFoundError:
        if not quiet:
            print("File does not exist. Returning default config.")
        return CAT_INIT


def write_item(category: str, key: str, value: str, configfilename: str=EXT_CONFIGFILE, network_name: str=None, modify: bool=False, add: bool=False, replace: bool=False, quiet: bool=False, debug: bool=False) -> None:


    # --modify: modifies a label (first argument is new label, old label or value is given as second argument)
    # --replace: modifies a value associated with a label (first argument is label, new value is given as second argument)

    # to allow simple command line arguments and avoid additional per-command processing,
    # this listcomp generates the mode from the add and modify bool variables.
    # the True value at the end means that "protect" (MODES[-1]) is the default.
    mode = [MODES[i] for i, m in enumerate([replace, modify, add, True]) if m][0]

    config = get_config(configfilename)

    if mode == "modify":
        # first, we look if the given value is an old key.
        if category == "address":
            old_key = network_name + "_" + value
            value_as_key = old_key in config[category]
        else:
            value_as_key = value in config[category]
            old_key = value

        # If the value given is not an old key, we
        # allow to modify labels searching for a value
        # TODO is this really ideal this way?
        # What if a typo determines a key is seen as a value?
        if not value_as_key:

            matching_items = search_value(category, value)
            try:
                old_key = matching_items[0]
                assert len(matching_items) == 1

            except IndexError:
                raise ei.PacliInputDataError("Value doesn't exist in configuration. Nothing was modified.")
            except AssertionError:
                raise ei.PacliInputDataError("More than one label for this value. Nothing was modified. Try to modify the label directly instead.")
                return
        value = config[category][old_key]

    if debug:
        print("Old config:", config)

    if mode in ("protect", "modify"):
        if (key not in config[category]) or (not config[category][key]):
            config[category].update({key : value})
        else:
            raise ei.ValueExistsError("Value already exists, you can't change it in protected mode.")
        if mode == "modify":
            del config[category][old_key]

    elif (mode == "replace") or (key not in config[category]) or (type(config[category][key]) != list):
        config[category].update({key : value})
    elif mode == "add":
        # allows to manage lists
        config[category][key].append(value)

    write_config(config, configfilename)

    if debug:
        config = get_config(configfilename)
        print("New config:", config)
    if not quiet:
        if category == "address":
            key_shown = "_".join(key.split("_")[1:])
        else:
            key_shown = key
        print("Stored {}:\nLabel: {}\nValue: {}".format(category, key_shown, value))

def write_config(config, configfilename: str=EXT_CONFIGFILE):
    with open(configfilename, "w") as configfile:
        json.dump(config, configfile)

def read_item(category: str, key: str, configfilename: str=EXT_CONFIGFILE):
    config = get_config(configfilename)
    try:
        result = config[category].get(str(key))
    except KeyError:
        raise ei.PacliInputDataError(ERR_NOCAT)
    return result


def delete_item(category: str, label: str, now: bool=False, configfilename: str=EXT_CONFIGFILE, network_name: str=Settings.network, debug: bool=False, quiet: bool=False):
    config = get_config(configfilename)

    key = network_name + "_" + label if category == "address" else label
    try:
        assert (category in config)
        if not quiet:
            print("WARNING: deleting item from category {}, label: {}, complete key: {}, value: {}".format(category, label, key, config[category][key]))
        del config[category][key]
    except KeyError:
        raise ei.PacliInputDataError("No item with this key. Nothing was deleted.")
    except AssertionError:
        raise ei.PacliInputDataError(ERR_NOCAT)

    if not now:
        print("This is a dry run. Use --now to delete irrecoverabily.")

    else:
        with open(configfilename, "w") as configfile:
            json.dump(config, configfile)
    if debug:
        print("New config file content:", config)

def search_value(category: str, value: str, configfilename: str=EXT_CONFIGFILE):
    try:
        config = get_config(configfilename)
        return [ key for key in config[category] if config[category][key] == value ]
    except KeyError:
        raise ei.PacliInputDataError(ERR_NOCAT)

def search_value_content(category: str, searchstring: str, configfilename: str=EXT_CONFIGFILE):
    try:
        config = get_config(configfilename)
        result = []
        for (key, value) in config[category].items():
            if searchstring in value:
                result.append({key : value})
        return result
        # key = [ key for key in config[category] if searchstring in config[category][key] ]
    except KeyError:
        raise ei.PacliInputDataError(ERR_NOCAT)

def process_fulllabel(fulllabel):
    # uses the network_label format.
    # this is necesary because a label can have underscores.
    label_split = fulllabel.split("_")
    network = label_split[0]
    label = "_".join(label_split[1:])
    return (network, label)

def update_categories(configfilename: str=EXT_CONFIGFILE, quiet: bool=False):
    # when a new category is added to the category list, this function adds it to the config file.
    config = get_config(configfilename)


    if CAT_INIT.keys() == config.keys():
        if not quiet:
            print("Category list is up to date.")
        return

    for cat in CAT_INIT:
        if cat not in config:
            if not quiet:
                print("Adding new category:", cat)
            config.update({cat : {} })

    write_config(config, configfilename)

def delete_category(category, configfilename: str=EXT_CONFIGFILE):
    # no tools command for this one. Should be used only manually.
    config = get_config(configfilename)
    del config[category]
    write_config(config, configfilename)

def backup_config(backupfilename: str, configfilename: str=EXT_CONFIGFILE):
    config = get_config(configfilename)
    write_config(config, backupfilename)

### Extended helper tools (api)

def list(category: str, quiet: bool=False, prettyprint: bool=True, return_list: bool=False):
    cfg = ei.run_command(get_config, quiet=quiet)
    rawdict = cfg[category]
    result_keys = [k for k in rawdict.keys()]
    result_keys.sort()
    result = {k : rawdict[k] for k in result_keys}

    if return_list:
        result_list = [{k : result[k]} for k in result]
        return result_list
    elif quiet or (not prettyprint):
        return result
    else:
        pprint(result)

def setcfg(category: str, label: str, value: str, modify: bool=False, replace: bool=False, quiet: bool=False, debug: bool=False):
    return ei.run_command(write_item, category=category, key=label, value=value, modify=modify, replace=replace, quiet=quiet, debug=debug)

def show(category: str, label: str, quiet: bool=False, debug: bool=False):
    result = ei.run_command(read_item, category=category, key=label, debug=debug)
    if result is None and not quiet:
        print("No entry was found for this label.")
    else:
        return result

def find(category: str, content: str, quiet: bool=False, prettyprint: bool=True, debug: bool=False):
    """Returns a list of matching labels if only a part of the value (content) is known."""
    result = ei.run_command(search_value_content, category, str(content), debug=debug)
    if not result and not quiet:
        print("No entry or label was found matching the search string.")
    elif quiet:
        return result
    else:
        print("Entries found with content {}:".format(content))
        if prettyprint:
            pprint(result)
        else:
            return result

def delete(category: str, label: str, now: bool=False, debug: bool=False) -> None:
    """Deletes an item from the extended config file.
       Specify category and label.
       Use --now to delete really."""
    return ei.run_command(delete_item, category, str(label), now=now, debug=debug)

