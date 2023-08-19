import json, os
import pacli.extended_interface as ei
from pacli.config import conf_dir

# This stores some settings in an additional config file, for example short keys for addresses, proposals, decks etc.
# An alternative for the future could be to use sqlite3 eventually.

EXT_CONFIGFILE = os.path.join(conf_dir, "extended_config.json")
CATEGORIES = ["address", "checkpoint", "deck", "proposal", "donation", "transaction", "utxo" ]
CAT_INIT = {c : {} for c in CATEGORIES}

# modes:
# "replace" : value gets replaced, key stays the same
# "modify" : label gets replaced (entry is deleted and a new entry is generated)
# "add" : an item is added to a list
# "protect" : only allows additions of new labels, no modifications (default)
MODES = ["replace", "modify", "add", "protect"]

class ValueExistsError(Exception):
    pass

def get_config(configfilename: str=EXT_CONFIGFILE) -> dict:

    try:
        with open(configfilename, "r") as configfile:
            try:
                return json.load(configfile)
            except json.JSONDecodeError as e:
                if len(configfile.read()) == 0:
                    print("Empty file. Returning default config.")
                    return CAT_INIT
                else:
                    raise json.JSONDecodeError(e)
    except FileNotFoundError:
        print("File does not exist. Returning default config.")
        return CAT_INIT


def write_item(category: str, key: str, value: str, configfilename: str=EXT_CONFIGFILE, network_name: str=None, modify: bool=False, add: bool=False, replace: bool=False, debug: bool=False) -> None:

    # to allow simple command line arguments and avoid additional per-command processing,
    # this listcomp generates the mode from the add and modify bool variables.
    # the True value at the end means that "protect" (MODES[-1]) is the default.
    mode = [MODES[i] for i, m in enumerate([replace, modify, add, True]) if m][0]

    if debug:
        print("Storing: category: {}, key: {}, value: {}".format(category, key, value))

    config = get_config(configfilename)
    print(category, key, value, mode, network_name)
    if mode == "modify":
        if category == "address":
            old_key = network_name + "_" + value
            value_as_key = old_key in config[category]
        else:
            value_as_key = value in config[category]
            old_key = value

        if not value_as_key: # allows to modify labels directly

            matching_items = search_value(category, value)
            try:
                old_key = matching_items[0]
                assert len(matching_items) == 1

            except IndexError:
                ei.print_red("Error: Value doesn't exist in configuration. Nothing was modified.")
                return
            except AssertionError:
                ei.print_red("Error: More than one label for this value. Nothing was modified. Try to modify the label directly instead.")
                return
        value = config[category][old_key]

    if debug:
        print("Old config:", config)

    if mode in ("protect", "modify"):
        if (key not in config[category]) or (not config[category][key]):
            config[category].update({key : value})
        else:
            raise ValueExistsError("Value already exists, you can't change it in protected mode.")
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

def write_config(config, configfilename: str=EXT_CONFIGFILE):
    with open(configfilename, "w") as configfile:
        json.dump(config, configfile)

def read_item(category: str, key: str, configfilename: str=EXT_CONFIGFILE):
    config = get_config(configfilename)
    return config[category].get(str(key))

def delete_item(category: str, key: str, now: bool=False, configfilename: str=EXT_CONFIGFILE, debug: bool=False, silent: bool=False):
    config = get_config(configfilename)

    try:
        if not silent:
            print("WARNING: deleting item from category {}, key: {}, value: {}".format(category, key, config[category][key]))

        del config[category][key]
    except KeyError:
        # raise ValueError("No item with this key. Nothing was deleted.")
        ei.print_red("Error: No item with this key. Nothing was deleted.")
        return

    if not now:
        print("This is a dry run. Use --now to delete irrecoverabily.")

    else:
        with open(configfilename, "w") as configfile:
            json.dump(config, configfile)
    if debug:
        print("New config file content:", config)

def search_value(category: str, value: str, configfilename: str=EXT_CONFIGFILE):
    config = get_config(configfilename)
    return [ key for key in config[category] if config[category][key] == value ]

def search_value_content(category: str, searchstring: str, configfilename: str=EXT_CONFIGFILE):
    config = get_config(configfilename)
    return [ key for key in config[category] if searchstring in config[category][key] ]

def process_fulllabel(fulllabel):
    # uses the network_label format
    label_split = fulllabel.split("_")
    network = label_split[0]
    label = "_".join(label_split[1:])
    return (network, label)

def update_categories(configfilename: str=EXT_CONFIGFILE, debug: bool=False):
    # when a new category is added to the category list, this function adds it to the config file.
    config = get_config(configfilename)
    for cat in CAT_INIT:
        if cat not in config:
            if debug:
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



