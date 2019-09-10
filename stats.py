#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from argparse import ArgumentParser

import os
import re
import sys
import unicodedata
import yaml

# Local files
import cfg
import jiralogin
from helper import vprint, eprint

###############################################################################
# Argument parser
###############################################################################


def get_parser():
    """ Takes care of script argument parsing. """
    parser = ArgumentParser(description='Script used to automatically + '
                            'update FTE fields in Initiatives')

    parser.add_argument('-c', required=False, action="store_true",
                        default=False,
                        help='Create ignore list (ignore_estimate.txt) fully \
                              populated')

    parser.add_argument('-i', required=False, action="store_true",
                        default=False,
                        help='Use ignore list (ignore_estimate.txt)')

    parser.add_argument('-k', '--key', required=False, action="store",
                        default="SWG-364",
                        help='Key, i.e., SWG-XYZ, LITE-XYZ etc')

    parser.add_argument('-p', '--project', required=False, action="store",
                        default="SWG",
                        help='Project type (SWG, PMWG, KWG etc)')

    parser.add_argument('-t', required=False, action="store_true",
                        default=False,
                        help='Use the test server')

    parser.add_argument('-v', required=False, action="store_true",
                        default=False,
                        help='Output some verbose debugging info')

    return parser

###############################################################################
# Config files
###############################################################################


def get_config_file():
    """ Returns the location for the config file (including the path). """
    for d in cfg.config_locations:
        for f in [cfg.config_filename, cfg.config_legacy_filename]:
            checked_file = d + "/" + f
            if os.path.isfile(checked_file):
                return d + "/" + f


def initiate_config():
    """ Reads the config file (yaml format) and returns the sets the global
    instance.
    """
    cfg.config_file = get_config_file()
    if not os.path.isfile(cfg.config_file):
        create_default_config()

    vprint("Using config file: %s" % cfg.config_file)
    with open(cfg.config_file, 'r') as yml:
        cfg.yml_config = yaml.load(yml, Loader=yaml.FullLoader)
###############################################################################
# Stats
###############################################################################
def stats(jira, f, key='SWG-364'):
    issue = jira.issue(key, expand='changelog')
    changelog = issue.changelog

    count = 0
    fixversions = []
    for history in changelog.histories:
        # For the creation date use: 'history.created'
        for item in history.items:
            if item.field == "Fix Version":
                #print("From: {}, To: {}".format(item.fromString, item.toString))
                bad_fixversions = ("NEXT-CYCLE", "SAN19")
                if item.toString is not None and item.toString not in bad_fixversions:
                    count += 1
                    print("{}".format(item.toString))
                    fixversions.append(item.toString)
    f.write("{}, {}, {}\n".format(key, count, ", ".join(fixversions)))


###############################################################################
# Main function
###############################################################################


def main(argv):
    global JQL
    global IGNORE_LIST
    parser = get_parser()

    # The parser arguments (cfg.args) are accessible everywhere after this
    # call.
    cfg.args = parser.parse_args()

    # This initiates the global yml configuration instance so it will be
    # accessible everywhere after this call.
    initiate_config()

    project = "SWG"
    key = "SWG-364"

    jira, username = jiralogin.get_jira_instance(cfg.args.t)

    if cfg.args.project:
        project = cfg.args.project

    if cfg.args.key:
        key = cfg.args.key

    with open("stats.txt", 'w') as f:
        jql = "project={} AND issuetype in (Epic, Initiative)".format(project)
        #jql = "project={} AND issuetype in (Epic, Initiative) AND status not in (Resolved, Closed)".format(project)
        print("JQL: \"{}\"".format(jql))
        issues = jira.search_issues(jql)
        total = issues.total
        print("Found {} (of {}) issues in {}".format(len(issues), total, project))
        print("Query again for all issues found ...")
        issues = jira.search_issues(jql.format(project), maxResults=total)
        print("Found {} issues in {}".format(len(issues), project))
        for issue in issues:
            print("{} ...".format(issue.key))
            stats(jira, f, issue.key)

    jira.close()
    print("Done!")


if __name__ == "__main__":
    main(sys.argv)
