# Globals
g_config_file = "config.txt"

g_cfg_field_api_key = "api_key"
g_cfg_field_api_secret = "api_secret_key"

g_config_fields = [g_cfg_field_api_key, g_cfg_field_api_secret]

def _generate_new_config_file():
    # Generate a new config file
    print("Generating new 'config.txt' file.")

    values = {}
    for field in g_config_fields:
        val = input("{}: ".format(field)).strip()
        values[field] = val
    
    config_lines = [k + "=" + v + "\n" for k,v in values.items()]

    with open(g_config_file, "w") as cf:
        cf.writelines(config_lines)

    return values


def get_api_keys():
    # parse the file and return public, private keys
    try:
        with open(g_config_file, "r") as cf:
            config_lines = cf.readlines()
    except:
        # if we couldn't find the config file, generate a new one through user input
        print("'config.txt' doesn't exist...")
        config_vals = _generate_new_config_file()
        return config_vals[g_cfg_field_api_key], config_vals[g_cfg_field_api_secret]

    # look for api_key

    api_key_line = list(filter(lambda s: s.find(g_cfg_field_api_key) != -1, config_lines))[0]
    api_key = api_key_line.split("=")[1].strip()

    # look for secret key
    api_secret_key_line = list(filter(lambda s: s.find(g_cfg_field_api_secret) != -1, config_lines))[0]
    api_secret_key = api_secret_key_line.split("=")[1].strip()

    # sanity
    if not api_secret_key or not api_key:
        raise("No api keys found in config.txt!")

    return api_key, api_secret_key

# should be imported...
def main():
    pass

if __name__ == "__main__":
    main()