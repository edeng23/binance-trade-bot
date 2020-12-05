# Globals
g_config_file = "config.txt"

class ConfigMan():

    cfg_field_api_key = "api_key"
    cfg_field_api_secret = "api_secret_key"
    cfg_field_current_coin = "current_coin"

    cfg_fields = [cfg_field_api_key, cfg_field_api_secret, cfg_field_current_coin]

    def __init__(self):
        # read config file
        try:
            with open(g_config_file, "r") as cf:
                config_lines = cf.readlines()

            values = {}
            for cl in config_lines:
                key, val = [s.strip() for s in cl.split("=")]
                values[key] = val
            
            self.config_values = values
        except:
            # if file doesn't exist
            values = self._generate_new_config_file()
            self.config_values = values

    def get_api_keys(self):
        return self.config_values[self.cfg_field_api_key], self.config_values[self.cfg_field_api_secret]
    
    def get_current_coin(self):
        return self.config_values[self.cfg_field_current_coin]

    def _generate_new_config_file(self):
        # Generate a new config file
        print("Generating new 'config.txt' file.")

        values = {}
        for field in self.cfg_fields:
            val = input("{}: ".format(field)).strip()
            values[field] = val
        
        config_lines = [k + "=" + v + "\n" for k,v in values.items()]

        with open(g_config_file, "w") as cf:
            cf.writelines(config_lines)

        return values

# should be imported...
def main():
    pass

if __name__ == "__main__":
    main()