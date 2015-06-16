#!/usr/bin/env python2
import sys, os, json, argparse, re
import yaml
from app.oauth import OAuth
from app.expression import expr_constructor, json_constructor
from app import default
import apiclient

def main():
    parser = argparse.ArgumentParser(description='Endpoint tester')
    parser.add_argument("--auth", metavar='AUTH_CONFIG_FILE', type=str,
                        help='The configuration file containg authentication information')
    parser.add_argument("scenario_file", metavar='SCENARIO_FILE', type=str, nargs="?",
                        help='The path to the scenario file')
    args = parser.parse_args()

    if args.scenario_file:
        scenario_root = os.path.abspath(os.path.join(os.path.abspath(args.scenario_file), os.pardir))
        scenario_file_path = os.path.abspath(args.scenario_file)

        # check that there is a scenario file
        if not os.path.isfile(scenario_file_path):
            print "{} does not exist".format(scenario_file_path)
            return -1

        with open(scenario_file_path, 'r') as scene_file:
            yaml.add_constructor('!expr', expr_constructor)
            yaml.add_constructor('!json', json_constructor)
            scene = yaml.load(scene_file)
    else:
        scenario_root = os.path.abspath(os.path.join(os.path.abspath("."), os.pardir))
        yaml.add_constructor('!expr', expr_constructor)
        yaml.add_constructor('!json', json_constructor)
        scene = yaml.load(sys.stdin.read())


    if args.auth:
        # check that there is a config file
        if not os.path.isfile(args.auth):
            print "{} does not exist".format(args.auth)
            return -1

        with open(args.auth, 'r') as conf:
            config = yaml.load(conf)
    else:
        config = {}

    command_parser = default.CommandParser(config, scene, scenario_root)
    return command_parser.parse()

if __name__ == "__main__":
    sys.exit(main())
